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

Each dataset needs at least six labeled videos, both classes, and at least two
videos in each class.

```powershell
.venv\Scripts\python landmark_classification.py
.venv\Scripts\python trajectory_classification.py
```

The trained models are stored in `models/*.joblib`.
Once those files exist, `main.py` automatically includes `form_prediction` and
`arc_prediction` in its output. Before training, both values are reported as `None`.

## Tests

```powershell
.venv\Scripts\python -m unittest discover -s tests -v
```
