"""Verify every model asset embedded in the Lambda worker image."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


DEFAULT_MANIFEST = Path(__file__).resolve().parents[1] / "lambda-model-manifest.json"


class AssetVerificationError(RuntimeError):
    """Raised when an expected inference asset is absent or has changed."""


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(path: Path) -> dict:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AssetVerificationError(f"Unable to read model manifest: {path}") from error
    if manifest.get("schema_version") != 1 or not isinstance(
        manifest.get("assets"), list
    ):
        raise AssetVerificationError("Unsupported model manifest")
    return manifest


def verify_assets(root: Path, manifest_path: Path = DEFAULT_MANIFEST) -> list[dict]:
    root = root.expanduser().resolve()
    manifest = load_manifest(manifest_path.expanduser().resolve())
    verified = []
    for asset in manifest["assets"]:
        try:
            relative_path = Path(asset["path"])
            expected_size = int(asset["size_bytes"])
            expected_sha256 = str(asset["sha256"]).lower()
        except (KeyError, TypeError, ValueError) as error:
            raise AssetVerificationError("Malformed model asset entry") from error
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise AssetVerificationError(f"Unsafe model asset path: {relative_path}")
        model_path = (root / relative_path).resolve()
        try:
            model_path.relative_to(root)
        except ValueError as error:
            raise AssetVerificationError(f"Unsafe model asset path: {relative_path}") from error
        if not model_path.is_file():
            raise AssetVerificationError(f"Missing model asset: {relative_path}")
        actual_size = model_path.stat().st_size
        if actual_size != expected_size:
            raise AssetVerificationError(
                f"Size mismatch for {relative_path}: {actual_size} != {expected_size}"
            )
        actual_sha256 = sha256_file(model_path)
        if actual_sha256 != expected_sha256:
            raise AssetVerificationError(f"SHA-256 mismatch for {relative_path}")
        verified.append(
            {
                "path": relative_path.as_posix(),
                "size_bytes": actual_size,
                "sha256": actual_sha256,
            }
        )
    return verified


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_MANIFEST.parent)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        verified = verify_assets(args.root, args.manifest)
    except AssetVerificationError as error:
        print(json.dumps({"verified": False, "error": str(error)}))
        return 1
    print(json.dumps({"verified": True, "assets": verified}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
