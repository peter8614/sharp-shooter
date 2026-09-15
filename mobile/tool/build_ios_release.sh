#!/usr/bin/env bash
set -euo pipefail

release_backend_url="${BACKEND_URL:-}"
dart run tool/validate_release_configuration.dart "$release_backend_url"

flutter build ipa --release \
  --dart-define="BACKEND_URL=$release_backend_url" \
  "$@"
