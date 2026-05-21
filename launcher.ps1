# Twit-Auto silent launcher.
# Spawns API + bot + dashboard as truly headless processes via cmd /c.
# Output goes to twit-auto\logs\. PIDs saved to .pids for the stopper.

$ErrorActionPreference = "Continue"
$root    = "C:\Users\Abhishek Satarkar\Desktop\projects\twit-auto"
$logDir  = Join-Path $root "logs"
$pidFile = Join-Path $root ".pids"

New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Start-Hidden {
    param([string]$Name, [string]$Cmd, [string]$Cwd)

    $logPath = Join-Path $logDir "$Name.log"
    # cmd /c handles redirect natively; CreateNoWindow truly hides the console.
    $args = "/c $Cmd > `"$logPath`" 2>&1"

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName        = "cmd.exe"
    $psi.Arguments       = $args
    $psi.WorkingDirectory = $Cwd
    $psi.UseShellExecute  = $false
    $psi.CreateNoWindow   = $true

    try {
        $p = [System.Diagnostics.Process]::Start($psi)
        return $p.Id
    } catch {
        "[$(Get-Date -Format o)] Failed to start $Name : $_" |
            Out-File -FilePath (Join-Path $logDir "launcher.err.log") -Append -Encoding ascii
        return $null
    }
}

# --- Pre-flight: don't double-start ---
try {
    Invoke-WebRequest -Uri "http://localhost:3000" -UseBasicParsing -TimeoutSec 1 | Out-Null
    # Already running — just open browser
    Start-Process "chrome.exe" -ArgumentList "http://localhost:3000" -ErrorAction SilentlyContinue
    if (-not $?) { Start-Process "http://localhost:3000" }
    exit 0
} catch { }

# --- Spawn the three processes ---
$pids = @{}

$pids.api = Start-Hidden -Name "api" `
    -Cmd "python -m uvicorn api_server:app --port 8000" `
    -Cwd (Join-Path $root "bot")

$pids.bot = Start-Hidden -Name "bot" `
    -Cmd "python x_automation_bot.py" `
    -Cwd (Join-Path $root "bot")

$pids.dashboard = Start-Hidden -Name "dashboard" `
    -Cmd "npm run dev" `
    -Cwd (Join-Path $root "dashboard")

$pids | ConvertTo-Json | Out-File -FilePath $pidFile -Encoding ascii

# --- Wait for dashboard to come up, then open Chrome ---
$deadline = (Get-Date).AddSeconds(180)
$ready = $false
while ((Get-Date) -lt $deadline) {
    try {
        Invoke-WebRequest -Uri "http://localhost:3000" -UseBasicParsing -TimeoutSec 2 | Out-Null
        $ready = $true
        break
    } catch {
        Start-Sleep -Seconds 2
    }
}

if ($ready) {
    # Prefer Chrome explicitly; fall back to default browser.
    $chromePaths = @(
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
        "$env:LocalAppData\Google\Chrome\Application\chrome.exe"
    )
    $chrome = $chromePaths | Where-Object { Test-Path $_ } | Select-Object -First 1
    if ($chrome) {
        Start-Process -FilePath $chrome -ArgumentList "--new-window","http://localhost:3000"
    } else {
        Start-Process "http://localhost:3000"
    }
} else {
    "[$(Get-Date -Format o)] Dashboard did not respond within 180s. Check logs\dashboard.log." |
        Out-File -FilePath (Join-Path $logDir "launcher.err.log") -Append -Encoding ascii
}
