# go_live.ps1 - connect the local repositories to their (already created, EMPTY) GitHub repositories and push.
#
#   powershell -ExecutionPolicy Bypass -File go_live.ps1                 # all repositories below
#   powershell -ExecutionPolicy Bypass -File go_live.ps1 -Only picthis   # just one
#
# Safety rules it enforces for every repository:
#   * a repository that must be PRIVATE is not pushed if GitHub shows it as public (an anonymous request must get 404)
#   * the PUBLIC facade is not pushed unless the leak guard says CLEAN and its history is exactly one commit
#   * after each push, the remote's head must equal the local head
# It never creates repositories (create them empty, with NO README / licence / .gitignore) and never stores or prints any credential:
# pushes use your normal Git login.
param([string]$Owner = "jamalemccarthy3-dev", [string]$Only = "")

$ErrorActionPreference = "Continue"
$env:GIT_TERMINAL_PROMPT = "0"
$Work = Split-Path -Parent $PSScriptRoot
$Repos = @(
    @{ Name = "nexxus-architecture"; Dir = "C:\Users\Jamal\Desktop\public_facade"; Public = $true },
    @{ Name = "axis-bridge";         Dir = $Work;                                  Public = $false },
    @{ Name = "axis-core";           Dir = Join-Path $Work "axis-ui-interface\project-X\silo_vault\axis-core"; Public = $false },
    @{ Name = "picthis";             Dir = "C:\Users\Jamal\Desktop\picthis";       Public = $false },
    @{ Name = "theblogguyengine";    Dir = "C:\Users\Jamal\Desktop\TheBlogGuyEngine"; Public = $false },
    @{ Name = "theblogguy";          Dir = "C:\Users\Jamal\Desktop\TheBlogGuy";    Public = $false }
)

function Anonymous-Status($owner, $name) {
    try { (Invoke-WebRequest -UseBasicParsing -Uri "https://api.github.com/repos/$owner/$name" -TimeoutSec 30).StatusCode }
    catch { if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { 0 } }
}

foreach ($r in $Repos) {
    if ($Only -and $r.Name -ne $Only) { continue }
    Write-Host ("`n=== {0}  ({1})" -f $r.Name, $(if ($r.Public) { "PUBLIC" } else { "private" }))
    if (-not (Test-Path (Join-Path $r.Dir ".git"))) { Write-Host "  SKIP: no git repository at $($r.Dir)"; continue }
    Push-Location $r.Dir
    try {
        $status = Anonymous-Status $Owner $r.Name
        if ($r.Public -and $status -ne 200) { Write-Host "  STOP: create the repository first (anonymous check: HTTP $status, expected 200 for an empty public repo)"; continue }
        if (-not $r.Public -and $status -ne 404) { Write-Host "  STOP: HTTP $status. A private repository must answer 404 to an anonymous request. If it is missing, create it; if it shows as public, make it private."; continue }
        if ((git status --short | Measure-Object).Count -ne 0) { Write-Host "  STOP: uncommitted changes"; continue }
        if ($r.Public) {
            $count = [int](git rev-list --count HEAD)
            python (Join-Path $PSScriptRoot "build_facade.py") verify | Out-Host
            if ($LASTEXITCODE -ne 0 -or $count -ne 1) { Write-Host "  STOP: the public facade must pass the leak guard and be exactly one commit (commits: $count)"; continue }
        }
        $url = "https://github.com/$Owner/$($r.Name).git"
        if ((git remote) -contains "origin") { git remote set-url origin $url } else { git remote add origin $url }
        git branch -M main
        # A repository that already has commits (for example a scaffold made on github.com) is MERGED, never overwritten: no force push, ever.
        git fetch origin 2>&1 | Out-Null
        git rev-parse --verify --quiet origin/main 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            git merge-base --is-ancestor origin/main HEAD 2>$null
            if ($LASTEXITCODE -ne 0) {
                if ($r.Public) { Write-Host "  STOP: the public repository already has commits; it must be created empty"; continue }
                Write-Host "  The remote already has commits that this history does not contain: merging them in (no force push)"
                git merge --allow-unrelated-histories --no-edit origin/main 2>&1 | Select-Object -Last 3 | Out-Host
                if ($LASTEXITCODE -ne 0) { git merge --abort 2>$null; Write-Host "  STOP: merge conflict; nothing was pushed. Resolve it by hand."; continue }
            }
        }
        git push -u origin main 2>&1 | Select-Object -Last 3 | Out-Host
        $local = (git rev-parse HEAD).Trim()
        $remote = ((git ls-remote origin main) -split "\s+")[0]
        if ($local -eq $remote) { Write-Host ("  OK: in sync at {0}" -f $local.Substring(0, 7)) } else { Write-Host "  PROBLEM: the remote head does not match the local head" }
    } finally { Pop-Location }
}
Write-Host "`nDone. Re-run any single repository with -Only <name>."
