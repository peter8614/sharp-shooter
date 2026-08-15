# Model evaluation report

Repeated stratified 5-fold cross-validation with 10 repeats on 45 recordings.
Confidence intervals use stratified recording-level percentile bootstrap resampling.

## Aggregate metrics

| Metric | Value (95% CI) |
| --- | ---: |
| Accuracy | 95.6% (88.9%–100.0%) |
| Balanced accuracy | 90.0% (75.0%–100.0%) |
| Macro precision | 97.3% (93.8%–100.0%) |
| Macro recall | 90.0% (75.0%–100.0%) |
| Macro F1 | 93.1% (80.0%–100.0%) |

## Per-class recall

| Class | Recall (95% CI) |
| --- | ---: |
| bad_trajectory | 80.0% (50.0%–100.0%) |
| good_trajectory | 100.0% (100.0%–100.0%) |

## Safety-focused class

Priority class: **bad_trajectory**.
Recall: **80.0% (50.0%–100.0%)**.
False-good rate (priority examples predicted as non-priority): **20.0% (0.0%–50.0%)**.

## Confusion matrix

Rows are actual classes and columns are predicted classes.

| Actual \ Predicted | bad_trajectory | good_trajectory |
| --- | ---: | ---: |
| bad_trajectory | 80 | 20 |
| good_trajectory | 0 | 350 |

> Repeated-fold predictions and bootstrap intervals describe uncertainty inside this dataset;
> they do not replace an independent shooter/session test set.
