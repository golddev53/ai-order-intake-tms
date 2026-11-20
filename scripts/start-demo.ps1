# Starts the sandbox and n8n locally (no Docker), waits until both respond, and opens them in the browser.
# Usage: .\scripts\start-demo.ps1 [-N8nDir <folder containing node_modules\n8n>] [-Import] [-NoBrowser]
#   -N8nDir    Where n8n is installed (npm install n8n@2.48.6 in that folder). Its data lives in <N8nDir>\data.
#   -Import    Re-import and publish the workflows from .\workflows (automatic on first run).
#   -NoBrowser Don't open the dashboard and editor.
param(
    [string]$N8nDir = "$env:TEMP\n8n-test",
    [switch]$Import,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$sandboxUrl = "http://127.0.0.1:8000/mock/state"
$n8nUrl = "http://localhost:5678/healthz"

function Test-Url([string]$url) {
    try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 $url | Out-Null; return $true } catch { return $false }
}

function Wait-Url([string]$url, [string]$name, [int]$seconds) {
    $deadline = (Get-Date).AddSeconds($seconds)
    while (-not (Test-Url $url)) {
        if ((Get-Date) -gt $deadline) { throw "$name did not start within $seconds seconds. Check its minimized window for errors." }
        Start-Sleep -Seconds 2
    }
    Write-Host "  $name is up" -ForegroundColor Green
}

# --- Environment: .env (or .env.example), pointed at the local sandbox instead of the Docker hostname
$envFile = if (Test-Path "$root\.env") { "$root\.env" } else { "$root\.env.example" }
$vars = @{}
foreach ($line in Get-Content $envFile) {
    if ($line -match '^\s*([A-Z0-9_]+)=(.*)$') {
        $vars[$Matches[1]] = $Matches[2].Trim() -replace 'http://sandbox:8000', 'http://127.0.0.1:8000'
    }
}
# n8n stores its own key in the data folder on first start; passing a different one locks it out.
$vars.Remove("N8N_ENCRYPTION_KEY")
$vars["N8N_USER_FOLDER"] = "$N8nDir\data"
$vars["N8N_BLOCK_ENV_ACCESS_IN_NODE"] = "false"
$vars["N8N_WEBHOOK_URL"] = "http://localhost:5678/"
$vars["N8N_SECURE_COOKIE"] = "false"
$vars["N8N_DIAGNOSTICS_ENABLED"] = "false"
foreach ($key in $vars.Keys) { Set-Item "env:$key" $vars[$key] }

# --- Tools
$portableNode = Get-ChildItem $N8nDir -Directory -Filter "node-v*" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($portableNode) { $env:Path = "$($portableNode.FullName);$env:Path" }
$n8n = "$N8nDir\node_modules\.bin\n8n.cmd"
if (-not (Test-Path $n8n)) {
    throw "n8n not found in $N8nDir. Install it with: cd `"$N8nDir`"; npm install n8n@2.48.6  (needs Node.js 24+), or pass -N8nDir."
}

$python = "$root\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "Creating Python environment for the sandbox..."
    python -m venv "$root\.venv"
    & $python -m pip install -q -r "$root\sandbox\requirements.txt"
}

# --- Sandbox
Write-Host "Sandbox (mock TMS, AI, Maps, Slack, email)"
if (Test-Url $sandboxUrl) {
    Write-Host "  already running" -ForegroundColor Yellow
} else {
    Start-Process -FilePath $python -WorkingDirectory $root -WindowStyle Minimized `
        -ArgumentList "-m uvicorn app:app --app-dir `"$root\sandbox`" --host 127.0.0.1 --port 8000"
    Wait-Url $sandboxUrl "Sandbox" 60
}

# --- n8n
Write-Host "n8n"
if (Test-Url $n8nUrl) {
    Write-Host "  already running (stop it first with stop-demo to re-import workflows)" -ForegroundColor Yellow
} else {
    if ($Import -or -not (Test-Path "$N8nDir\data\.n8n\database.sqlite")) {
        Write-Host "  importing workflows (takes a couple of minutes)..."
        & $n8n import:workflow --separate --input="$root\workflows" *> "$N8nDir\import.log"
        if ($LASTEXITCODE -ne 0) { throw "Workflow import failed. See $N8nDir\import.log" }
        foreach ($id in "aiIntakeAlerts01", "aiIntakeReview01", "aiIntakeMain0001") {
            & $n8n publish:workflow --id=$id *> "$N8nDir\publish.log"
            if ($LASTEXITCODE -ne 0) { throw "Publishing $id failed. See $N8nDir\publish.log" }
        }
    }
    Start-Process -FilePath $n8n -ArgumentList "start" -WindowStyle Minimized
    Wait-Url $n8nUrl "n8n" 240
}

# n8n reports healthy before it has activated the workflows; a GET on the POST-only intake
# webhook answers "Did you mean to make a POST request?" once it is registered.
$deadline = (Get-Date).AddSeconds(90)
while (-not ((curl.exe -s http://localhost:5678/webhook/order-intake) -match "POST request")) {
    if ((Get-Date) -gt $deadline) { throw "The intake webhook was not registered. Open http://localhost:5678 and check that the workflows are published." }
    Start-Sleep -Seconds 2
}
Write-Host "  workflows are active" -ForegroundColor Green

if (-not $NoBrowser) {
    Start-Process "http://localhost:8000"
    Start-Process "http://localhost:5678"
}

Write-Host ""
Write-Host "Demo is ready." -ForegroundColor Green
Write-Host "  Dashboard:  http://localhost:8000   (click 'Reset sandbox' before recording)"
Write-Host "  n8n editor: http://localhost:5678"
Write-Host "  Send an order:  .\scripts\send-sample.ps1 samples\01-email-clean.json"
Write-Host "  Stop everything: .\scripts\stop-demo.cmd"
