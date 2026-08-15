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

The pose model is stored at `data/landmark_data/basketball_shot_model.pkl`, and
the trajectory model is stored at `data/trajectory_data/trajectory_model.pkl`.
The API loads these versioned bundles automatically; until they are available,
the corresponding classification result is reported as `unavailable`.

## Tests

```powershell
.venv\Scripts\python -m unittest discover -s tests -v
```
