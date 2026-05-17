#!/usr/bin/env python3
"""
generate_checksums.py
=====================

Generate (or verify) a SHA256SUMS file for the PRISM-36K dataset release.

The output is fully compatible with the GNU coreutils ``sha256sum -c`` format,
so any user can verify their download with::

    sha256sum -c SHA256SUMS

Usage
-----
Generate (default mode)::

    python generate_checksums.py --root images/ --output checksums/SHA256SUMS

Verify an existing SHA256SUMS file::

    python generate_checksums.py --verify --root images/ \
                                 --output checksums/SHA256SUMS

Optional flags
--------------
``--include-metadata``
    Also hash files under ``metadata/`` and ``splits/`` (recommended for the
    final release record on Zenodo).

``--workers N``
    Parallel workers for hashing. Defaults to ``os.cpu_count()``.

``--pattern GLOB``
    Glob filter applied to filenames (default: ``*``). Use e.g. ``*.png`` to
    hash only the images.

The script is deterministic: files are sorted by their POSIX-style relative
path before hashing so the resulting ``SHA256SUMS`` file is byte-identical
across runs and across operating systems.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable

# Read in 1 MiB chunks: large enough to amortise syscall overhead, small enough
# to keep memory flat even on enormous files.
CHUNK_SIZE = 1024 * 1024


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------

def sha256_of_file(path: Path) -> str:
    """Return the hex SHA-256 digest of *path*."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK_SIZE), b""):
            h.update(chunk)
    return h.hexdigest()


def _hash_one(args: tuple[Path, Path]) -> tuple[str, str]:
    """Worker function: returns (relative_posix_path, hex_digest)."""
    abs_path, root = args
    rel = abs_path.relative_to(root).as_posix()
    return rel, sha256_of_file(abs_path)


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def collect_files(
    root: Path,
    include_metadata: bool,
    pattern: str,
) -> list[Path]:
    """Return the sorted list of files to hash, relative to *root*'s parent."""
    base = root.parent  # repository root, so paths look like images/foo.png

    targets: list[Path] = []

    # Always include everything under the images root.
    targets.extend(p for p in root.rglob(pattern) if p.is_file())

    if include_metadata:
        for sibling in ("metadata", "splits"):
            sibling_dir = base / sibling
            if sibling_dir.is_dir():
                targets.extend(p for p in sibling_dir.rglob("*") if p.is_file())

    # Skip the SHA256SUMS file itself if it lives inside the tree.
    targets = [p for p in targets if p.name != "SHA256SUMS"]

    # Sort by POSIX-style relative path for reproducibility.
    targets.sort(key=lambda p: p.relative_to(base).as_posix())
    return targets


# ---------------------------------------------------------------------------
# Generate / verify
# ---------------------------------------------------------------------------

def write_sums(
    files: list[Path],
    base: Path,
    output: Path,
    workers: int,
) -> None:
    """Hash *files* in parallel and write the SHA256SUMS file."""
    output.parent.mkdir(parents=True, exist_ok=True)

    results: list[tuple[str, str]] = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        jobs = {pool.submit(_hash_one, (f, base)): f for f in files}
        done = 0
        total = len(jobs)
        for fut in as_completed(jobs):
            results.append(fut.result())
            done += 1
            if done % 500 == 0 or done == total:
                print(f"  hashed {done}/{total}", file=sys.stderr)

    # Sort again by relative path (parallel completion order is not stable).
    results.sort(key=lambda r: r[0])

    with output.open("w", encoding="utf-8", newline="\n") as fh:
        for rel, digest in results:
            # GNU coreutils format: "<digest>  <relative-path>\n"
            # Two spaces == binary mode marker (we always read binary).
            fh.write(f"{digest}  {rel}\n")

    print(f"\nWrote {len(results)} entries to {output}", file=sys.stderr)


def parse_sums_file(path: Path) -> dict[str, str]:
    """Parse a SHA256SUMS file into a {relative_path: digest} mapping."""
    mapping: dict[str, str] = {}
    with path.open("r", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            line = raw.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            # Format: "<64-hex-digest>  <relpath>" (two spaces, binary mode).
            # Tolerate single-space separators just in case.
            try:
                digest, rel = line.split(maxsplit=1)
            except ValueError as e:
                raise ValueError(
                    f"{path}:{lineno}: malformed line: {line!r}"
                ) from e
            rel = rel.lstrip("*").lstrip()  # drop the "*" binary marker if present
            if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise ValueError(
                    f"{path}:{lineno}: not a valid SHA-256 digest: {digest!r}"
                )
            mapping[rel] = digest
    return mapping


def verify_sums(
    files: list[Path],
    base: Path,
    sums_file: Path,
    workers: int,
) -> int:
    """Verify *files* against *sums_file*. Returns exit code (0 == OK)."""
    if not sums_file.is_file():
        print(f"ERROR: {sums_file} not found", file=sys.stderr)
        return 2

    expected = parse_sums_file(sums_file)
    found_paths = {p.relative_to(base).as_posix() for p in files}
    expected_paths = set(expected)

    missing = sorted(expected_paths - found_paths)
    extra = sorted(found_paths - expected_paths)

    # Hash the files we actually have (in parallel).
    actual: dict[str, str] = {}
    common = sorted(found_paths & expected_paths)
    print(f"Verifying {len(common)} files...", file=sys.stderr)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        common_paths = [base / rel for rel in common]
        jobs = {pool.submit(_hash_one, (p, base)): p for p in common_paths}
        done = 0
        for fut in as_completed(jobs):
            rel, digest = fut.result()
            actual[rel] = digest
            done += 1
            if done % 500 == 0 or done == len(jobs):
                print(f"  verified {done}/{len(jobs)}", file=sys.stderr)

    mismatched = sorted(rel for rel in common if actual[rel] != expected[rel])

    print(file=sys.stderr)
    print(f"  files in manifest: {len(expected_paths)}", file=sys.stderr)
    print(f"  files on disk    : {len(found_paths)}", file=sys.stderr)
    print(f"  matched          : {len(common) - len(mismatched)}", file=sys.stderr)
    print(f"  mismatched       : {len(mismatched)}", file=sys.stderr)
    print(f"  missing on disk  : {len(missing)}", file=sys.stderr)
    print(f"  unlisted on disk : {len(extra)}", file=sys.stderr)

    if mismatched:
        print("\nMismatched files:", file=sys.stderr)
        for rel in mismatched[:20]:
            print(f"  {rel}", file=sys.stderr)
        if len(mismatched) > 20:
            print(f"  ... ({len(mismatched) - 20} more)", file=sys.stderr)

    if missing:
        print("\nMissing files (in manifest but not on disk):", file=sys.stderr)
        for rel in missing[:20]:
            print(f"  {rel}", file=sys.stderr)
        if len(missing) > 20:
            print(f"  ... ({len(missing) - 20} more)", file=sys.stderr)

    if extra:
        print("\nExtra files (on disk but not in manifest):", file=sys.stderr)
        for rel in extra[:20]:
            print(f"  {rel}", file=sys.stderr)
        if len(extra) > 20:
            print(f"  ... ({len(extra) - 20} more)", file=sys.stderr)

    return 0 if not (mismatched or missing or extra) else 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate or verify SHA256SUMS for the PRISM-36K release.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("images"),
        help="Image root directory (default: ./images)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("checksums/SHA256SUMS"),
        help="Path to the SHA256SUMS file (default: ./checksums/SHA256SUMS)",
    )
    parser.add_argument(
        "--include-metadata",
        action="store_true",
        help="Also hash files under metadata/ and splits/",
    )
    parser.add_argument(
        "--pattern",
        default="*",
        help="Glob filter applied to filenames under --root (default: '*')",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=os.cpu_count() or 1,
        help="Parallel hashing workers (default: %(default)s)",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify mode: check files against an existing SHA256SUMS",
    )

    args = parser.parse_args()

    root = args.root.resolve()
    if not root.is_dir():
        print(f"ERROR: --root {root} is not a directory", file=sys.stderr)
        return 2

    base = root.parent
    print(f"Repository base : {base}", file=sys.stderr)
    print(f"Hashing root    : {root}", file=sys.stderr)
    print(f"Pattern         : {args.pattern}", file=sys.stderr)
    print(f"Include metadata: {args.include_metadata}", file=sys.stderr)
    print(f"Workers         : {args.workers}", file=sys.stderr)

    files = collect_files(root, args.include_metadata, args.pattern)
    if not files:
        print("ERROR: no files matched", file=sys.stderr)
        return 2
    print(f"Files to process: {len(files)}\n", file=sys.stderr)

    if args.verify:
        return verify_sums(files, base, args.output, args.workers)
    else:
        write_sums(files, base, args.output, args.workers)
        return 0


if __name__ == "__main__":
    sys.exit(main())
