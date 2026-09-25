param(
    [Parameter(Mandatory = $true)][ValidatePattern('^\d{12}$')][string]$ExpectedAccountId,
    [Parameter(Mandatory = $true)][ValidatePattern('^references/catalog-[0-9a-f]{64}\.json$')][string]$CatalogKey,
    [string]$Region = 'us-east-1'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$identity = aws sts get-caller-identity --region $Region --output json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or $identity.Account -ne $ExpectedAccountId) {
    throw 'AWS identity does not match ExpectedAccountId.'
}
$stackName = 'sharp-shooter-dev'
$bucket = "sharp-shooter-dev-uploads-$ExpectedAccountId-$Region"
$catalogSize = aws s3api head-object --bucket $bucket --key $CatalogKey --region $Region `
    --query ContentLength --output text
if ($LASTEXITCODE -ne 0 -or [long]$catalogSize -le 0) {
    throw 'Reference catalog is missing from the expected Dev bucket.'
}
$stack = aws cloudformation describe-stacks --stack-name $stackName --region $Region --output json |
    ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or $stack.Stacks[0].StackStatus -ne 'UPDATE_COMPLETE') {
    throw 'Dev stack is not ready for a parameter-only update.'
}
$parameters = @()
$foundCatalogParameter = $false
foreach ($entry in $stack.Stacks[0].Parameters) {
    if ($entry.ParameterKey -eq 'ReferenceCatalogKey') {
        $foundCatalogParameter = $true
        $parameters += "ParameterKey=ReferenceCatalogKey,ParameterValue=$CatalogKey"
    } else {
        $parameters += "ParameterKey=$($entry.ParameterKey),UsePreviousValue=true"
    }
}
if (-not $foundCatalogParameter) { throw 'ReferenceCatalogKey parameter is missing.' }
aws cloudformation update-stack --stack-name $stackName --region $Region `
    --use-previous-template --parameters $parameters --capabilities CAPABILITY_NAMED_IAM
if ($LASTEXITCODE -ne 0) { throw 'Dev stack update failed to start.' }
aws cloudformation wait stack-update-complete --stack-name $stackName --region $Region
if ($LASTEXITCODE -ne 0) { throw 'Dev stack update did not complete.' }
Write-Output "ReferenceCatalogKey=$CatalogKey"
Write-Output 'StackStatus=UPDATE_COMPLETE'
