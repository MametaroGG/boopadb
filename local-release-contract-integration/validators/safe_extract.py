#!/usr/bin/env python3
"""[DRAFT-ADAPTATION] The ONE safe tar extraction routine.

Proposed checked-in location: generator/scripts/safe_extract.py

Used identically by the daily validate job and the promote workflow
(dot v2 review: the archive handling must be a single common routine,
not two hand-rolled copies that can drift).

    safe_extract.py ARCHIVE DEST

Rules (any violation = exit 1, nothing is promoted):
- DEST itself must not be a symlink; it is created if absent and must
  be empty.
- Every member name is confined: no absolute paths, no "..", no
  ".git" content.
- No duplicate member names, and no two names that collide after
  Unicode NFC normalization + case folding.
- Only regular files and directories: symlinks, hardlinks, devices
  and FIFOs are rejected.
- Extraction is manual (member-by-member copy); tarfile's own
  extraction filters are never relied on.
- After extraction, no symlink may exist anywhere under DEST.
"""

import os
import sys
import tarfile
import unicodedata
from pathlib import Path, PurePosixPath


def fail(msg):
    print(f"::error::{msg}")
    sys.exit(1)


def main(argv):
    if len(argv) != 3:
        print(__doc__)
        return 2
    archive, dest = Path(argv[1]), Path(argv[2])
    if dest.is_symlink():
        fail(f"extraction root is a symlink: {dest}")
    if dest.exists() and any(dest.iterdir()):
        fail(f"extraction root is not empty: {dest}")
    dest.mkdir(parents=True, exist_ok=True)
    dest_resolved = dest.resolve()

    try:
        tf = tarfile.open(archive)
    except (OSError, tarfile.TarError) as exc:
        fail(f"cannot open archive {archive}: {exc}")

    members = tf.getmembers()
    seen = {}
    plan = []
    for m in members:
        name = m.name[2:] if m.name.startswith("./") else m.name
        if name in ("", "."):
            continue
        pp = PurePosixPath(name)
        if pp.is_absolute() or ".." in pp.parts:
            fail(f"unsafe archive entry: {m.name}")
        if name == ".git" or name.startswith(".git/"):
            fail(f".git content in archive: {m.name}")
        if m.issym() or m.islnk():
            fail(f"link entry in archive: {m.name}")
        if not (m.isfile() or m.isdir()):
            fail(f"non-regular archive entry: {m.name}")
        folded = unicodedata.normalize("NFC", name).casefold()
        if folded in seen:
            fail(f"duplicate/colliding archive entry: {m.name!r} vs {seen[folded]!r}")
        seen[folded] = m.name
        plan.append((m, name))

    n_files = 0
    for m, name in plan:
        target = dest.joinpath(*PurePosixPath(name).parts)
        if dest_resolved not in target.resolve().parents and target.resolve() != dest_resolved:
            # Defence in depth: the confinement checks above already
            # guarantee this; never extract outside DEST regardless.
            if not str(target.resolve()).startswith(str(dest_resolved) + os.sep):
                fail(f"entry escapes destination: {m.name}")
        if m.isdir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            src = tf.extractfile(m)
            if src is None:
                fail(f"cannot read archive entry: {m.name}")
            with open(target, "wb") as out:
                while True:
                    chunk = src.read(1024 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
            n_files += 1

    for dirpath, dirnames, filenames in os.walk(dest):
        for entry in dirnames + filenames:
            if os.path.islink(os.path.join(dirpath, entry)):
                fail(f"symlink present after extraction: {entry}")

    print(f"safe extraction OK: {n_files} files, {len(plan)} members -> {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
