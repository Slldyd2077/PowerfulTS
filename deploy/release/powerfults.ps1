param([ValidateSet('start', 'stop', 'restart', 'logs', 'status', 'init')][string]$Action = 'start')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:POWERFULTS_VERSION = (Get-Content -LiteralPath '.release-version' -Raw).Trim()
$createdConfig = $false
if (-not (Test-Path -LiteralPath 'backend.env')) {
    Copy-Item -LiteralPath 'backend.env.example' -Destination 'backend.env'
    Write-Host 'Created backend.env. Set TS3 / TSMusicBot connection settings, then restart.'
    $createdConfig = $true
}
New-Item -ItemType Directory -Path 'data' -Force | Out-Null
if ($Action -eq 'init') { exit 0 }
if ($createdConfig -and $Action -in @('start', 'restart')) {
    Write-Host 'Edit backend.env, then run start again.'
    exit 0
}
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Install Docker Desktop with Compose v2 first (see README.md).'
}
function Test-DockerCommand {
    # Windows PowerShell turns redirected native stderr into an error record.
    # Probe failures are expected (especially on a fresh install without images).
    $ErrorActionPreference = 'Continue'
    & docker @args *> $null
    return ($LASTEXITCODE -eq 0)
}
if (-not (Test-DockerCommand info)) { throw 'Start Docker Desktop with Linux containers first.' }
if (-not (Test-DockerCommand compose version)) { throw 'Docker Compose v2.20+ is required.' }
function Invoke-Compose {
    & docker compose --project-directory $PSScriptRoot -f compose.yml @args
    if ($LASTEXITCODE -ne 0) { throw "Docker Compose failed ($LASTEXITCODE). Inspect logs with .\powerfults.ps1 logs." }
}
function Start-PowerfulTS {
    if (Test-Path -LiteralPath 'images.tar') {
        $machine = (& docker info --format '{{.Architecture}}').Trim()
        if ($LASTEXITCODE -ne 0) { throw 'Could not detect Docker CPU architecture.' }
        if ($machine -in @('x86_64', 'amd64')) { $machine = 'amd64' }
        if ($machine -in @('aarch64', 'arm64')) { $machine = 'arm64' }
        $expected = (Get-Content -LiteralPath '.release-arch' -Raw).Trim()
        if ($machine -ne $expected) { throw "This archive is $expected, but Docker is $machine. Download the matching CPU archive." }
        if (-not (Test-DockerCommand image inspect "powerfults-backend:$env:POWERFULTS_VERSION" "powerfults-frontend:$env:POWERFULTS_VERSION")) {
            & docker load --input images.tar
            if ($LASTEXITCODE -ne 0) { throw 'Docker image import failed.' }
        }
        Invoke-Compose up -d --no-build --pull never --wait --wait-timeout 180
    } else {
        Invoke-Compose up -d --build --wait --wait-timeout 180
    }
    $port = if ($env:POWERFULTS_PORT) { $env:POWERFULTS_PORT } else { '8080' }
    Write-Host "PowerfulTS is ready: http://localhost:$port"
}
switch ($Action) {
    start { Start-PowerfulTS }
    stop { Invoke-Compose down }
    restart { Invoke-Compose down; Start-PowerfulTS }
    logs { Invoke-Compose logs -f --tail 100 }
    status { Invoke-Compose ps }
}
