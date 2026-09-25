# Phase 10 Dev App API and mobile integration

The existing `POST /jobs` and `GET /jobs/{job_id}` operations retain
`AWS_IAM` authorization for developers and operators. The same HTTP API also
offers `POST /app/jobs` and `GET /app/jobs/{job_id}` with a Cognito User Pool
JWT authorizer. These App routes require the `openid` scope, so callers use an
access token rather than an ID token. The JWT issuer and audience are fixed to
the stack's User Pool and public mobile client. The mobile client has no IAM
credentials, AWS access keys, or Cognito client secret.

The two route families share the existing create/get Lambda functions and
presigned S3 PUT implementation. App-created DynamoDB jobs store the Cognito
`sub` claim as `owner_sub`; App GET returns 404 for another user's job and for
older IAM jobs without an owner. IAM routes retain their original behavior.
Worker/SQS processing and the model pipeline are unchanged. The worker now
persists the existing annotated-video output as H.264 MP4 in private S3 and
compares the existing pose-variance output with a private, versioned NBA
reference catalog. These are application-layer additions, not classifier or
trajectory-model changes.

The Dev pool explicitly uses the lower-cost Cognito Lite tier and classic
Hosted UI, and defaults to administrator-created users only. Do not enable
`AllowCognitoSelfSignup` without deciding registration, abuse protection,
account deletion, and user support. Existing Firebase users are **not**
automatically migrated into Cognito.

## Current Dev deployment (updated 2026-09-24)

CloudFormation `sharp-shooter-dev` completed its update in `us-east-1`.
The public App configuration is:

```text
APP_API_URL=https://ekmafbj0fe.execute-api.us-east-1.amazonaws.com/app
COGNITO_CLIENT_ID=7qvino9jus9fbvcptll4uketbb
COGNITO_ISSUER=https://cognito-idp.us-east-1.amazonaws.com/us-east-1_hrlId2sMb
```

These identifiers are public app configuration, **not** IAM credentials or
client secrets. The original IAM API remains at
`https://ekmafbj0fe.execute-api.us-east-1.amazonaws.com`.
An anonymous App GET returned 401; an anonymous IAM GET returned 403. Live
route inspection initially confirmed two IAM routes and two JWT job routes with `openid`
scope; the owner-checked video route was added later. OIDC discovery returned the expected authorization and token endpoints.
The User Pool reports `LITE` and administrator-only creation. A Dev invitation
was sent to the confirmed tester email and receipt was confirmed; no password
or token was collected by the implementation process.

## Mobile configuration

Run `flutter pub get` in `mobile/` before the first Android or iOS build; the
generated native plugin registration is required for AppAuth. Do not use
`--no-pub` on a fresh checkout.

Set these public build values together when testing the App API:

```bash
flutter run \
  --dart-define=APP_API_URL=https://<api-id>.execute-api.us-east-1.amazonaws.com/app \
  --dart-define=COGNITO_CLIENT_ID=<public-app-client-id> \
  --dart-define=COGNITO_ISSUER=https://cognito-idp.us-east-1.amazonaws.com/<user-pool-id>
```

The redirect URI is
`com.codingminds.shotrater://oauth/callback` on Android and iOS. The native
AppAuth integration uses authorization code with PKCE, and the refresh token
is stored using platform secure storage. If all three values are absent, the
older Flask/Firebase client remains available. A partial App configuration is
rejected at startup. `BACKEND_URL` remains required by the existing iOS
release wrapper for that legacy fallback; the IAM Dev URL must never be used
as a mobile backend URL.

The current Dev sign-out clears the locally stored tokens only. It does not
revoke the Cognito refresh token or clear the hosted browser session. Do not
use shared devices for this test; add server-side revocation and hosted logout
before a public release.

App mode currently exposes Analyze and a minimal Dev Account page. It does
not claim that legacy history, account deletion, or Firebase accounts have
been migrated. Results are shown immediately after
`completed` in the Analyze screen. Uploads use the returned HTTPS presigned
URL and matching `Content-Type`, without an Authorization header; status GET
uses the Cognito access token. Polling is every three seconds with a 12-minute
UI timeout and a retry-status option. The old `/get_prediction` code path is
kept as a separately configured fallback.

### Result videos and NBA reference comparison

Completed App jobs can expose `processed_video_available` and
`reference_video_available` in `GET /app/jobs/{job_id}`. Raw S3 keys are never
returned by that endpoint. The App requests a short-lived playback URL via
`GET /app/jobs/{job_id}/videos/processed` or `/reference`. Both routes require
the Cognito access token and verify the job's `owner_sub` before issuing a
five-minute private-S3 URL. Flutter fetches a new URL when playback begins or
is retried; it does not persist the URL. An IAM-created job has no App owner
and cannot be opened through these routes.

The analyzed video is retained in S3 for seven days. The NBA catalog and
reference clips are private Dev objects under `references/`; their lifecycle
is separate from the seven-day job results. The catalog contains only entries
with both a clip and variance data. The App shows the nearest catalog entry,
player name, and an **experimental similarity score among available clips**.
This is a normalized pose-variance heuristic, not a validated probability or
claim that the user's mechanics match a professional athlete. Missing or
invalid reference data results in an explicit unavailable state, while the
primary shot analysis can still complete.

To refresh the Dev reference catalog, use
`infra/phase8/publish-reference-catalog.ps1` with the local NBA clips and
variance-data directories and `-ConfirmDisplayRights`. The script checks the
expected AWS account, transcodes clips to phone-compatible H.264, uploads them
under content-addressed keys, and writes the catalog last. Install
`imageio-ffmpeg==0.6.0` in the local Python environment before publishing.
Use `-RepairCurrentReferences` when already-completed jobs point at the older
non-H.264 clips; this replaces only those private video objects and leaves
the original local files untouched. Set the resulting `ReferenceCatalogKey`
with `infra/phase8/update-reference-catalog.ps1` or the full Dev deployment.
Do not publish these files in Git, public S3, ECR layers, or CI artifacts.

## Deployment and verification

### Optional asynchronous AI coaching

Create a **Standard SecureString** named
`/sharp-shooter/dev/openai-api-key` in AWS Systems Manager Parameter Store,
`us-east-1`, before enabling coaching. Enter the key only in the AWS console;
do not put it in Git, a command argument, Flutter, or a Lambda environment
variable. The coaching Lambda alone receives `ssm:GetParameter` for this
specific path and decrypts the value at invocation time. Use the default
AWS-managed `aws/ssm` KMS key; a customer-managed key would require a
separately scoped `kms:Decrypt` grant. The key is never
returned through the job API.

Build and push a fresh x86_64 inference image containing the new
`coaching_worker` and OpenAI dependency. Use
`docker buildx build --platform linux/amd64 --provenance=false --sbom=false --load`
so ECR receives a single-image manifest accepted by Lambda, not an OCI index.
Deploy the Dev stack using
`-CoachingEnabled 1`, preserving `-ResultVideoEnabled 1` and the current
`-ReferenceCatalogKey`; the deploy script checks that the parameter exists
and is a SecureString without reading its value. The default remains disabled.

When enabled, inference writes a private, aggregate-only pose summary and
enqueues `{ "job_id": "..." }` to a separate Standard SQS queue. The existing
job reaches `completed` independently. A dedicated coaching Lambda claims
`queued` or expired `processing` work with a DynamoDB conditional lease and
worker token, then writes `coaching_status=ready` plus English text. API
responses omit the private summary. Failed attempts return a partial-batch
failure to SQS; after three application attempts the public coaching state is
`unavailable`, while SQS continues redelivery up to `maxReceiveCount=5` and
then retains the message in `sharp-shooter-dev-coaching-dlq` for 14 days.
Check the DLQ and CloudWatch logs; do not assume failed coaching is lost.

The App displays classification and evidence-based guidance immediately,
polling separately for up to two minutes for AI coaching. If coaching times
out or fails, the completed analysis and media remain available. Validate a
real Dev upload, duplicate queue delivery, failure/DLQ, and Android/iOS
rendering before calling this cloud feature verified. OpenAI requests are
metered and the large shared container may add a cold-start cost; measure
before broad release.

Use `infra/phase8/deploy-dev.ps1` with the built media-enabled worker image,
the confirmed Dev account ID, `-ResultVideoEnabled 1`, and the versioned
`-ReferenceCatalogKey` returned by the publishing script. The script verifies
account identity before updating the stack. Its API ZIP includes the new
video-link handler. Omitting the media parameters on a later deployment turns
off new video generation/reference comparison, so preserve them explicitly.

Before giving the App to testers:

1. Verify CloudFormation `UPDATE_COMPLETE` and confirm the two IAM routes
   still require IAM signatures.
2. Confirm unauthenticated and ID-token requests to `/app/jobs` and the video
   route fail, while a valid Cognito access token succeeds.
3. Create two administrator-managed test users and check that user B cannot
   read user A's job by ID.
4. Upload a real video using the presigned URL, poll to `completed`, compare
   result categories with Phase 9, and play both videos on a real phone.
5. Check invalid video, network interruption, expired URL, cold-start
   timeout, DLQ, and sign-out behavior on a real phone.

This is a Dev integration, not a release approval. The legacy backend still
owns old users and history. A production cutover needs an account migration or
explicit new-account policy, account deletion on Cognito/S3/DynamoDB, end-user
abuse and upload-size controls, native iOS testing, and the Phase 11 release
checks.
Do not infer real-phone or iOS playback from unit tests. A fresh Android build
must be installed and the invited Dev account must perform a real
upload/poll/playback check before release.

### Phase 10 coaching Dev check (2026-09-24)

The Dev stack reached `UPDATE_COMPLETE` with `CoachingEnabled=1`, the prior
video output setting and reference catalog preserved, and the new ECR image
using a Lambda-compatible single-image manifest. Two IAM-signed uploads of
the repository's public `sharp-shooter-demo-3.mp4` each completed in about
198 seconds; coaching reached `ready` separately. The final English response
used standalone `Main Findings` and `How to Improve` headings, described an
overall trajectory concern without inventing a specific cause, and rendered
0.875 model confidence as 88%. The public GET response omitted
`coaching_summary`. A conditional requeue of the second test job validated
the final prompt without rerunning inference. The coaching source queue and
DLQ were both empty at final check. This is cloud-path validation, not a
real-phone or iOS UI sign-off. An Android debug APK with the Dev App API,
Cognito issuer, and English result UI was built locally; install that fresh
APK before phone verification.

The 2026-09-24 IAM-signed Dev end-to-end check uploaded
`docs/demos/sharp-shooter-demo-3.mp4` and reached `completed` in 172.61 seconds
after upload. The public result reported both video availability flags,
Kevin Durant as the closest catalog reference, and a 27.21% experimental
score. Both S3 objects were present as encrypted `video/mp4` files; the
results lifecycle rule expires them after seven days. Anonymous access to
the App video route returned 401, and the original unsigned IAM GET returned
403. This verifies cloud processing and storage, but not an authenticated
phone playback session.

On 2026-09-24 the tester reported corrupted NBA playback and a bottom
overflow on a portrait clip. The original Kevin Durant clip decoded cleanly
on desktop but used MPEG-4 Simple Profile (`mp4v`). All 55 private reference
clips were converted to H.264 Baseline/`yuv420p`; legacy S3 keys were repaired
so completed jobs can replay without re-analysis. The Worker now uses the new
catalog, and the Android player's layout is bounded by available screen
height. The specific legacy Kevin Durant object was byte-verified against
the converted local file. A new APK and real-phone replay are still required
to confirm the visual fix on the tester's device.
