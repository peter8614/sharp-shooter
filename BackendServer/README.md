# Sharp Shooter backend

## Setup

Use Python 3.11 or 3.12 in a fresh virtual environment. Do not reuse the checked-in
`.venv`; its NumPy version is incompatible with MediaPipe.

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

## Analyze one video

Run commands from the `BackendServer` folder:

```powershell
.venv\Scripts\python main.py shot\Irvine_good.mp4 --device cpu
```

The run writes landmarks, ball trajectory, extracted frames, and an annotated AVI
under `output/<video-name>/`. To add a labeled example to the two datasets:

```powershell
.venv\Scripts\python main.py shot\Irvine_good.mp4 --form-label 1 --arc-label 1
```

Use `--arm L` for a left-handed shooter. CUDA users can pass `--device 0`.

## Train classifiers

Each dataset needs at least five labeled recordings in every class so the fixed
five-fold repeated evaluation can place every class in every validation fold.

```powershell
.venv\Scripts\python landmark_classification.py
.venv\Scripts\python trajectory_classification.py
```

Each command performs five-fold, ten-repeat stratified cross-validation before
refitting the deployable model on all labeled recordings. Aggregate Markdown and
JSON reports plus confusion-matrix CSV files are written to `reports/`. The pose
report highlights bad-form recall and the complementary false-good rate. See
[`docs/model-evaluation.md`](../docs/model-evaluation.md) for the full protocol.

Pose training also stores good-form reference bands for interpretable elbow-angle
and wrist-height features. The inference service uses them to turn a bad-form
prediction into at most two evidence-backed coaching labels. Retrain the pose
model after upgrading an older bundle so these specific labels are available.

The pose model is stored at `data/landmark_data/basketball_shot_model.pkl`, and
the trajectory model is stored at `data/trajectory_data/trajectory_model.pkl`.
The API loads these versioned bundles automatically; until they are available,
the corresponding classification result is reported as `unavailable`.

## LLM coaching

OpenAI API usage is metered; there is no free API text model. The backend uses
`gpt-5.4-nano` as its low-cost default and allows operators to override it with
`OPENAI_MODEL`. Before an API request, raw frame landmarks are reduced locally
to anonymous aggregate angles, offsets, tracking quality, and known limitations.
The LLM receives locally generated coaching labels and may only explain their
named findings, correction goals, and drills; it is not allowed to invent a
posture problem from raw statistics. User-facing coaching is English-only and
contains `Main Findings` plus an action-focused `How to Improve` section. Internal
label codes and redundant generic classifier flags are removed before the request.
Configure `OPENAI_REASONING_EFFORT` as needed. The full prompt and privacy
contract are documented in
[`docs/llm-coaching.md`](../docs/llm-coaching.md).

## Tests

```powershell
.venv\Scripts\python -m unittest discover -s tests -v
```
