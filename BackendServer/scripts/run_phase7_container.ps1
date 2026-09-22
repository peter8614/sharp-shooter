[CmdletBinding()]
param(
    [string]$Image = "sharp-shooter-inference:phase7",
    [int]$Port = 9000,
    [string]$SourceBackend = ""
)

$ErrorActionPreference = "Stop"
$backendRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$repositoryRoot = (Resolve-Path (Join-Path $backendRoot "..")).Path
$workspaceRoot = Split-Path $repositoryRoot -Parent
if (-not $SourceBackend) {
    $SourceBackend = Join-Path $workspaceRoot "github-release\sharp-shooter\BackendServer"
}
$SourceBackend = (Resolve-Path $SourceBackend).Path
$demoRoot = (Resolve-Path (Join-Path $repositoryRoot "docs\demos")).Path
$report = Join-Path $backendRoot "reports\phase-7-container-validation.json"
$containerName = "sharp-shooter-phase7-$([guid]::NewGuid().ToString('N').Substring(0, 10))"

$dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
if ($dockerCommand) {
    $dockerCommand = $dockerCommand.Source
} else {
    $dockerCommand = "C:\Program Files\Docker\Docker\resources\bin\docker.exe"
}
if (-not (Test-Path -LiteralPath $dockerCommand)) {
    throw "Docker is required. Install Docker Desktop with Linux containers and retry."
}

Push-Location $backendRoot
try {
    & $dockerCommand version | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "The Docker engine is not running." }

    python scripts/prepare_lambda_assets.py --source-backend $SourceBackend
    if ($LASTEXITCODE -ne 0) { throw "Model asset preparation failed." }

    & $dockerCommand buildx build --platform linux/amd64 --provenance=false `
        --file Dockerfile.lambda-worker --tag $Image --load .
    if ($LASTEXITCODE -ne 0) { throw "Lambda worker image build failed." }

    $metadata = (& $dockerCommand image inspect $Image `
        --format "{{.Size}}|{{.Id}}|{{.Architecture}}/{{.Os}}") -split "\|"
    if ($LASTEXITCODE -ne 0 -or $metadata.Count -ne 3) {
        throw "Unable to inspect the Lambda worker image."
    }

    & $dockerCommand run --rm --detach --name $containerName `
        --platform linux/amd64 --memory 6g --cpus 4 `
        --publish "${Port}:8080" `
        --volume "${demoRoot}:/tmp/videos:ro" `
        --env SHARP_SHOOTER_LOCAL_SMOKE=1 `
        $Image lambda_container_smoke.lambda_handler | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "Unable to start the Lambda worker image." }

    Start-Sleep -Seconds 3
    python scripts/test_lambda_container.py `
        --endpoint "http://localhost:${Port}/2015-03-31/functions/function/invocations" `
        --host-video-root $demoRoot `
        --image-size-bytes $metadata[0] `
        --image-id $metadata[1] `
        --image-platform $metadata[2] `
        --report $report
    if ($LASTEXITCODE -ne 0) { throw "Phase 7 container validation failed." }
}
finally {
    & $dockerCommand logs --tail 30 $containerName 2>$null | Out-Host
    & $dockerCommand stop $containerName 2>$null | Out-Null
    Pop-Location
}

Write-Host "Phase 7 validation passed. Report: $report"
