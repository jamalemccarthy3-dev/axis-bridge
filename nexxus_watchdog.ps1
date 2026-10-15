# nexxus_watchdog.ps1 - keeps the NEXXUS side of the system standing while you are logged in.
#
# Every IntervalSeconds it checks two ports on this computer:
#   8080  the module gateway (PICTHIS, the Blog Guy, ...)    - normally restarts itself within seconds (run_gateway.bat loops);
#                                                              this only matters if that loop itself is gone
#   8000  the NEXXUS server                                  - started through nexxus_autostart.ps1, which also starts any missing engine
# A port must be down for FailsBeforeRestart checks in a row before anything is started (so it can never race a normal restart).
# It only ever STARTS what is missing. It never stops or kills anything. If something keeps dying (5 restarts in 15 minutes) it
# stops trying for 15 minutes instead of looping forever. Every ReviveEnginesEveryPasses checks it also re-runs the idempotent
# autostart so a crashed engine comes back. Only one copy runs at a time. Everything it does is written to logs\watchdog_private.log.
#
#   -Once        one check, then exit (used by the tests)        -DryRun   log what it would start, start nothing
param(
    [int]$IntervalSeconds = 30,
    [int]$FailsBeforeRestart = 2,
    [int]$ReviveEnginesEveryPasses = 20,
    [int]$GatewayPort = 8080,
    [int]$ServerPort = 8000,
    [string]$GatewayStartCmd = "",
    [string]$ServerStartCmd = "",
    [string]$Root = $PSScriptRoot,
    [string]$LogFile = "",
    [switch]$Once,
    [switch]$DryRun
)
if (-not $LogFile) { $LogFile = Join-Path $Root "logs\watchdog_private.log" }
New-Item -ItemType Directory -Force (Split-Path $LogFile) | Out-Null

function Say($m) {
    try {
        if ((Test-Path $LogFile) -and ((Get-Item $LogFile).Length -gt 1MB)) { Move-Item $LogFile "$LogFile.1" -Force }
        ("{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $m) | Add-Content $LogFile
    } catch {}
}

function Test-Port([int]$port) {
    try {
        $c = New-Object System.Net.Sockets.TcpClient
        $iar = $c.BeginConnect("127.0.0.1", $port, $null, $null)
        $ok = $iar.AsyncWaitHandle.WaitOne(800)
        if ($ok) { try { $c.EndConnect($iar) } catch { $ok = $false } }
        $c.Close()
        return $ok
    } catch { return $false }
}

# one copy only (not for -Once, which the tests run in parallel with a real one)
$mutex = $null
if (-not $Once) {
    $mutex = New-Object System.Threading.Mutex($false, "Local\NEXXUS_Watchdog")
    if (-not $mutex.WaitOne(0)) { Say "another watchdog is already running - exiting"; exit 0 }
}

function Start-Gateway {
    if ($GatewayStartCmd) { Start-Process cmd.exe -ArgumentList '/c', "`"$GatewayStartCmd`"" -WindowStyle Hidden }     # outer quotes: cmd /c mangles a command that starts with a quoted path
    else { Start-Process wscript.exe -ArgumentList '//nologo', "`"$Root\axis-ui-interface\_gateway\hidden_start_gateway.vbs`"" -WindowStyle Hidden }
}
function Start-Server {   # the server AND any missing engine (the autostart script is idempotent)
    if ($ServerStartCmd) { Start-Process cmd.exe -ArgumentList '/c', "`"$ServerStartCmd`"" -WindowStyle Hidden }
    else { Start-Process powershell.exe -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden', '-File', "`"$Root\nexxus_autostart.ps1`"", '-NoDelay', '-NoWatchdog' -WindowStyle Hidden }
}

$targets = @(
    @{ name = "gateway"; port = $GatewayPort; start = { Start-Gateway }; fails = 0; starts = @(); quietUntil = [datetime]::MinValue },
    @{ name = "server";  port = $ServerPort;  start = { Start-Server };  fails = 0; starts = @(); quietUntil = [datetime]::MinValue }
)

Say ("watchdog start (every {0}s, restart after {1} misses{2})" -f $IntervalSeconds, $FailsBeforeRestart, $(if ($DryRun) { ", DRY RUN" } else { "" }))
$pass = 0
try {
    while ($true) {
        $pass++
        foreach ($t in $targets) {
            if (Test-Port $t.port) {
                if ($t.pendingSince) { Say ("$($t.name) is back on $($t.port) ({0:N0} s after it was started)" -f ((Get-Date) - $t.pendingSince).TotalSeconds); $t.pendingSince = $null }
                elseif ($t.fails -ge 1) { Say "$($t.name) is back on $($t.port) (on its own)" }
                $t.fails = 0
                continue
            }
            $t.fails++
            if ($t.fails -lt $FailsBeforeRestart) { Say "$($t.name) not answering on $($t.port) (miss $($t.fails) of $FailsBeforeRestart)"; continue }
            if ((Get-Date) -lt $t.quietUntil) { continue }
            $t.starts = @($t.starts | Where-Object { $_ -gt (Get-Date).AddMinutes(-15) })
            if ($t.starts.Count -ge 5) {
                $t.quietUntil = (Get-Date).AddMinutes(15)
                Say "$($t.name) keeps dying (5 restarts in 15 minutes) - backing off for 15 minutes"
                continue
            }
            if ($DryRun) { Say "DRY RUN: would start the $($t.name)"; continue }
            Say "$($t.name) is down on port $($t.port) - starting it"
            try { & $t.start } catch { Say "could not start the $($t.name): $($_.Exception.Message)" }
            $t.starts += (Get-Date)
            $t.pendingSince = Get-Date
            $t.fails = 0
        }
        if (-not $Once -and $ReviveEnginesEveryPasses -gt 0 -and ($pass % $ReviveEnginesEveryPasses) -eq 0 -and -not $DryRun -and (Test-Port $ServerPort)) {
            Say "periodic check: re-running the idempotent autostart (starts only what is missing)"
            try { Start-Server } catch { Say "periodic autostart failed: $($_.Exception.Message)" }
        }
        if ($Once) { break }
        Start-Sleep -Seconds $IntervalSeconds
    }
} finally {
    if ($mutex) { try { $mutex.ReleaseMutex() } catch {} }
}
