#!/usr/bin/env python3
"""Download the fonts used by the pixel-perfect preview.

Run at Docker build time (and manually when developing) so the repository does
not have to carry ~4.5 MB of binary assets. Every file is verified against its
expected size *and* git blob SHA-1 before it is accepted, so a moved tag, a
truncated download or a tampered mirror is rejected rather than silently
producing a subtly wrong preview.

Usage::

    python scripts/fetch_assets.py            # download what is missing
    python scripts/fetch_assets.py --check    # verify only, download nothing
    python scripts/fetch_assets.py --force    # re-download everything
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.error
import urllib.request
from pathlib import Path

# The same files the integration ships in
# custom_components/open_epaper_link/imagegen/assets, pinned to the revision the
# renderer was written against.
SOURCE_REVISION = "f28c21761365181cfaf203030678f1c29433baf3"
SOURCE_BASE = (
    "https://raw.githubusercontent.com/OpenEPaperLink/Home_Assistant_Integration/"
    f"{SOURCE_REVISION}/custom_components/open_epaper_link/imagegen/assets"
)

ASSETS_DIR = Path(__file__).resolve().parents[1] / "app" / "assets"

# name -> (size in bytes, git blob SHA-1)
ASSETS: dict[str, tuple[int, str]] = {
    "ppb.ttf": (153944, "00559eeb290fb8036f10633ff0640447d827b27c"),
    "rbm.ttf": (168644, "ac0f908b9c9c73da558b45d65cc5c6094874d3e8"),
    "materialdesignicons-webfont.ttf": (
        1279992,
        "b00c684d3ef14be87f0badd2eecc88babc70fea0",
    ),
    "materialdesignicons-webfont_meta.json": (
        3164954,
        "b1f439079270016fb50502ba531736f4cae20790",
    ),
}


def git_blob_sha1(data: bytes) -> str:
    """The SHA-1 git reports for a blob, i.e. over `blob <size>\\0<content>`."""
    header = f"blob {len(data)}\0".encode()
    return hashlib.sha1(header + data).hexdigest()


def verify(path: Path, size: int, sha: str) -> tuple[bool, str]:
    """Check a file against its expected size and hash."""
    if not path.exists():
        return False, "missing"
    data = path.read_bytes()
    if len(data) != size:
        return False, f"size {len(data)} != {size}"
    actual = git_blob_sha1(data)
    if actual != sha:
        return False, f"sha1 {actual} != {sha}"
    return True, "ok"


def download(name: str, expected_size: int, expected_sha: str, *, force: bool) -> bool:
    target = ASSETS_DIR / name

    if not force:
        ok, reason = verify(target, expected_size, expected_sha)
        if ok:
            print(f"  ok       {name} (already present)")
            return True
        if target.exists():
            print(f"  stale    {name}: {reason}")

    url = f"{SOURCE_BASE}/{name}"
    print(f"  fetch    {name} <- {url}")
    try:
        with urllib.request.urlopen(url, timeout=120) as response:  # noqa: S310
            data = response.read()
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"  FAILED   {name}: {exc}")
        return False

    if len(data) != expected_size:
        print(f"  FAILED   {name}: downloaded {len(data)} bytes, expected {expected_size}")
        return False

    actual_sha = git_blob_sha1(data)
    if actual_sha != expected_sha:
        print(f"  FAILED   {name}: sha1 {actual_sha}, expected {expected_sha}")
        return False

    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    print(f"  saved    {name} ({len(data)} bytes)")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify existing files without downloading",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="re-download even when a verified file is present",
    )
    args = parser.parse_args()

    print(f"Assets directory: {ASSETS_DIR}")
    failures: list[str] = []

    for name, (size, sha) in ASSETS.items():
        if args.check:
            ok, reason = verify(ASSETS_DIR / name, size, sha)
            print(f"  {'ok      ' if ok else 'MISSING '} {name}: {reason}")
        else:
            ok = download(name, size, sha, force=args.force)
        if not ok:
            failures.append(name)

    if failures:
        print(f"\n{len(failures)} asset(s) could not be prepared: {', '.join(failures)}")
        return 1

    print("\nAll assets verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
