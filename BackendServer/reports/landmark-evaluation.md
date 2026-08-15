# Model evaluation report

Repeated stratified 5-fold cross-validation with 10 repeats on 36 recordings.
Confidence intervals use stratified recording-level percentile bootstrap resampling.

## Aggregate metrics

| Metric | Value (95% CI) |
| --- | ---: |
| Accuracy | 81.7% (71.4%–90.6%) |
| Balanced accuracy | 66.4% (51.7%–82.0%) |
| Macro precision | 70.2% (51.9%–90.5%) |
| Macro recall | 66.4% (51.7%–82.0%) |
| Macro F1 | 67.9% (51.1%–83.2%) |

## Per-class recall

| Class | Recall (95% CI) |
| --- | ---: |
| bad_form | 41.4% (14.3%–71.4%) |
| good_form | 91.4% (81.4%–99.3%) |

## Safety-focused class

Priority class: **bad_form**.
Recall: **41.4% (14.3%–71.4%)**.
False-good rate (priority examples predicted as non-priority): **58.6% (28.6%–85.7%)**.

## Confusion matrix

Rows are actual classes and columns are predicted classes.

| Actual \ Predicted | bad_form | good_form |
| --- | ---: | ---: |
| bad_form | 29 | 41 |
| good_form | 25 | 265 |

> Repeated-fold predictions and bootstrap intervals describe uncertainty inside this dataset;
> they do not replace an independent shooter/session test set.
