# Privacy guidance

Basketball videos and pose landmarks can identify a person and may reveal age,
location, appearance, physical characteristics, or surroundings. Treat them as
sensitive data even when a dataset does not contain names.

## Repository policy

The published repository must not contain raw videos, extracted frames, personal
landmark CSV files, private documents, credentials, or local environment files.
The `.gitignore` file blocks common forms of these artifacts, but it is not a
substitute for reviewing every commit.

## Data collection

- Obtain informed consent before recording or processing a person.
- Obtain guardian consent where required for minors.
- Explain the purpose, retention period, and intended audience.
- Avoid recording faces, addresses, school names, license plates, and bystanders
  when they are not required for the analysis.
- Use non-identifying sample IDs instead of real names in filenames and labels.

## Storage and sharing

- Store private datasets outside the Git repository.
- Encrypt sensitive datasets at rest and in transit.
- Limit access to people who need the data for the stated purpose.
- Do not publish model artifacts without considering whether they may memorize or
  reveal information from a small training set.
- Delete raw and derived data after the retention period expires.

## Before every push

Review the staged file list and scan for secrets, personal paths, email addresses,
documents, videos, archives, generated outputs, and model metadata. If sensitive
data is committed, removing it in a later commit is not sufficient: rotate exposed
credentials and clean the repository history before publishing again.
