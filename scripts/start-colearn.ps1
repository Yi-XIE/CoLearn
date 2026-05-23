param(
    [string]$ConfigPath = "D:\Colearn-nightly\.colearn\nanobot-v0.2-slim.config.json",
    [string]$Workspace = "D:\Colearn-nightly\.colearn\nanobot-workspace",
    [int]$Port = 8001,
    [switch]$OpenBrowser
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$nanobotRoot = Join-Path $repoRoot "third_party\nanobot-0.2.0\nanobot-0.2.0"

if (!(Test-Path $ConfigPath)) {
    throw "Config not found: $ConfigPath"
}

if (!(Test-Path $Workspace)) {
    New-Item -ItemType Directory -Path $Workspace -Force | Out-Null
}

$env:PYTHONPATH = "$repoRoot;$nanobotRoot"
$env:COLEARN_REPO_ROOT = $repoRoot
$env:COLEARN_STATE_ROOT = Join-Path $repoRoot ".colearn\state"
$env:COLEARN_NANOBOT_WORKSPACE = $Workspace

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

Write-Host "Starting CoLearn (unified server)..."
Write-Host "  Config: $ConfigPath"
Write-Host "  Workspace: $Workspace"
Write-Host "  Port: $Port"

if ($OpenBrowser) {
    Write-Host "  Open browser: http://127.0.0.1:5173"
}

python -m colearn.server --port $Port --config $ConfigPath --workspace $Workspace
