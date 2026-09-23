# Phase 9: real AWS Dev end-to-end validation

Validated on 2026-09-23 in the existing `us-east-1` Dev stack. No Flutter code,
prediction logic, model weights, or legacy Flask route changed. The Dev API is
still IAM-protected and is **not** a mobile production endpoint.
The diagnostic Worker image used the Phase 7-tested base image and private ECR
digest `sha256:e00ba16bbace17e452bdc13f33ee4a75e6b38b7f5a5b0d86c4ddf01fa22c9479`;
only `inference_worker.py` was overlaid.

## Outcome

The real path `POST /jobs` → HTTPS presigned `PUT` → private S3 → Standard SQS →
Lambda → DynamoDB → `GET /jobs/{id}` completed for two public demo videos.
The returned classifications and coaching categories matched the Phase 7 Linux
baseline. Duplicate messages did not repeat inference. Bad videos reached a
safe `failed` state after three attempts, and a failure notification moved to
the actual Dev DLQ after five receives. A real 10-second Lambda timeout left a
job in `processing`; an active lease blocked a duplicate, and a worker reclaimed
the deliberately expired lease and completed on attempt two.

This is Dev backend acceptance, not mobile release approval. Exact numeric
prediction parity did **not** hold, and longer unseen videos still need a
duration/size policy before Phase 10 cutover.

## Real video measurements

All uploads returned HTTP 200, create returned 201, and final GET returned
`completed`. Client time starts immediately after the video upload finishes.
Lambda `REPORT` duration excludes API and queue delay. Memory allocation was
3008 MiB, timeout 300 seconds, and `/tmp` allocation 512 MiB.

| Video / invocation | Client upload→completed | Lambda duration | Billed duration | Max memory | YOLO cached before | Sampled `/tmp` peak |
| --- | ---: | ---: | ---: | ---: | --- | ---: |
| Demo 1, initial cold path | 195.70 s | 182.51 s | 191.55 s | 970 MiB | not instrumented | not instrumented |
| Demo 3, initial separate runtime | 69.38 s | 54.66 s | 54.66 s | 953 MiB | not instrumented | not instrumented |
| Demo 3, instrumented cold path | 137.16 s | 123.94 s | 123.94 s | 955 MiB | false | 5.14 MiB |
| Demo 3, same-runtime warm path | 40.14 s | 37.72 s | 37.72 s | 1005 MiB | true | 4.95 MiB |

The last two invocations had the same Worker `runtime_id` and CloudWatch log
stream. Their `invocation_number` values were 1 and 2, and YOLO was cached
after the first job and before the second. The 0.5-second `/tmp` sampler is an
observed peak, not a guaranteed exact peak; it reported a 525-MiB mounted
capacity and returned to about 0.06 MiB used after each job. The first cold
path had `Init Duration: 9034.61 ms`. Another cold stream emitted
`INIT_REPORT ... Status: timeout` at about 10 seconds before its successful
invocation; this is a cold-start reliability/performance signal to retain in
future measurements, not a failed job.

Demo 1 returned `good` form and `bad` trajectory, as did Phase 7. Demo 3 did
the same. JSON schema and coaching codes remained compatible. Exact numerical
parity was not achieved: Demo 1's form confidence was 0.845 versus 0.849 in
Phase 7, with 34 versus 40 shot frames and 8 versus 11 release frames. Demo 3's
form confidence was 0.883 versus 0.884, with 6 versus 7 shot frames. The cause
has not been isolated; do not promise bit-for-bit consistency across Lambda
and the local Linux container. No inference algorithm was changed in Phase 9.

## Failure and idempotency checks

| Check | Observed result |
| --- | --- |
| API input errors | Signed unsupported MIME request returned 415; signed lookup of a missing job returned 404. Neither exposed internal details. |
| Repeat S3 notification for a completed job | SQS message acknowledged; DynamoDB stayed `completed`, `attempt_count=1`, and `updated_at` did not change. |
| Invalid MP4 bytes | Worker returned partial batch failure; attempts 1 and 2 returned to `pending`; attempt 3 set `failed`. GET returned only `Video processing failed.` |
| Actual queue redrive | With the event mapping paused, manual receives 1–5 accelerated the real source queue's configured redrive; the notification appeared in the Dev DLQ. This avoids waiting roughly two hours and does not claim five full Lambda invocations occurred. |
| DLQ alarm | `sharp-shooter-dev-inference-dlq-visible` entered `ALARM`. It has no email action; an operator must inspect it. The test message remains visible in the DLQ for inspection. |
| Real Lambda timeout | A temporary 10-second timeout produced `REPORT ... Status: timeout`, leaving `processing`, attempt 1. The original 300-second setting was restored. |
| Active lease | A duplicate call completed in about 0.23 seconds without claiming or incrementing the attempt count. |
| Expired lease | Expiration was advanced in DynamoDB rather than waiting 360 seconds. A concurrent SQS Worker won the reclaim and completed the video at attempt 2. The test runner now waits for the final owner rather than assuming its direct invocation wins. |
| Stale worker token | Conditional ownership is covered by backend unit tests. A separate live old-token completion race was not forced; the timed-out invocation had already exited. |

Test control exposed AWS propagation races: an event source mapping can report
`Disabled` while a previous poller still processes a message, and an S3
notification configuration change is not an instantaneous isolation barrier.
Two early bad-video test jobs therefore had an extra automatic attempt. Both
eventually reached `failed`; the controlled DLQ test then passed. The recovery
script waits for the mapping to quiesce and restores configuration in `finally`.
Run it only in Dev without other users. The one orphan `pending` record created
when the local Anaconda TLS stack failed before S3 upload was conditionally
deleted after confirming the S3 object did not exist.

## Cost and operations

Using the [AWS Lambda on-demand price](https://aws.amazon.com/lambda/pricing/)
of about USD 0.0000166667 per GB-second for the relevant first pricing tier,
the 3008-MiB Worker compute component is approximately:

| Example | Estimated Worker compute cost |
| --- | ---: |
| Demo 1 initial cold | USD 0.00938 |
| Demo 3 instrumented cold | USD 0.00607 |
| Demo 3 same-runtime warm | USD 0.00185 |

These are *not* invoice amounts: the Lambda free tier or account credits may
offset them, while API Gateway, S3, SQS, DynamoDB, logs, data transfer, and ECR
storage can add charges. [SQS](https://aws.amazon.com/sqs/pricing/) and
[HTTP API Gateway](https://aws.amazon.com/api-gateway/pricing/) charge by
requests at this scale. The account-wide USD 10 monthly Budget remained
configured; its contemporaneous actual spend read 0.00 USD and forecast 0.027
USD, both subject to billing-report delay. Budget alerts are not a hard cap.
ECR reported about 728 MB of compressed image data for each digest, with
potential shared layers; the local unpacked image was about 2.95 GiB.

After fault injection, CloudFormation returned `UPDATE_COMPLETE`, Lambda was
active with a 300-second timeout, S3 notification pointed to the Dev queue,
and the SQS event mapping was `Enabled`. The DLQ alarm intentionally remains
`ALARM` while the test message remains visible. Do not silently redrive it:
the associated bad video would fail again.
At final inspection the source queue had zero visible messages and two
in-flight notifications from the earlier invalid-video probes. They are test
artifacts that should naturally retry and eventually reach the DLQ; inspect
them before any manual redrive. No production traffic was used.

## Reproduce

Run from the repository root after `aws login`, with the intended account ID
supplied explicitly. The end-to-end script needs Python, AWS CLI, `curl.exe`,
and a trusted CA bundle (`certifi` is used when available on Anaconda/Windows).
It never prints the presigned URL or AWS credentials.

```powershell
python BackendServer/scripts/run_phase9_e2e.py `
  --expected-account-id '<12-digit Dev account ID>' `
  --api-base '<Dev stack ApiUrl>' `
  --video docs/demos/sharp-shooter-demo-3.mp4 `
  --phase7-report BackendServer/reports/phase-7-container-validation.json
```

`BackendServer/scripts/run_phase9_recovery.py` provides the controlled
`invalid` and `timeout` scenarios. It temporarily changes Dev-only S3
notifications, SQS event mapping, and/or Lambda timeout, then restores them.
Review its arguments and verify the stack and queue are idle before running.
Do not run it against production traffic.

## Phase 10 handoff

- Keep the old `/get_prediction` fallback while the mobile asynchronous flow
  is tested. The current Dev `AWS_IAM` API cannot be called anonymously from
  Flutter; choose end-user authorization before mobile cutover.
- Polling and client timeout must tolerate several minutes, especially for
  cold starts and larger videos. Establish upload length/size limits or a
  longer-running compute option based on further real workloads.
- Exact frame counts and confidence numbers may drift. Decide which semantic
  and numeric tolerance the product requires; do not silently assume local
  Phase 7 JSON is bit-for-bit identical to AWS results.
- Monitor the DLQ and CloudWatch logs. The DLQ alarm has no email action yet.
