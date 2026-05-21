# Launches all three processes in separate PowerShell windows.
# Run from project root: .\start.ps1

$root = $PSScriptRoot

Write-Host "Launching X Bot, API server, and Dashboard..." -ForegroundColor Magenta

# 1. Bot
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "cd '$root\bot'; Write-Host 'X BOT' -ForegroundColor Cyan; python x_automation_bot.py"
)

Start-Sleep -Seconds 2

# 2. API bridge
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "cd '$root\bot'; Write-Host 'API SERVER' -ForegroundColor Cyan; python -m uvicorn api_server:app --port 8000"
)

Start-Sleep -Seconds 2

# 3. Dashboard
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "cd '$root\dashboard'; Write-Host 'DASHBOARD' -ForegroundColor Cyan; npm run dev"
)

Write-Host ""
Write-Host "All three processes launched in separate windows." -ForegroundColor Green
Write-Host "Open dashboard at: http://localhost:3000" -ForegroundColor Yellow
