# Start the FinAlly container. Pass -Build to force an image rebuild.
param([switch]$Build, [switch]$NoBrowser)

$Image = "finally"
$Container = "finally"
$Root = Split-Path -Parent $PSScriptRoot
$Url = "http://localhost:8000"

docker image inspect $Image *> $null
if ($Build -or $LASTEXITCODE -ne 0) {
    docker build -t $Image $Root
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

docker rm -f $Container *> $null

$EnvArgs = @()
$EnvFile = Join-Path $Root ".env"
if (Test-Path $EnvFile) { $EnvArgs = @("--env-file", $EnvFile) }

docker run -d --name $Container -v finally-data:/app/db -p 127.0.0.1:8000:8000 @EnvArgs $Image | Out-Null
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "FinAlly is running at $Url"
if (-not $NoBrowser) { Start-Process $Url }
