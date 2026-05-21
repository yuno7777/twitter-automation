# Twit-Auto silent stopper. Kills the 3 processes (and their children) by PID.

$root = "C:\Users\Abhishek Satarkar\Desktop\projects\twit-auto"
$pidFile = Join-Path $root ".pids"

if (Test-Path $pidFile) {
    try {
        $pids = Get-Content $pidFile -Raw | ConvertFrom-Json
        foreach ($name in @("api","bot","dashboard")) {
            $procId = $pids.$name
            if ($procId) {
                # /T kills the process tree, /F forces
                cmd /c "taskkill /F /T /PID $procId" 2>$null | Out-Null
            }
        }
        Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    } catch {}
}

# Belt-and-suspenders: kill any stragglers matching our command lines
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -like '*x_automation_bot*' -or $_.CommandLine -like '*uvicorn*api_server*' } |
    ForEach-Object { cmd /c "taskkill /F /T /PID $($_.ProcessId)" 2>$null | Out-Null }

Get-CimInstance Win32_Process -Filter "Name='node.exe'" |
    Where-Object { $_.CommandLine -like '*next*dev*' -or $_.CommandLine -like '*x-bot-dashboard*' } |
    ForEach-Object { cmd /c "taskkill /F /T /PID $($_.ProcessId)" 2>$null | Out-Null }
