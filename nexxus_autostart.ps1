# nexxus_autostart.ps1 - bring up the NEXXUS server and all 21 engines. Safe to run any time:
# it only starts what is NOT already running (no duplicates). Logs to logs\autostart.log.
# -NoDelay      skip the 20 s settle wait (the watchdog uses this)      -NoWatchdog   do not launch the watchdog (the watchdog uses this)
param([switch]$NoDelay, [switch]$NoWatchdog)
$root = $PSScriptRoot
$log  = Join-Path $root "logs\autostart.log"
New-Item -ItemType Directory -Force (Join-Path $root "logs") | Out-Null
function Say($m) { ("{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $m) | Add-Content $log }

$engines = "axis-cloud","axis-core","axis-curator","axis-diagnostic","axis-drive","axis-integrity","axis-link","axis-llm","axis-logic","axis-omni","axis-phonetic","axis-port","axis-SandM","axis-search_engine","axis-sweep","axis-triage","axis-validator","axis-vantage_point","axis-video_creator","axis-vision","render"

Say "autostart begin"
if (-not $NoDelay) { Start-Sleep -Seconds 20 }          # let Windows finish logging in before loading 22 Python processes

# 1. server (nexxus_env.bat supplies the shared secret and PYTHONPATH)
$listening = netstat -ano | Select-String ":8000 .*LISTENING"
if ($listening) {
    Say "server already listening on 8000 - leaving it alone"
} else {
    Start-Process cmd.exe -ArgumentList '/k', "title NEXXUS server & call `"$root\nexxus_env.bat`" && call `"$root\nexxus_admin.bat`" && cd /d `"$root`" && python python_server.py" -WindowStyle Minimized
    Say "server started"
}

# 2. wait (up to 90 s) for the server to answer before starting engines
$up = $false
for ($i = 0; $i -lt 45 -and -not $up; $i++) {
    try { $up = ((Invoke-WebRequest "http://127.0.0.1:8000/api/mesh/telemetry" -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200) } catch { Start-Sleep -Seconds 2 }
}
if (-not $up) { Say "WARNING: server did not answer in 90 s - starting engines anyway (they keep retrying)" }

# 3. engines: start only the ones with no running window, one every 2 s so the CPU is not swamped
$titles = @(Get-Process cmd -ErrorAction SilentlyContinue | ForEach-Object { $_.MainWindowTitle })
$started = 0
foreach ($e in $engines) {
    if ($titles -contains "ENGINE $e") { continue }
    Start-Process cmd.exe -ArgumentList '/c', "title ENGINE $e & call `"$root\start_engine.bat`" $e >> `"$root\logs\engine_$e.log`" 2>&1" -WindowStyle Minimized
    $started++
    Start-Sleep -Seconds 2
}
Say "engines: started $started, already running $($engines.Count - $started)"

# 4. the module gateway (port 8080). It has its own login entry and restarts itself, so this only covers "not running at all".
if (netstat -ano | Select-String ":8080 .*LISTENING") {
    Say "gateway already listening on 8080 - leaving it alone"
} else {
    Start-Process wscript.exe -ArgumentList '//nologo', "`"$root\axis-ui-interface\_gateway\hidden_start_gateway.vbs`"" -WindowStyle Hidden
    Say "gateway started"
}

# 5. the watchdog: keeps the gateway and the NEXXUS server standing. One copy only - it exits at once if one is already running.
if (-not $NoWatchdog) {
    Start-Process powershell.exe -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden', '-File', "`"$root\nexxus_watchdog.ps1`"" -WindowStyle Hidden
    Say "watchdog launched"
}
Say "autostart done"
