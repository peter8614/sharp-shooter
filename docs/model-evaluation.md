# Model evaluation protocol

Sharp Shooter evaluates the pose and ball-trajectory classifiers with repeated,
stratified cross-validation at the recording level. One complete recording is
always one sample; frames from the same video are never divided between train
and validation folds.

## Fixed report

Every training run generates the following metrics:

- Accuracy
- Balanced accuracy
- Macro precision
- Macro recall
- Macro F1
- Confusion matrix
- Recall for every class
- 95% confidence intervals for all scalar metrics

The default evaluation uses five folds and ten repeats. Each recording receives
exactly one out-of-fold prediction in each repeat. Confusion-matrix counts
therefore aggregate ten predictions per recording and must not be mistaken for
ten times as many independent videos.

Confidence intervals use a stratified, recording-level percentile bootstrap with
2,000 resamples. Recordings are resampled within each class so every bootstrap
sample retains the original class counts. When a recording is selected, all
repeated out-of-fold predictions for it are selected together. This keeps the
uncertainty calculation from treating correlated predictions as independent.

## Safety focus for pose classification

The pose label contract is:

- `0`: `bad_form`
- `1`: `good_form`

The primary safety-oriented metric is `bad_form` recall:

```text
bad-form recall = bad forms predicted as bad / all actual bad forms
```

The report also publishes the complementary false-good rate:

```text
false-good rate = bad forms predicted as good / all actual bad forms
                = 1 - bad-form recall
```

A high overall accuracy cannot compensate for low bad-form recall. Model
selection and release decisions should inspect this value first because a false
good result gives the user inappropriate reassurance about an unsafe or
ineffective shooting motion.

## Generated artifacts

Training writes three privacy-safe aggregate artifacts per classifier under
`BackendServer/reports/`:

- `*-evaluation.md`: human-readable report
- `*-evaluation.json`: machine-readable metrics and metadata
- `*-evaluation-confusion-matrix.csv`: confusion-matrix values

Raw recordings, landmark files, private indexes, and serialized models remain
excluded from Git.

## Interpretation limits

The bootstrap interval measures uncertainty within the available labeled
recordings. It does not prove performance for new shooters, camera positions,
gyms, or recording devices. As the dataset grows, evaluation should use groups
for shooter and recording session, followed by a final independent external test
set that is used only once for release validation.
