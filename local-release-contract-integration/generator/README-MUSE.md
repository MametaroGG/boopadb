# BoopaDB generator integration — private Muse dry-run handoff

This package repairs candidate generation and provides a separately gated single-
commit publisher. It is **not yet a deployed/scheduled automatic-update repair**.
Keep it separate from `~/workspace/boothdb/`; do not replace live scripts or cron
while testing. No credential or remote configuration changes are included.

## v4 current instructions

Read `V4-RERUN.md` first. v4 supersedes earlier handoffs for new candidates;
old v2 plans withdraw public relationships and must not be published. The earlier
verification results below are historical evidence, not v4 test totals.

## Verified locally (prior releases)

- 19 pipeline fixture tests, plus delivery smoke test passed.
- 59/59 frozen public output files matched Muse's 2026-10-29 SHA/byte inventory.
- Full output-render validator: 201,234 rows/unique IDs, date 2026-10-29, hero sync.
- Activated regenerated index/item with actual relation data passed 7 DOM tests;
  broader relation DOM suite passed 15 tests. Pixel/browser QA remains blocked.
- Full generated-catalog DOM regression suite: **102/102 passed** (activated-gate assertion adjusted in private QA harness; original source tests unchanged).
- These are not proof of a complete raw collection/rebuild on Muse.

## 1. Verify and smoke-test (no network)

Verify every `DELIVERY-MANIFEST.json` SHA256 before importing or running code.
Python 3 and Node are required. No pip/npm installation is needed for the smoke test.

```
cd ~/workspace/boothdb-integration-v4
python3 -m unittest test_delivery_smoke.py -v
```

All smoke data is synthetic and temporary; no production path is touched.
`pinned-static/` contains 22 exact baseline assets; the code has independent digest
pins. No full raw tracker or catalog output is included in this package.

## 2. Prepare a real immutable source batch ON MUSE

Existing tracker path is `~/workspace/boopa-inspect/data/` and `meta/`.
Do not infer collection completion from file counts, max_date, or the old published
output inventory. Muse must first establish the actual producer finished one
batch, and keep that data/meta immutable while preparing it. Do not run the old
unpinned-main/raw-swap script as part of this dry run.

Record the verified batch in a private `producer-complete.json`:

```
{"schema":1,"status":"complete","collection_id":"<actual producer batch>",
 "fixture":false,"expected_date":"<actual YYYY-MM-DD>",
 "files":{"data/123/123456.json":"<SHA256>",
          "meta/123/123456.json":"<SHA256>","...":"..."}}
```

`files` must list every JSON file in those two immutable directories. Ignore only
empty `.gitkeep`; reject any other non-JSON or zero-byte JSON. The inventory can
be generated locally after genuine completion is established; it must not be
presented as independent proof that the collector completed. No raw bulk needs
transfer to dot. The old frozen public-output manifest is NOT this raw manifest.

```
RUN="$HOME/workspace/boothdb-integration-runs/<unique-real-batch>"
python3 prepare_inputs.py --tracker-root "$HOME/workspace/boopa-inspect" \
  --generate-charts --attestation "$RUN/producer-complete.json" \
  --output-dir "$RUN/input"
bash refresh_data.sh --input-root "$RUN/input" \
  --completion-manifest "$RUN/input/completion.json" \
  --static-root "$PWD/pinned-static" --output-dir "$RUN/candidate" \
  --relations-bundle relation-bundle --relations-approval relation-local-approval.json \
  --relation-search-bundle relation-search-bundle \
  --relation-search-approval relation-search-local-approval.json
```

Charts and sale/drop variation histories are built from this frozen source using
verified varutil. HTML bootstrap sizes match published caps (12 sale, 10 drops,
9 active, 10 newest), but values/stats and hero pools use the current candidate.
The full lists/shards are never replaced with capped data. Compact output is
optional and **off by default**; no semantic/remote search feature is enabled.

## 3. Relationship integration

`relation-bundle/` contains the final 75-file new-namespace bundle. Its inventory
is `relation-bundle-inventory.json` with status `review-required`, not fabricated
approval. Existing source provenance was verified, and local runtime QA passed;
publication activation requires the parent's separate final approval.
For an explicitly approved local test, use an approval copy with `status:approved`,
`activate:true`, `scope:local-test-only`; pass `--relations-bundle` and
`--relations-approval` plus `--relation-search-bundle` and
`--relation-search-approval` to refresh (see V4-RERUN.md for both approvals).
The complete-search extension contains ten additional files; all 85 runtime files
are required for current activated UI. Such a candidate cannot be published by the
publisher. Final publication requires `scope:publication-approved` and exact
unchanged inventory hashes. Legacy children shards and legacy gate remain disabled.

## 4. Publication planning and unresolved transport preflight

The old `/opt/hatch/bin/github push-files` route has a ~5 MB ceiling and cannot
atomically carry the 7.6 MB lists + all related assets. Do not return to per-shard
pushes or browser-uploading lists separately. The new publisher uses existing Git
`origin`/credentials and one commit; its credential/transport viability on Muse
has **not** been established. It changes no credential config.

Use a NEW dedicated checkout per run, never a user's dirty working checkout.
Verify its existing origin identifies `MametaroGG/boopadb`, then perform an
explicitly authorized read-only `git ls-remote` preflight with a timeout. If the
existing credentials do not work, stop and report the exact failure; do not invent
an alternate credential/security setup. Parent must approve any transport change.
Plan against the exact verified current remote SHA after bringing the dedicated
checkout to that commit. Local HEAD is left unchanged by publication, so the next
run requires a new/refreshed checkout and a new plan.

```
bash deploy_data.sh --candidate "$RUN/candidate" --target-repo /path/fresh-checkout \
  --expected-head <full-current-SHA> --output-plan "$RUN/plan.json"
```

This writes a dry-run plan only. Default publisher execution also stays dry.
`publish_snapshot.py --execute` requires an exact plan-hash/repository/parent
publication authorization and completed real-data/browser-QA attestations. Never
set it during this handoff dry run. See `PIPELINE-CONTRACT.md` for the contract.

A publication journal records planned/blob/commit/push-uncertain/verified stages
with fsync. Existing journals are never silently overwritten. After timeout:

```
python3 reconcile_publication.py --journal "$RUN/plan.json.publication.json" \
  --target-repo /path/fresh-checkout
```

This only reads remote HEAD; it never retries a push. After confirmed remote commit,
use `verify_published_manifest.py` with the exact expected manifest SHA and actual
HTTPS Pages manifest URL. Bounded observation may fail if Pages has not updated;
Git push success is not a promise of HTTP readiness.

## 5. What to return to dot

Small artifacts only: producer completion evidence description/source revision,
raw manifest hash + file counts, candidate `snapshot-manifest.json`, validator/log
summary, relation version/approval hash, local/remote expected SHA, Git transport
preflight result, and (only after separate authorized publication) journal,
remote commit SHA and public HTTP manifest hash result. Do not send raw data,
credentials, or unrelated private documents.

## Scheduler gate

Current caller is cron agent `boopadb-data-refresh`, ~05:53 JST; it currently
expects `RESULT ok`, runs shard deployment, then browser-uploads lists. This new
explicit-argument pipeline deliberately is NOT a no-argument drop-in. Do not
replace its instructions or enable cron until the real Muse dry run, transport,
atomic publication and public hash verification succeed and parent authorizes the
caller change. The final new caller must treat the candidate/plan/one-commit/
HTTP-verification stages as one job; old partial-upload steps must not remain.
