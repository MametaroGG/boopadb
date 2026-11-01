# v4: isolated, relationship-preserving local verification

v4 supersedes v2/v3 for new candidate generation. Do not publish the old v2 plan:
it withdraws the now-public relationship UI. This package includes the approved
UI spacing/status/cache linkage and complete inverse-child search changes from
31f26b5, published as a485fbe9c40eb779e1f3517f89ced8a27d3808ec. It does not resolve upstream
missing relations, classify “other,” infer edges, or change the 73 preview data
files. Complete search is derived only from approved master parent links.

## Local approval and exact inventories

`relation-bundle-inventory.json`: 75 files; unchanged relation-data version
260d8e22db4ae7a39ba8c43e6b75a3f587d353e58e6fa0b43787a3acbac93858.
`relation-search-bundle-inventory.json`: 10 files; complete inverse version
 af92b741ef73bca291d2312903a4bc843aaa518876f08b320fbc7f2504a3d79d,
72,104 edges / 4,661 parents, maximum 3,578 children without preview truncation.
Module import content hashes bind all three modules. Inventory approval is local
only, not publication authority. Generate private approvals after verifying the
handoff manifest and receiving the parent's local rerun instruction:

```sh
python3 - <<'PY'
import json
from pathlib import Path
for stem in ('relation','relation-search'):
    a=json.loads(Path(stem+'-bundle-inventory.json').read_text())
    a.update(status='approved',activate=True,scope='local-test-only')
    Path(stem+'-local-approval.json').write_text(json.dumps(a,indent=2)+'\n')
PY
```

## Fast UI-only route: reuse verified output, NOT another raw rebuild

Parent must resolve the machine scope first (mini PC requested; prior v2 report
said VM). Muse supplies the actual OLD_CANDIDATE absolute path; do not guess it.
It must contain the complete v2 candidate, not just the manifest. NEW_OUTPUT must
be a new absent directory outside that source. All source files are hashed before
use and rechecked during reading; HTML payload is parsed as JSON, never evaluated.

```sh
python3 rerender_candidate.py \
  --source-candidate "$OLD_CANDIDATE" \
  --expected-source-manifest-sha256 339cec04950ccdbb0ef6a22dbcb91c2aa39bac9780f41d511dccbe5d5c527f3b \
  --output-dir "$NEW_OUTPUT" \
  --relations-bundle relation-bundle --relations-approval relation-local-approval.json \
  --relation-search-bundle relation-search-bundle \
  --relation-search-approval relation-search-local-approval.json
```

No `--allow-fixture` for real data. The output must retain all 59 data SHA256s,
201,234 rows/IDs, and source input manifest digest
31a6826cbcf1161b0e7ed572109fbb27565fac6e138224231fcc7e33148d1cc9.
It explicitly records `raw_rebuild_performed:false`, original input provenance,
and the source candidate manifest digest. This preserves Muse's reported raw
rebuild provenance; it does not independently establish collection completeness.

## New raw batch route remains required for actual data updates

Use `prepare_inputs.py` and `build_site.py` as documented in README-MUSE. Supply
BOTH pairs of bundle/approval flags above to `build_site.py` too. A fresh completed
producer attestation is required for a new batch; output reuse never replaces the
collector, scheduler, or frozen raw rebuild. Do not execute legacy refresh/deploy.

## Plan only, then return evidence

Use a fresh clean checkout at the actual current public HEAD and provide its exact
SHA to `prepare_deployment.py`; never assume the historical static baseline is
current main. Planner refuses already-live UI/search withdrawal or differing
pinned static assets. Return snapshot manifest, plan, stdout, machine/path facts,
and exact extra ignored raw-file paths from the v2 source manifest. No publish,
cron, credential, transport, or live-directory change is authorized by this file.
The local-only approval scope intentionally blocks publication; a separately
reviewed approval/plan is needed after all evidence and public baseline agree.

Existing open pages require reload to receive the new versioned modules; no
instant live-update promise. The raw generator/publisher has not been installed
or scheduled here, and authenticated Git push from Muse remains unverified.
