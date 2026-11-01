#!/usr/bin/env python3
"""[DRAFT-ADAPTATION] Ledger <-> file-tree exact verification.

Proposed checked-in location: generator/scripts/verify_inventory.py

Used identically by the daily build job (pre-pack), the daily
validate job, and the promote workflow.

    verify_inventory.py LEDGER_JSON ROOT

Rules (any violation = exit 1):
- ROOT itself must not be a symlink, and no symlink may exist
  anywhere under ROOT.
- The ledger must satisfy the typed "ledger" contract (non-empty,
  confined paths, sha256 values, no duplicate keys, no
  normalization/case collisions) via validate_bindings.
- The ledger file set must EXACTLY equal the actual file set under
  ROOT (both directions), and every hash must match.
- No unexpected empty directories: every directory under ROOT (other
  than ROOT itself) must contain at least one file in its subtree.
"""

import hashlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_bindings import BindingError, check_ledger, load_strict_json


def fail(msg):
    print(f"::error::{msg}")
    sys.exit(1)


def main(argv):
    if len(argv) != 3:
        print(__doc__)
        return 2
    ledger_path, root = Path(argv[1]), Path(argv[2])
    if os.path.islink(root):
        fail(f"inventory root is a symlink: {root}")
    if not root.is_dir():
        fail(f"inventory root is not a directory: {root}")
    try:
        ledger = check_ledger(load_strict_json(ledger_path), str(ledger_path))
    except BindingError as exc:
        fail(str(exc))

    actual = {}
    dirs_with_files = set()
    all_dirs = set()
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        base = Path(dirpath)
        for name in dirnames:
            p = base / name
            if p.is_symlink():
                fail(f"symlink in tree: {p}")
            all_dirs.add(p.relative_to(root).as_posix())
        for name in filenames:
            p = base / name
            if p.is_symlink():
                fail(f"symlink in tree: {p}")
            rel = p.relative_to(root).as_posix()
            actual[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
            parent = p.parent
            while parent != root:
                dirs_with_files.add(parent.relative_to(root).as_posix())
                parent = parent.parent
    empty_dirs = sorted(all_dirs - dirs_with_files)
    if empty_dirs:
        fail(f"unexpected empty directories: {empty_dirs[:10]}")
    if set(actual) != set(ledger):
        fail(f"ledger/file set mismatch: on disk only="
             f"{sorted(set(actual) - set(ledger))[:10]}, in ledger only="
             f"{sorted(set(ledger) - set(actual))[:10]}")
    bad = [rel for rel, want in ledger.items() if actual[rel] != want]
    if bad:
        fail(f"hash mismatch: {bad[:10]}")
    print(f"inventory OK: {len(ledger)} files, sets equal, hashes match, "
          f"no empty directories, no symlinks")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
