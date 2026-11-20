# Sends a sample order to the n8n intake webhook and prints the result.
# Usage: .\scripts\send-sample.ps1 samples\01-email-clean.json
param(
    [string]$File = "samples\01-email-clean.json",
    [string]$Url = "http://localhost:5678/webhook/order-intake"
)

$tomorrow = (Get-Date).AddDays(1).ToString("yyyy-MM-dd")
$body = (Get-Content $File -Raw).Replace("{{TOMORROW}}", $tomorrow)
$result = Invoke-RestMethod -Method Post -Uri $Url -ContentType "application/json" -Body ([Text.Encoding]::UTF8.GetBytes($body))
$result | ConvertTo-Json -Depth 10
