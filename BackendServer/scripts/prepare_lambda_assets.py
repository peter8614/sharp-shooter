"""Stage ignored private model bundles into a Lambda Docker build context."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

try:
    from .verify_lambda_assets import (
        DEFAULT_MANIFEST,
        AssetVerificationError,
        load_manifest,
        verify_assets,
    )
except ImportError:  # Direct script execution.
    from verify_lambda_assets import (
        DEFAULT_MANIFEST,
        AssetVerificationError,
        load_manifest,
        verify_assets,
    )


TARGET_BACKEND = Path(__file__).resolve().parents[1]


def prepare_assets(source_backend: Path, target_backend: Path, *, force: bool) -> None:
    source_backend = source_backend.expanduser().resolve()
    target_backend = target_backend.expanduser().resolve()
    manifest = load_manifest(DEFAULT_MANIFEST)
    for asset in manifest["assets"]:
        relative_path = Path(asset["path"])
        target = target_backend / relative_path
        if target.is_file() and not force:
            continue
        source = source_backend / relative_path
        if not source.is_file():
            raise AssetVerificationError(f"Source model asset is missing: {source}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    verify_assets(target_backend, DEFAULT_MANIFEST)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-backend", type=Path, required=True)
    parser.add_argument("--target-backend", type=Path, default=TARGET_BACKEND)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        prepare_assets(
            args.source_backend,
            args.target_backend,
            force=args.force,
        )
    except AssetVerificationError as error:
        print(f"Lambda assets are not ready: {error}")
        return 1
    print("Lambda model assets are staged and verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
