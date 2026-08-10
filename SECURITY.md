# Security policy

## Reporting a vulnerability

Keep security reports private. Contact the repository owner through GitHub rather
than opening a public issue containing exploit details, credentials, personal data,
or links to private datasets.

Include the affected component, reproduction steps, expected impact, and a minimal
proof of concept that does not expose other people's data.

## Credential handling

- Never commit private keys, passwords, API tokens, cookies, or `.env` files.
- Use environment variables or an external secret manager for local credentials.
- Immediately revoke and rotate any credential that enters Git history.
- Do not load untrusted `.pt`, `.pth`, `.pkl`, or `.joblib` files. These formats may
  execute code during deserialization.

## Model and upload safety

If an upload API is added, enforce file-size limits, validate actual media types,
generate server-side filenames, isolate processing jobs, and never pass user input
through a shell. Treat model checkpoints as executable dependencies and obtain them
only from trusted sources with verified checksums.
