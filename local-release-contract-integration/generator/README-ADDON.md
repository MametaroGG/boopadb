# Private v4 relation correction addon — LOCAL RERENDER ONLY

Use only after the parent confirms the correction's independent review and public
release commit recorded in ADDON-MANIFEST.json. This addon does not authorize
publication, producer collection, cron installation or transport changes.
Original v4 archive remains unchanged; do not edit that archive or live scripts.

## Bounded changes

- Replaces 82 version-coherent JSON files; all three UI module bytes unchanged.
- Original master stays immutable. Hash-bound additive override adds exactly 12
  parent edges and two prerequisites across two items; no removals/inferred IDs.
- Complete inverse is rebuilt, not patched from capped previews: Lumina1,121,
  maximum3,579. New preview7153fbbb… and complete-search0fc6bbdd… versions.
- Replaces only prepare_deployment.py in generator code. The planner requires
  every relationship module/data path already in expected public HEAD to have
  the exact same candidate hash. Missing, old or altered bytes fail with no plan.
  Normal daily catalog updates remain allowed when relation runtime is unchanged.
- Intentional relationship upgrades must use the separately reviewed publication
  path FIRST, then rerun the generator against that current public baseline.
  There is no override flag, upgrade approval bypass or automatic remote update.

## Private provenance

private-provenance/ contains original source hashes, the tiny exact override,
review receipts and reconstruction reference. It deliberately excludes the full
master/raw catalog. Official compatibility qualifications (Lumina1.07,
FC_Milltina FBX) stay private evidence because current public arrays cannot encode
qualifiers; do not turn these edges into unqualified compatibility guarantees.
The immutable override retains its original review_pending status for hash
stability; the separate release/review receipt determines approval, not edits to
that source document. Reconstruction reference is for audit, not a runnable
collector installation: it refers to the review workspace. Future source rebuild
must apply the exact override to the exact original master, verify derived source
hashes and retain the separate approval; otherwise the old master would regress.

## Installation into a fresh private tool directory only

Verify every original v4 DELIVERY-MANIFEST.json file hash and every addon
ADDON-MANIFEST.json hash BEFORE executing/importing any supplied Python. Confirm
base archive SHA d4cb538007657f1b065cde744122ef0f39100b3071b7b6dcf61faadd3b21ca23.
Use actual absolute paths for BASE (verified extracted v4), ADDON, and a NEW path
which does not exist. This edits neither source, published site nor live scripts:

```sh
set -eu
mkdir "$NEW"
cp -a "$BASE/." "$NEW/"
mv "$NEW/DELIVERY-MANIFEST.json" "$NEW/BASE-DELIVERY-MANIFEST.json"
cp "$ADDON/prepare_deployment.py" "$NEW/prepare_deployment.py"
cp "$ADDON/test_runtime_preservation.py" "$NEW/test_runtime_preservation.py"
cp "$ADDON/relation-bundle-inventory.json" "$NEW/relation-bundle-inventory.json"
cp "$ADDON/relation-search-bundle-inventory.json" "$NEW/relation-search-bundle-inventory.json"
cp -a "$ADDON/relation-bundle/." "$NEW/relation-bundle/"
cp -a "$ADDON/relation-search-bundle/." "$NEW/relation-search-bundle/"
cp "$ADDON/ADDON-MANIFEST.json" "$NEW/ADDON-MANIFEST.json"
```

Keep both base/addon verification receipts: base hashes no longer describe the
replaced files. Reverify all replacement paths against addon hashes. Do not use
old local-approval JSON files. In NEW regenerate both local-only approvals from
the NEW inventories using V4-RERUN.md. Then run `python3 -m unittest test_delivery_smoke test_runtime_preservation` before the
same pinned Muse-source rerender command. Both corrected bundle flags remain
mandatory. The 59 source catalog data hashes and raw provenance must stay equal.

Use a fresh clean checkout at the ACTUAL latest public HEAD for the plan, not a
stale a485fbe target. If public runtime differs, stop and reconcile; never disable
the equality guard or use the original unpatched v4 planner. Return manifest,
plan and logs to parent; no push. Local-only approvals intentionally cannot publish.
