# Phase 8: minimal AWS Dev deployment

Phase 8 uses two small CloudFormation stacks in `us-east-1`:

```text
sharp-shooter-dev-bootstrap
  private ECR repository + short-lived deployment-artifact bucket + AWS Budget

sharp-shooter-dev
  private S3 uploads -> Standard SQS -> Lambda inference -> DynamoDB
                              |              |
                              v              v
                             DLQ       CloudWatch Logs
  IAM-protected HTTP API -> create/get job Lambda -> DynamoDB
```

There is no VPC, NAT Gateway, load balancer, always-on server, Redis, RDS,
Kubernetes, Firebase migration, or Flutter change. The subsequent real AWS
video, failure, lease, DLQ, cold/warm, and cost results are in the
[Phase 9 validation report](aws-phase9-validation.md).

The Dev Worker emits `WORKER_DIAGNOSTIC` CloudWatch lines when the configurable
`WorkerDiagnosticsEnabled` template parameter is `1`; set it to `0` to disable
sampling. Diagnostics are outside `predict_video()` and do not alter results.
The Dev IAM API is not a mobile production endpoint.

## Deploy

Use AWS CLI v2, Docker Desktop, and PowerShell 7. Sign in with `aws login` (or
`aws login --remote` if the browser callback fails). Do not create root access
keys. Confirm the intended account ID with `aws sts get-caller-identity`.

The validated local `sharp-shooter-inference:phase7` image must still be present
for the initial deployment; the deployment script compares its image ID with
the Phase 7 report before pushing it to private ECR. For a code-only SQS event
handling update, the overlay Dockerfile retains the tested base image exactly:

```powershell
cd BackendServer
docker buildx build --platform linux/amd64 --provenance=false `
  -f ../infra/phase8/Dockerfile.worker-overlay `
  -t sharp-shooter-inference:phase8 --load .
cd ..
./infra/phase8/deploy-dev.ps1 -ExpectedAccountId '<account ID>' `
  -BudgetEmail '<alert email>' -LocalImageTag sharp-shooter-inference:phase8
```

The script verifies the architecture and production handler. The image contains private classifier bundles, so
never publish it to a public registry or CI artifact. API handlers are packaged
separately as a small ZIP with only `aws_backend/*.py` and `job_api/*.py`.

```powershell
./infra/phase8/deploy-dev.ps1 `
  -ExpectedAccountId '<12-digit AWS account ID>' `
  -Region us-east-1 `
  -BudgetEmail '<account-alert-email>' `
  -MonthlyBudgetUsd 10
```

The script validates both templates, deploys the bootstrap stack, pushes the
image under a unique tag and uses its immutable digest, uploads the API ZIP,
then deploys the main stack. It refuses to run if the account ID differs or if
the SQS visibility/lease/worker-timeout relationships are unsafe. All names
are Dev-specific. Re-running creates a new ECR image and updates the stacks;
the ECR lifecycle keeps only the latest three images. AWS costs can still accrue
while the environment is idle from ECR/S3/log storage and any AWS service usage.

## Initial limits and security

| Setting | Initial value |
| --- | --- |
| Worker architecture / memory / timeout | x86_64 / 3008 MiB / 300 s |
| Worker reserved concurrency | 2 |
| SQS batch size / mapping max concurrency | 1 / 2 |
| Processing lease / attempts | 360 s / 3 |
| SQS visibility / DLQ redrive | 1800 s / 5 receives |
| Video expiration / deployment ZIP expiration | 2 days / 7 days |
| Analyzed result video expiration | 7 days (configurable) |
| Worker ephemeral storage for annotated-video conversion | 2048 MiB (configurable) |
| CloudWatch Lambda log retention | 14 days |
| Monthly budget | configurable; initial 10 USD, email at 50% and 100% |

The SQS visibility timeout is six times the Lambda timeout, following AWS
guidance. The lease outlasts the worker timeout and expires before the message
becomes visible again. `ReportBatchItemFailures` is enabled, and DynamoDB lease
ownership remains the idempotency authority. A CloudWatch alarm marks visible
DLQ messages; operators should inspect and explicitly redrive after fixing the
cause. The alarm has no email action, so it must be monitored in CloudWatch.
The first attempt at 3072 MiB Worker memory was rejected by this account's
current Lambda limit; the Dev stack was cleanly rolled back and recreated with
3008 MiB. Raising memory in this account requires checking its effective quota.

Both S3 buckets block public access, enforce TLS, use S3-managed encryption,
and have lifecycle rules. SQS uses SQS-managed encryption. Lambda roles are
limited to their required upload keys, table actions, queue, and log groups.
The original `POST /jobs` and `GET /jobs/{job_id}` routes use `AWS_IAM` and
the API has 2 requests/second stage throttling. Phase 10 added separate
Cognito JWT `/app/jobs` routes for the Flutter Dev client; see
[`aws-phase10-cognito.md`](aws-phase10-cognito.md). Neither route family
allows anonymous job creation.
The optional Phase 10 media path stores annotated MP4 files under `results/`
and a versioned private NBA catalog under `references/`. Enable it explicitly
with `-ResultVideoEnabled 1 -ReferenceCatalogKey '<catalog key>'` during
deployment, and preserve those arguments on later stack updates. The
`-ResultsRetentionDays` parameter controls automatic removal of job videos;
reference clips do not use that expiry rule. Publish the catalog with
`publish-reference-catalog.ps1` only after confirming App display rights.
The publishing script transcodes reference clips to H.264 for mobile playback.
For a catalog-only change, `update-reference-catalog.ps1` preserves every
other CloudFormation parameter and avoids pushing a new Worker image.
`AWS_REGION` is supplied automatically by Lambda, and the lightweight ZIP APIs
use the Python runtime's bundled boto3. A runtime upgrade should verify that
SDK compatibility remains intact.

An AWS Budget sends alerts but is **not** a spending cap or automatic shutdown.
The budget here covers account-wide cost, not only these stacks. Inspect the
budget, ECR repository, CloudFormation stacks, and DLQ after deployment.

## API and operational checks

The stack outputs an HTTPS API base URL. Signed callers with `execute-api:Invoke`
permission may use `POST /jobs` and `GET /jobs/{job_id}`; the upload URL is a
short-lived HTTPS S3 presigned PUT URL. A caller must send the signed
`Content-Type`. IAM authorization intentionally makes an unauthenticated curl
request return 403. The old Flask `/get_prediction` route remains untouched.

Read-only checks:

```powershell
aws cloudformation describe-stacks --region us-east-1 --stack-name sharp-shooter-dev
aws lambda list-event-source-mappings --region us-east-1 --function-name sharp-shooter-dev-inference
aws sqs get-queue-attributes --region us-east-1 --queue-url '<DLQ URL>' --attribute-names ApproximateNumberOfMessages
```

Do not manually delete the stacks without first reviewing bucket contents and
the ECR image: stack deletion can fail for nonempty S3 buckets, and any
unmanaged copies of the image may remain billable. Phase 9 should verify
presigned upload, S3 notification, worker inference, DynamoDB completion,
failure retries/DLQ, and real AWS timings/cost before any Flutter integration.
