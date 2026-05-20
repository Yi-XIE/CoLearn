param(
    [string]$ConfigPath = "D:\Colearn-nightly\.colearn\nanobot-v0.2-slim.config.json",
    [string]$Workspace = "D:\Colearn-nightly\.colearn\nanobot-workspace",
    [switch]$OpenBrowser
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$nanobotRoot = Join-Path $repoRoot "third_party\nanobot-0.2.0\nanobot-0.2.0"

if (!(Test-Path $ConfigPath)) {
    throw "Config not found: $ConfigPath"
}

if (!(Test-Path $nanobotRoot)) {
    throw "nanobot v0.2 source not found: $nanobotRoot"
}

if (!(Test-Path $Workspace)) {
    New-Item -ItemType Directory -Path $Workspace -Force | Out-Null
}

if (!(Test-Path "$repoRoot\.colearn\tmp")) {
    New-Item -ItemType Directory -Path "$repoRoot\.colearn\tmp" -Force | Out-Null
}

$env:PYTHONPATH = "$repoRoot;$nanobotRoot"
$env:COLEARN_REPO_ROOT = $repoRoot
$env:COLEARN_STATE_ROOT = Join-Path $repoRoot ".colearn\state"
$env:COLEARN_NANOBOT_WORKSPACE = $Workspace
$env:TMP = "$repoRoot\.colearn\tmp"
$env:TEMP = "$repoRoot\.colearn\tmp"

$envPath = Join-Path $repoRoot ".env"
if (Test-Path $envPath) {
    Get-Content $envPath | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) {
            return
        }
        $name, $value = $line.Split("=", 2)
        $name = $name.Trim()
        $value = $value.Trim().Trim('"')
        if ($name) {
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
}

if (-not $env:COLEARN_NANOBOT_TOKEN_ISSUE_SECRET) {
    Write-Host "Note: COLEARN_NANOBOT_TOKEN_ISSUE_SECRET not set. Running in localhost dev mode (no auth)." -ForegroundColor Yellow
    $env:COLEARN_NANOBOT_TOKEN_ISSUE_SECRET = ""
}

$args = @("-m", "nanobot.cli.commands", "gateway", "--config", $ConfigPath, "--workspace", $Workspace)

if ($OpenBrowser) {
    Write-Host "Open browser after gateway binds: http://127.0.0.1:8765"
}

Write-Host "Starting CoLearn v0.2 gateway..."
Write-Host "Config: $ConfigPath"
Write-Host "Workspace: $Workspace"
python @args
