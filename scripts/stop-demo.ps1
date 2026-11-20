# Stops the sandbox (port 8000) and n8n (ports 5678 and 5679) started by start-demo.
foreach ($port in 5678, 5679, 8000) {
    $listeners = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    foreach ($processId in ($listeners.OwningProcess | Sort-Object -Unique)) {
        taskkill /PID $processId /T /F | Out-Null
        Write-Host "Stopped process $processId (port $port)"
    }
}
Write-Host "Demo stopped."
