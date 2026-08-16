# LLM coaching protocol

Sharp Shooter uses an optional OpenAI Responses API call to turn locally derived
pose measurements into short educational practice suggestions. OpenAI API text
models are metered rather than free. The default is `gpt-5.4-nano`, selected as
a current low-cost model for a bounded text-generation task; operators can set
`OPENAI_MODEL` to another model available to their account.

## Local privacy reduction

The previous implementation sent up to 40,000 characters of frame-level shoulder,
elbow, and wrist coordinates. The current implementation parses those coordinates
locally and sends only rounded aggregate statistics:

- usable and dropped frame counts;
- left and right elbow-angle summaries;
- wrist height as a fraction of normalized image height;
- horizontal wrist-to-elbow offset as a fraction of normalized image width;
- shoulder-line angle;
- explicit statements about unavailable context.

The API input contains no video name, user identifier, file path, raw coordinate,
or frame-level sequence. A stable HMAC pseudonym is sent separately as the OpenAI
`safety_identifier`, and `store=False` remains enabled.

## Prompt contract

The backend first creates deterministic coaching labels locally. A pose-model
bundle trained by `landmark_classification.py` contains reference bands built
from the 10th and 90th percentiles of correctly labelled good-form recordings.
For a bad-form prediction, the label generator compares interpretable features
with those bands and emits at most two ranked findings. Each finding contains a
code, confidence, measured value, reference band, correction goal, and drill.
These bands describe the training dataset; they are not universal biomechanics
standards. Old model bundles remain compatible, but cannot produce a specific
finding until the pose classifier is retrained.

The prompt instructs the model to treat these labels as the only source of named
problems, strengths, correction goals, and drills. It may use the supplied
aggregate measurements for context, but must never invent a technique issue. It
must also never
infer the shooting hand, camera viewpoint, shot outcome, pain, injury, fatigue,
lower-body motion, or exact release mechanics. Coordinate patterns must be
described as uncertain observations rather than diagnoses or proof of correct or
incorrect form.

Because the summary contains aggregates rather than a continuous timeline, the
prompt also prohibits frame-to-frame, timing, sequencing, and repeatability claims.
It clarifies that `start` and `end` mean the first and last usable rows—not named
shot phases—and warns about the shoulder-angle wrap boundary at -90/+90 degrees.
Ranges and standard deviations cannot be labelled as motion instability or used
to justify corrective drills when the timing and shot phases are unavailable.
The model must self-check for these failure modes before returning its answer,
and it should prefer guidance for capturing better continuous evidence when the
available aggregates cannot support a correction.

The user-facing response is always in English and has exactly two sections:

1. Main Findings
2. How to Improve

`How to Improve` contains most of the response. Internal label codes, JSON field
names, generic classifier flags, status values, and severity values are removed
before the API call and prohibited in the response. Data quality and safety rules
still constrain the analysis internally, but they are not rendered as separate
user-facing sections. The model may explain no more than two findings and their
associated low-risk drills, must cite label evidence, and must stay under 180
words. If fewer than five usable frames remain after local validation, it must
request a better recording instead of providing technique conclusions.

## Configuration

```dotenv
OPENAI_API_KEY=your-openai-api-key
OPENAI_MODEL=gpt-5.4-nano
OPENAI_REASONING_EFFORT=low
SAFETY_IDENTIFIER_SALT=replace-with-a-long-random-secret
```

`OPENAI_REASONING_EFFORT` accepts `none`, `low`, `medium`, `high`, or `xhigh`.
Changing the model or prompt should be evaluated on a fixed set of privacy-safe
summaries before release, checking factual grounding, unsupported claims, action
quality, response length, latency, and token cost.
