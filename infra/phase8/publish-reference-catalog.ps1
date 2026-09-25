param(
    [Parameter(Mandatory = $true)][ValidatePattern('^\d{12}$')][string]$ExpectedAccountId,
    [Parameter(Mandatory = $true)][string]$DataDir,
    [Parameter(Mandatory = $true)][string]$VideoDir,
    [string]$Region = 'us-east-1',
    [switch]$ConfirmDisplayRights,
    [switch]$RepairCurrentReferences
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if (-not $ConfirmDisplayRights) {
    throw 'Explicitly confirm permission to display these reference clips in the Dev App.'
}
$resolvedDataDir = (Resolve-Path -LiteralPath $DataDir).Path
$resolvedVideoDir = (Resolve-Path -LiteralPath $VideoDir).Path
if (-not (Test-Path -LiteralPath $resolvedDataDir -PathType Container) -or
    -not (Test-Path -LiteralPath $resolvedVideoDir -PathType Container)) {
    throw 'DataDir and VideoDir must both be existing directories.'
}
$identity = aws sts get-caller-identity --region $Region --output json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or $identity.Account -ne $ExpectedAccountId) {
    throw 'AWS identity does not match ExpectedAccountId; no clip was uploaded.'
}
$bucket = (aws cloudformation describe-stacks --region $Region --stack-name sharp-shooter-dev `
    --query "Stacks[0].Outputs[?OutputKey=='UploadBucketName'].OutputValue | [0]" --output text).Trim()
if ($LASTEXITCODE -ne 0 -or $bucket -ne "sharp-shooter-dev-uploads-$ExpectedAccountId-$Region") {
    throw 'Dev upload bucket could not be verified.'
}
$backendRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..\BackendServer')).Path
$outputDir = Join-Path $backendRoot '.phase10-reference-build'
Push-Location $backendRoot
try {
    python -m scripts.build_reference_catalog --data-dir $resolvedDataDir --video-dir $resolvedVideoDir --output-dir $outputDir
    if ($LASTEXITCODE -ne 0) { throw 'Reference validation failed; nothing was uploaded.' }
} finally {
    Pop-Location
}
$plan = Get-Content -LiteralPath (Join-Path $outputDir 'upload-plan.json') -Raw | ConvertFrom-Json
foreach ($item in $plan.uploads) {
    if ($item.key -notmatch '^references/videos/[a-z0-9-]{1,80}\.mp4$' -or
        -not (Test-Path -LiteralPath $item.source -PathType Leaf)) {
        throw 'Invalid upload plan; stopped before publishing the catalog.'
    }
    aws s3 cp $item.source "s3://$bucket/$($item.key)" --region $Region `
        --content-type video/mp4 --sse AES256 --no-progress
    if ($LASTEXITCODE -ne 0) { throw "Reference clip upload failed: $($item.key)" }
}
if ($RepairCurrentReferences) {
    # Existing completed jobs retain their original reference key. Replace the
    # private object at that legacy key with its phone-compatible rendition.
    $currentCatalogKey = (aws lambda get-function-configuration --region $Region `
        --function-name sharp-shooter-dev-inference `
        --query 'Environment.Variables.NBA_REFERENCE_CATALOG_KEY' --output text).Trim()
    if ($LASTEXITCODE -ne 0 -or $currentCatalogKey -notmatch '^references/catalog-[0-9a-f]{64}\.json$') {
        throw 'Current Worker catalog key could not be verified.'
    }
    $previousCatalogPath = Join-Path $outputDir 'previous-catalog.json'
    aws s3 cp "s3://$bucket/$currentCatalogKey" $previousCatalogPath --region $Region --no-progress
    if ($LASTEXITCODE -ne 0) { throw 'Unable to read current reference catalog.' }
    $previousCatalog = Get-Content -LiteralPath $previousCatalogPath -Raw | ConvertFrom-Json
    foreach ($entry in $previousCatalog.entries) {
        if ($entry.id -notmatch '^[a-z0-9-]{1,80}$' -or
            $entry.video_key -notmatch '^references/videos/[a-z0-9-]{1,80}\.mp4$' -or
            -not $entry.video_key.StartsWith("references/videos/$($entry.id)-")) {
            throw 'Invalid legacy reference key; stopped repair.'
        }
        $replacement = $plan.uploads | Where-Object { $_.id -eq $entry.id } | Select-Object -First 1
        if ($null -eq $replacement -or $entry.video_key -eq $replacement.key) { continue }
        aws s3 cp $replacement.source "s3://$bucket/$($entry.video_key)" --region $Region `
            --content-type video/mp4 --sse AES256 --no-progress
        if ($LASTEXITCODE -ne 0) { throw "Legacy reference repair failed: $($entry.id)" }
    }
}
if ($plan.catalog_key -notmatch '^references/catalog-[0-9a-f]{64}\.json$') {
    throw 'Invalid catalog key.'
}
# Publish the index last: the worker never observes a partially uploaded set.
aws s3 cp $plan.catalog_file "s3://$bucket/$($plan.catalog_key)" --region $Region `
    --content-type application/json --sse AES256 --no-progress
if ($LASTEXITCODE -ne 0) { throw 'Reference catalog upload failed.' }
Write-Output "ReferenceCatalogKey=$($plan.catalog_key)"
Write-Output "PublishedClips=$($plan.uploads.Count)"
Write-Output "SkippedWithoutVideo=$($plan.skipped_without_video.Count)"
