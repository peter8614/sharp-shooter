param(
    [Parameter(Mandatory = $true)][ValidatePattern('^\d{12}$')][string]$ExpectedAccountId,
    [string]$Region = 'us-east-1',
    [string]$BudgetEmail,
    [string]$ExistingInferenceImageUri,
    [string]$LocalImageTag = 'sharp-shooter-inference:phase7',
    [int]$MonthlyBudgetUsd = 10,
    [int]$WorkerTimeoutSeconds = 300,
    [int]$WorkerMemoryMb = 3008,
    [int]$WorkerEphemeralStorageMb = 2048,
    [int]$ResultsRetentionDays = 7,
    [ValidatePattern('^$|^references/catalog-[0-9a-f]{64}\.json$')][string]$ReferenceCatalogKey = '',
    [ValidateSet('0', '1')][string]$ResultVideoEnabled = '0',
    [ValidateSet('0', '1')][string]$CoachingEnabled = '0',
    [string]$OpenAiApiKeyParameterName = '/sharp-shooter/dev/openai-api-key',
    [int]$CoachingLeaseSeconds = 90,
    [int]$MaxCoachingAttempts = 3,
    [string]$OpenAiModel = 'gpt-5.4-nano',
    [int]$QueueVisibilitySeconds = 1800,
    [int]$ProcessingLeaseSeconds = 360,
    [int]$MaxProcessingAttempts = 3,
    [ValidateSet('0', '1')][string]$WorkerDiagnosticsEnabled = '1',
    [ValidateSet('true', 'false')][string]$AllowCognitoSelfSignup = 'false'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if ($QueueVisibilitySeconds -lt (6 * $WorkerTimeoutSeconds)) {
    throw 'SQS visibility must be at least six times the Lambda timeout.'
}
if ($ProcessingLeaseSeconds -le $WorkerTimeoutSeconds -or $ProcessingLeaseSeconds -ge $QueueVisibilitySeconds) {
    throw 'Processing lease must be longer than Lambda timeout and shorter than SQS visibility.'
}
if ($MonthlyBudgetUsd -lt 1 -or $MaxProcessingAttempts -lt 1) {
    throw 'Budget and attempt limit must be positive.'
}
if ($CoachingLeaseSeconds -le 30 -or $CoachingLeaseSeconds -ge 180 -or $MaxCoachingAttempts -lt 1) {
    throw 'Coaching lease must be between its Lambda timeout (30s) and SQS visibility (180s).'
}
if ($CoachingEnabled -eq '1') {
    $parameterType = (aws ssm describe-parameters --region $Region --parameter-filters "Key=Name,Values=$OpenAiApiKeyParameterName" --query 'Parameters[0].Type' --output text).Trim()
    if ($LASTEXITCODE -ne 0 -or $parameterType -ne 'SecureString') { throw 'Coaching requires an existing SecureString parameter; no key value is read by deployment.' }
}

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$backendRoot = Join-Path $repoRoot 'BackendServer'
$identity = aws sts get-caller-identity --region $Region --output json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or $identity.Account -ne $ExpectedAccountId) {
    throw 'AWS identity does not match ExpectedAccountId; no resource was changed.'
}
if (-not $BudgetEmail) {
    $BudgetEmail = (aws account get-contact-information --region $Region --query 'ContactInformation.EmailAddress' --output text).Trim()
    if ($LASTEXITCODE -ne 0 -or $BudgetEmail -notmatch '^[^@ ]+@[^@ ]+\.[^@ ]+$') {
        throw 'Could not read the AWS account contact email. Supply -BudgetEmail explicitly.'
    }
}

if (-not $ExistingInferenceImageUri) {
    $imageDetails = (docker image inspect $LocalImageTag --format '{{.Id}} {{.Architecture}} {{json .Config.Cmd}}').Trim()
    if ($LASTEXITCODE -ne 0 -or $imageDetails -notmatch '^sha256:[0-9a-f]{64} amd64 \["inference_worker.lambda_handler"\]$') {
        throw 'The local Lambda image is missing, not amd64, or has the wrong production handler.'
    }
    if ($LocalImageTag -eq 'sharp-shooter-inference:phase7') {
        $report = Get-Content -LiteralPath (Join-Path $backendRoot 'reports\phase-7-container-validation.json') -Raw | ConvertFrom-Json
        if ($imageDetails.Split(' ')[0] -ne $report.image.id) {
            throw 'The local Phase 7 image does not match its validation report.'
        }
    }
}

$bootstrapStack = 'sharp-shooter-dev-bootstrap'
$appStack = 'sharp-shooter-dev'
aws cloudformation validate-template --region $Region --template-body "file://$(Join-Path $PSScriptRoot 'bootstrap.yaml')" --query 'Description' --output text
if ($LASTEXITCODE -ne 0) { throw 'Bootstrap template validation failed.' }
aws cloudformation validate-template --region $Region --template-body "file://$(Join-Path $PSScriptRoot 'dev.yaml')" --query 'Description' --output text
if ($LASTEXITCODE -ne 0) { throw 'Dev template validation failed.' }

aws cloudformation deploy --region $Region --stack-name $bootstrapStack `
    --template-file (Join-Path $PSScriptRoot 'bootstrap.yaml') `
    --parameter-overrides "BudgetEmail=$BudgetEmail" "MonthlyBudgetUsd=$MonthlyBudgetUsd" `
    --tags Project=sharp-shooter Environment=dev `
    --no-fail-on-empty-changeset
if ($LASTEXITCODE -ne 0) { throw 'Bootstrap deployment failed; inspect CloudFormation events.' }

$bootstrapOutputs = aws cloudformation describe-stacks --region $Region --stack-name $bootstrapStack --query 'Stacks[0].Outputs' --output json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw 'Could not read bootstrap outputs.' }
$outputMap = @{}
foreach ($entry in $bootstrapOutputs) { $outputMap[$entry.OutputKey] = $entry.OutputValue }
$repositoryUri = $outputMap['RepositoryUri']
$artifactBucket = $outputMap['ArtifactBucketName']
if (-not $repositoryUri -or -not $artifactBucket) { throw 'Bootstrap outputs are incomplete.' }

if ($ExistingInferenceImageUri) {
    if (-not $ExistingInferenceImageUri.StartsWith("${repositoryUri}@sha256:", [StringComparison]::Ordinal) -or
        $ExistingInferenceImageUri -notmatch '@sha256:[0-9a-f]{64}$') {
        throw 'ExistingInferenceImageUri must be a digest in this account and Dev ECR repository.'
    }
    $imageDigest = $ExistingInferenceImageUri.Split('@')[1]
    $verifiedDigest = (aws ecr describe-images --region $Region --repository-name 'sharp-shooter/inference-dev' --image-ids "imageDigest=$imageDigest" --query 'imageDetails[0].imageDigest' --output text).Trim()
    if ($LASTEXITCODE -ne 0 -or $verifiedDigest -ne $imageDigest) { throw 'Existing ECR image digest was not found.' }
    $manifestType = (aws ecr describe-images --region $Region --repository-name 'sharp-shooter/inference-dev' --image-ids "imageDigest=$imageDigest" --query 'imageDetails[0].imageManifestMediaType' --output text).Trim()
    if ($LASTEXITCODE -ne 0 -or $manifestType -notin @('application/vnd.oci.image.manifest.v1+json', 'application/vnd.docker.distribution.manifest.v2+json')) {
        throw 'The ECR image is not a Lambda-compatible single-architecture manifest.'
    }
    $imageUri = $ExistingInferenceImageUri
} else {
    $registry = $repositoryUri.Split('/')[0]
    aws ecr get-login-password --region $Region | docker login --username AWS --password-stdin $registry
    if ($LASTEXITCODE -ne 0) { throw 'Private ECR login failed.' }
    $imageTag = 'phase8-{0}-{1}' -f (git -C $repoRoot rev-parse --short HEAD).Trim(), (Get-Date).ToUniversalTime().ToString('yyyyMMddHHmmss')
    $taggedImage = "${repositoryUri}:${imageTag}"
    docker tag $LocalImageTag $taggedImage
    if ($LASTEXITCODE -ne 0) { throw 'Could not tag the validated Lambda image.' }
    docker push $taggedImage
    if ($LASTEXITCODE -ne 0) { throw 'Image push failed.' }
    $imageDigest = (aws ecr describe-images --region $Region --repository-name 'sharp-shooter/inference-dev' --image-ids "imageTag=$imageTag" --query 'imageDetails[0].imageDigest' --output text).Trim()
    if ($LASTEXITCODE -ne 0 -or $imageDigest -notmatch '^sha256:[0-9a-f]{64}$') { throw 'Could not verify the ECR image digest.' }
    $manifestType = (aws ecr describe-images --region $Region --repository-name 'sharp-shooter/inference-dev' --image-ids "imageTag=$imageTag" --query 'imageDetails[0].imageManifestMediaType' --output text).Trim()
    if ($LASTEXITCODE -ne 0 -or $manifestType -notin @('application/vnd.oci.image.manifest.v1+json', 'application/vnd.docker.distribution.manifest.v2+json')) {
        throw 'The pushed image is not Lambda-compatible. Rebuild with --provenance=false --sbom=false.'
    }
    $imageUri = "${repositoryUri}@${imageDigest}"
}

$stagingRoot = Join-Path $backendRoot '.phase8-build'
$stagingDir = Join-Path $stagingRoot ([guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $stagingDir | Out-Null
try {
    foreach ($package in @('aws_backend', 'job_api')) {
        $packageDestination = Join-Path $stagingDir $package
        New-Item -ItemType Directory -Path $packageDestination | Out-Null
        Get-ChildItem -LiteralPath (Join-Path $backendRoot $package) -Filter '*.py' -File | ForEach-Object {
            Copy-Item -LiteralPath $_.FullName -Destination $packageDestination
        }
    }
    $zipPath = Join-Path $stagingRoot 'job-api.zip'
    Compress-Archive -Path (Join-Path $stagingDir '*') -DestinationPath $zipPath -Force
    $zipSha = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $artifactKey = "phase8/job-api-$zipSha.zip"
    aws s3 cp $zipPath "s3://$artifactBucket/$artifactKey" --region $Region --sse AES256 --no-progress
    if ($LASTEXITCODE -ne 0) { throw 'Could not upload the API package.' }
} finally {
    $resolvedStagingRoot = [IO.Path]::GetFullPath($stagingRoot)
    $resolvedStagingDir = [IO.Path]::GetFullPath($stagingDir)
    if ($resolvedStagingDir.StartsWith($resolvedStagingRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        Remove-Item -LiteralPath $stagingDir -Recurse -Force
    }
    if (Test-Path -LiteralPath $zipPath) {
        $resolvedZip = [IO.Path]::GetFullPath($zipPath)
        if ($resolvedZip.StartsWith($resolvedStagingRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
            Remove-Item -LiteralPath $zipPath -Force
        }
    }
}

aws cloudformation deploy --region $Region --stack-name $appStack `
    --template-file (Join-Path $PSScriptRoot 'dev.yaml') `
    --capabilities CAPABILITY_NAMED_IAM `
    --parameter-overrides "InferenceImageUri=$imageUri" "ApiCodeBucket=$artifactBucket" "ApiCodeKey=$artifactKey" `
    "WorkerTimeoutSeconds=$WorkerTimeoutSeconds" "WorkerMemoryMb=$WorkerMemoryMb" `
    "WorkerEphemeralStorageMb=$WorkerEphemeralStorageMb" "ResultsRetentionDays=$ResultsRetentionDays" `
    "ReferenceCatalogKey=$ReferenceCatalogKey" "ResultVideoEnabled=$ResultVideoEnabled" `
    "CoachingEnabled=$CoachingEnabled" "OpenAiApiKeyParameterName=$OpenAiApiKeyParameterName" `
    "CoachingLeaseSeconds=$CoachingLeaseSeconds" "MaxCoachingAttempts=$MaxCoachingAttempts" "OpenAiModel=$OpenAiModel" `
    "QueueVisibilitySeconds=$QueueVisibilitySeconds" "ProcessingLeaseSeconds=$ProcessingLeaseSeconds" `
    "MaxProcessingAttempts=$MaxProcessingAttempts" "WorkerDiagnosticsEnabled=$WorkerDiagnosticsEnabled" `
    "AllowCognitoSelfSignup=$AllowCognitoSelfSignup" `
    --tags Project=sharp-shooter Environment=dev `
    --no-fail-on-empty-changeset
if ($LASTEXITCODE -ne 0) { throw 'Dev deployment failed; inspect CloudFormation events.' }

aws cloudformation describe-stacks --region $Region --stack-name $appStack `
    --query 'Stacks[0].{Status:StackStatus,Outputs:Outputs}' --output json
if ($LASTEXITCODE -ne 0) { throw 'Could not read final stack status.' }
