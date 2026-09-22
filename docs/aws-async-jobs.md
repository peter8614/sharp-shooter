# AWS asynchronous job backend

This phase adds Lambda-compatible application code only. It does not create or
deploy an S3 bucket, DynamoDB table, API Gateway, Lambda function, IAM role, VPC,
or any other AWS resource.

## Request lifecycle

1. `POST /jobs` validates the requested video MIME type, creates a UUID, and
   derives `uploads/<job_id>/input.<extension>` without using the supplied
   filename in the object key.
2. The handler creates a short-lived presigned S3 `PutObject` URL and writes a
   `pending` job to DynamoDB. The URL is returned only after both operations
   succeed.
3. The client uploads directly to the private upload bucket. It must send the
   same `Content-Type` value that was signed.
4. An S3 `ObjectCreated` notification is delivered to a Standard SQS processing
   queue. S3 does not invoke the inference function directly.
5. The SQS event-source mapping invokes `inference_worker.lambda_handler` with
   batch size `1`. The worker unwraps the SQS message body, parses the embedded
   S3 notification, and verifies that its bucket and key match the stored job.
6. The worker atomically acquires a time-limited processing lease, downloads into
   a job-specific directory under the operating-system temporary root (`/tmp` on
   Lambda), and calls the existing `core.inference.predict_video()` function.
7. Successful inference is stored as `completed`. A normal exception releases
   the job to `pending` and returns an SQS partial-batch failure until the attempt
   budget is exhausted. A timeout, OOM, or process crash leaves the lease behind;
   a later SQS delivery can reclaim it after expiration.

The existing Flask `/get_prediction` route and Flutter client remain unchanged.

## Lambda handlers

- Create job: `job_api.create_job.lambda_handler`
- Read job: `job_api.get_job.lambda_handler`
- SQS inference worker: `inference_worker.lambda_handler`

The HTTP handlers return API Gateway/Lambda Function URL response objects with a
JSON body.

### Create job

Request:

```json
{
  "filename": "shot.mp4",
  "content_type": "video/mp4"
}
```

Success (`201`):

```json
{
  "job_id": "2bdc5274-7189-4d85-b1a6-b4dc727927bb",
  "upload_url": "https://signed-s3-url.example",
  "status": "pending"
}
```

Supported mappings are `video/mp4` to `.mp4`, `video/quicktime` to `.mov`,
`video/x-msvideo` to `.avi`, and `video/x-matroska` to `.mkv`. Unsupported MIME
types return `415`; malformed requests return `400`.

### Read job

`GET /jobs/{job_id}` returns only the public job contract:

```json
{"job_id":"...","status":"pending"}
```

```json
{"job_id":"...","status":"processing"}
```

```json
{"job_id":"...","status":"completed","result":{"success":true}}
```

```json
{"job_id":"...","status":"failed","error":"Video processing failed."}
```

A missing job returns `404`. Bucket names, object keys, timestamps, and internal
exceptions are not returned by the status API.

## DynamoDB schema and state machine

The table uses the string partition key `job_id` and no sort key. A new item is:

```json
{
  "job_id": "uuid",
  "status": "pending",
  "attempt_count": 0,
  "created_at": "ISO-8601 UTC timestamp",
  "updated_at": "ISO-8601 UTC timestamp",
  "s3_bucket": "private-upload-bucket",
  "s3_key": "uploads/<job_id>/input.mp4"
}
```

During processing, the item additionally contains:

```json
{
  "status": "processing",
  "processing_started_at": "ISO-8601 UTC timestamp",
  "lease_expires_at": "ISO-8601 UTC timestamp",
  "attempt_count": 1,
  "worker_token": "unique Lambda invocation token"
}
```

The state machine includes `pending -> processing -> completed`,
`processing -> pending` for a retryable caught exception, and
`processing -> failed` after the configured attempt limit. An expired
`processing` lease can atomically transition to a new `processing` lease.

The claim update succeeds only when the item is `pending`, or when it is
`processing` and `lease_expires_at` is earlier than the claim time. It sets a new
worker token and increments `attempt_count` in the same DynamoDB update. The
attempt-limit condition prevents additional inference once the budget is spent.

Completion, failure, and retry release all require both `status=processing` and
an exact `worker_token` match. A delayed worker therefore cannot overwrite a job
after another delivery has reclaimed its lease. Expired jobs that exhausted the
attempt limit are finalized using a conditional comparison against their stored
token and expired lease.

Completed items add `result`; failed items remove lease ownership and add only
the fixed safe `error`. Prediction floats are converted to `Decimal` before
DynamoDB writes and converted back to JSON numbers when read. Video bytes are
never stored in the table.

## SQS event and DLQ behavior

The worker expects an SQS Lambda event whose `body` is the JSON S3 notification:

```json
{
  "Records": [
    {
      "eventSource": "aws:sqs",
      "messageId": "message-id",
      "body": "{\"Records\":[{\"s3\":{\"bucket\":{\"name\":\"bucket\"},\"object\":{\"key\":\"uploads%2Fjob-id%2Finput.mp4\"}}}]}"
    }
  ]
}
```

Configure a Standard source queue, an event-source mapping with batch size `1`,
and `ReportBatchItemFailures`. Successful and already-completed jobs are
acknowledged. Active leases, retryable failures, missing/mismatched jobs, and
terminal failures are returned in `batchItemFailures`, so they are not silently
deleted.

Attach a separate DLQ such as `sharp-shooter-inference-dlq` using the source
queue redrive policy. The recommended initial `maxReceiveCount` is `5` with
`MAX_PROCESSING_ATTEMPTS=3`: three processing attempts are available and
terminal messages still receive enough failed deliveries to be moved to the
DLQ. The DLQ retention should exceed the source queue retention. Operators
should alarm on visible DLQ messages and investigate or explicitly redrive them.

The queue visibility timeout must exceed both the Lambda timeout and the
processing lease. `PROCESSING_LEASE_SECONDS` must include a safety margin above
the maximum Lambda runtime; otherwise a live invocation could lose its lease and
a second invocation could start inference concurrently. Token checks still
prevent stale completion, but correct timeout configuration avoids wasted work.

## Configuration

The runtime requires:

```text
AWS_REGION
UPLOAD_BUCKET
JOBS_TABLE
PROCESSING_LEASE_SECONDS
MAX_PROCESSING_ATTEMPTS
```

No AWS access keys belong in source or `.env.example`. Lambda should receive
least-privilege permissions through its execution role. boto3 clients/resources
are lazily created once at module scope and reused by warm invocations.

## Local tests

The AWS tests use mocks and make no network calls:

```powershell
python -m unittest discover -s tests -p "test_aws*.py" -v
python -m unittest discover -s tests -p "test_inference_worker.py" -v
```

Phase 8 defines and deploys the private bucket, table, queues and redrive
policy, S3 event filter, batch-size-one Lambda mapping with partial-batch
responses, IAM-protected API routes, roles, logs, budget, and resource limits.
See [`aws-dev-deployment.md`](aws-dev-deployment.md) for the Dev runbook.
The worker also acknowledges S3's one-off `s3:TestEvent` configuration probe;
malformed and permanently failing upload notifications still retry to the DLQ.
