# Offline candidate pipeline contract

## Scope and safety

`build_site.py` is the supported orchestrator. It does **not** collect, deploy,
replace a production directory, push, alter cron, or enable semantics/remote APIs.
Standalone sub-builders are low-level tools and are not publication gates.
Baseline static files are read with `git show` from exact commit
`3e05fc01d65d0457cc7dd1ec5fab04c4b879e31b`, never from the mutable checkout.
Only the 21 explicit static paths are copied: no source/docs/test tree is published.
The validator and optional compact builder are reviewed local copies in `scripts/`.
Relations stay withdrawn (eight empty children shards); no heuristic fallback.

## Input tree

```
frozen-input/
  data/<shard>/<id>.json
  tracker_meta/<shard>/<id>.json
  metadata.json                   # optional legacy metadata mapping
  charts.json                     # REQUIRED same-snapshot chart array
```

Supply a separate producer manifest:

```
{"schema":1,"status":"complete","collection_id":"producer-batch-id",
 "fixture":false,"expected_date":"2026-10-28",
 "files":{"data/123/123456.json":"<64-lowercase-hex-SHA256>",
          "tracker_meta/123/123456.json":"<SHA256>",
          "charts.json":"<SHA256>"}}
```

Every file under the two input directories and every optional named input must
appear exactly once in the digest inventory. No symlinks, traversal, unlisted
files, invalid IDs, unreadable JSON, or empty usable price history are accepted.
Input hash checking and copying create a frozen private working tree. The
producer, not this builder, is responsible for truthfully attesting collection
completion and generating charts from that same data. Hashes prove integrity,
not that collection succeeded. Production charts must be nonempty. Explicit
`fixture:true` permits an empty chart list for tests only and is carried to output.
No production completion manifest or real price/meta fixture has been supplied.

## Invocation

```
python build_site.py --input-root /path/frozen-input \
  --completion-manifest /path/completion.json \
  --baseline-repo /path/boopadb-data-validation \
  --output-dir /path/NEW-candidate [--compact]
```

The output must not exist. Linux atomic no-replace rename is required; unsupported
platforms fail closed. Staging is a sibling `.NAME-candidate-*` directory. Failed
runs retain `FAILED.txt`, frozen inputs, and partial private output for diagnosis;
they never expose the requested output. Successful runs keep provenance staging
with `SUCCESS.json`. No unrelated paths are cleaned or deleted automatically.

## Order and completion

1. Verify/freeze manifest-bound inputs; copy pinned static assets.
2. Build legacy lists, 24 search shards, shop/category data, withdrawn relations.
3. Render HTML from those lists and explicit charts; add index-only diagnostics.
4. Run trusted `embed-hero.cjs` **after lists and HTML**; derive item afterward.
5. Optionally generate lossless compact data (does not activate compact client).
6. Run snapshot validator including hero `--check`, date, count/IDs/schema.
7. Hash all output files; validate output manifest; atomically expose new candidate.

`snapshot-manifest.json` uses schema 1 + files SHA256 map accepted by the validator,
with status `validated-candidate`, producer collection ID, fixture marker, input
hashes, baseline commit, validation result, compact flag, and `deployed:false`.
It deliberately does **not** claim production collection completion, deployment,
or comprehensive browser QA. External handoff must run the full applicable UI
suite against the resulting candidate before authorizing production publication.

## Static review and tests

Original build_prod/full/embed were reviewed before execution and left unchanged.
They had fixed home paths/import-time writes and partial direct-prod output.
Copies now use explicit paths and guarded entrypoints. Build_full retains pricing,
ranking, windows and withdrawn-relations decisions; invalid files fail instead of
silently lowering counts. `validate_snapshot.py` reviewed: JSON/hash reads plus
node hero check only; root hero script is always the pinned reviewed script.
`build_search_catalog.py` reviewed: local lossless serialization only.

Run `python -m unittest discover -s . -p test_pipeline.py -v` from integration.
Current tests use synthetic data only: success with compact output, preserved
static assets/index-only diagnostics/empty relations; input tampering; wrong date;
existing-target refusal. These do not substitute for real full-dataset/browser QA.

## Received operational scripts reconciliation (2026-10-29)

Static review of newly received originals occurred before any execution. Originals
remain immutable and were never run:

- Original `build_site.py` was an embedded two-page preview, not production.
  Its intent is retained as explicit-path `build_preview_site.py`; the integrated
  `build_site.py` name is deliberately reserved for the full candidate pipeline.
- Original `refresh_data.sh` fetched mutable remote main, removed stage/backups,
  swapped live data/meta separately, then built data alone. New `refresh_data.sh`
  delegates to the explicit producer-manifest candidate pipeline. It does not
  fetch, extract, delete backups, swap collector directories, or infer completion
  from dates/counts. Collection/transport integration remains a separate blocked
  step until the producer completion contract is implemented and verified.
- Original `deploy_data.sh` made per-file commits, skipped old filenames using a
  persistent DONE list, and excluded lists_full/HTML. This could expose mixed
  snapshots. New script delegates to `prepare_deployment.py`: **dry-run only**,
  one all-files commit plan including 15 HTML pages (active is a redirect), data,
  preserved static assets and snapshot manifest. It neither uses nor changes the
  existing `/opt/hatch/bin/github` credentials/configuration. There is deliberately
  no publishing switch or executable publisher in this handover.

Deployment plan invocation:

```
bash deploy_data.sh --candidate /path/NEW-candidate \
  --target-repo /path/local-boopadb-checkout \
  --expected-head <full-40-character-SHA> --output-plan /path/NEW-plan.json
```

The expected SHA is compared to the supplied **local** checkout. No remote check
is claimed. Plans are always `publishable:false`, `published:false`, and require
fresh remote HEAD verification + atomic/non-force one-commit compare-and-swap,
completion evidence and full QA before a separately authorized publisher could
act. Fixture plans require `--allow-fixture` and remain nonpublishable. Exact
candidate inventory and hashes are revalidated; modified HTML, missing data,
changed local HEAD, or incomplete producer status yields no output plan.

Verification expanded to **10 passing fixture tests** including snapshot planning,
SHA mismatch, fixture refusal, changed HTML hash refusal, incomplete collection
refusal; shell syntax and Python compile checks pass. No remote deployment ran.

## Review fixes and legacy producer adapter

`prepare_deployment.py` now checks every manifest path and SHA256 **before**
invoking any validator subprocess. It additionally pins the hero selector source
SHA256 to the reviewed baseline; rewriting both candidate index and its manifest
cannot authorize arbitrary selector execution. The input completion manifest is
read once and hashed from those exact bytes, avoiding a late provenance reread.

`charts_contract.py` validates nonnull chart objects, unique canonical IDs, source
names, nonempty variations, sorted ISO dates, finite nonnegative prices, sale and
outlier flags, source point correspondence, endpoint coverage and observation
counts. Production rendering reattaches sale/drop embedded variation histories
using the actual reviewed `varutil.py`; it fails if that dependency is absent.
`generate_charts` preserves the original prototype's representative-series choice,
score formula, minimum 60 observations/3 distinct prices, and top-three ordering.
If those selected records cannot provide valid variations, production fails rather
than silently emitting empty/invalid charts.

`prepare_inputs.py` can consume the existing local `data/` + `meta/` layout.
It ignores **only empty `.gitkeep`**; any other non-JSON file or symlink is rejected.
The producer attestation has schema/status/collection_id/fixture/expected_date and
an exact SHA256 `files` mapping using legacy `data/...` and `meta/...` paths.
For `--charts-file`, include `charts.json` in that mapping; for `--generate-charts`,
include only raw source files, and charts are derived from the frozen copy with the
reviewed helper. The adapter does not make its own collection-complete claim.

```
python prepare_inputs.py --tracker-root /path/existing-tracker \
  --generate-charts --attestation /path/producer-complete.json \
  --output-dir /path/NEW-input
bash refresh_data.sh --input-root /path/NEW-input \
  --completion-manifest /path/NEW-input/completion.json \
  --baseline-repo /path/boopadb-data-validation --output-dir /path/NEW-candidate
```

This is not cron repair or verified end-to-end automatic refresh: a truthful
producer completion attestation and real input batch still need integration.

## Separate inert publisher implementation

`publish_snapshot.py` now contains an optional separately invoked Git publisher;
this supersedes the earlier statement that no executable publisher exists. It is
**not invoked by either wrapper**, defaults to dry-run, and was never executed
against any remote during this work. It uses the existing `origin` and Git
credential configuration without changing either. Execution additionally requires
an exact plan-hash/parent-SHA/repository/branch authorization file identifying the
authorizer and affirming completed full-dataset/browser QA and independently
verified producer completion. These are operator attestations, not facts inferred
by the tool. The current handover grants no permission to run it.

On separately authorized execution it revalidates the candidate, verifies remote
HEAD, creates a temporary-index commit with exactly expected HEAD as its parent,
and sends all manifest files in **one** explicit-lease compare-and-swap push.
Existing paths not listed in the snapshot are inherited; no delete operation or
working-tree reset occurs. A changed remote HEAD fails the lease. It verifies the
remote commit afterward and reports uncertainty instead of automatically retrying.
Git object writes may remain locally on failed attempts; no partial remote commit
is intentionally published. Real credential/transport compatibility is untested.

Current checks: **15 fixture tests pass**, including a synthetic 65-day,
two-variation chart using real varutil and production enrichment, forged-selector
rejection before validator loading, legacy adapter, and publisher default making
no Git calls. No remote publication or full real-dataset/browser QA was run.

Publisher contract coverage expanded to **16 total passing tests**. The additional
publisher test mocks every Git operation: one commit and one explicit-lease push
are requested on mocked success, while a mismatched remote HEAD requests no writes
or push. This validates control flow only, not actual credentials/transport.

## Explicit approved relation bundle (new namespace)

Optional `--relations-bundle ROOT --relations-approval FILE` preserves exactly
`relationship-ui-draft.js`, `relationship-data.js`, `relation-data/manifest.json`,
64 `relation-data/items_N.json`, and 8 `relation-data/children_N.json`. Approval:

```
{"schema":1,"status":"approved","version":"<bundle version>",
 "activate":true,"files":{"relationship-data.js":"<sha256>","...":"..."}}
```

The complete 75-file SHA256 mapping is required. Every JSON wrapper must match
`schema:boopadb-relations-v1` and the approved version. Legacy
`relations_children_N.json` remain empty/withdrawn; the new namespace cannot be
overwritten by build_full. Copying takes place after generators and before item
page derivation. Snapshot provenance includes approval hash/version/inventory.
The deployment planner cross-checks approval hashes against snapshot hashes and
rejects mixed relation versions; all new files join the same snapshot commit.

Activation is **separate from structural data QA**: only literal `activate:true`
enables exactly one reviewed `const RELATION_UI_LIVE = false;` marker in generated
index, and requires both module imports. Item inherits that approved change.
Missing/duplicate markers or missing imports fail the candidate. Without explicit
activation, a copied bundle stays disabled. Current source QA reports with
`provenance_approval:false` are not approval documents.

Current fixture suite: **18 tests pass**, including explicit activation gating and
relation bundle preservation/planning/tamper rejection. Final real UI hashes and
browser QA remain owned by the relation integration worker.

## Final operational safeguards

All Git subprocesses have bounded timeouts (local baseline/planning: 60 seconds;
publisher operations: 480 seconds). Publication writes an fsync-backed journal
before any write and after each blob/index entry, commit creation, push start,
uncertain result, and verified remote commit. An existing journal is never
silently overwritten. `reconcile_publication.py` makes only a bounded remote HEAD
read and records expected-parent/current-commit/conflict; it never pushes. A push
timeout requires reconciliation, not blind retry. Tests simulate success, changed
HEAD and push timeout/remote success entirely with mocked Git calls.

Use a fresh dedicated checkout per run (existing credentials, no new config).
The publisher leaves the local branch/working tree unchanged; it explicitly
reports that the next run needs a fresh checkout/refreshed plan. Scheduler wiring
and producer transport remain unmodified. A separate
`verify_published_manifest.py` can make bounded read-only HTTPS checks (0–600s) for
the exact snapshot manifest SHA after Pages updates. A remote Git commit being
verified does not prove public HTTP content has updated. This checker has only
been mock-tested here; no public verification was claimed.

Builds may use `--static-root pinned-static` instead of a Git baseline checkout.
The package's 22 static assets must match both the pinned commit and trusted
hardcoded SHA256 map; rewriting its manifest cannot authorize changed code.
Minimal delivery smoke tests run entirely offline against these pinned assets.

## Delivery v2 scale/privacy and reconciliation hardening

The complete producer/raw input SHA inventory stays private in the staging run's
`producer-completion.json`. The public snapshot manifest now records only its
original-byte SHA256, input file count and canonical inventory digest, not hundreds
of thousands of raw input entries. This keeps published receipts small and avoids
unnecessary source-inventory publication. All frozen-input checking still uses
the complete private inventory before building.

Reconciliation validates the journal's repository/branch and the checkout's
existing origin against the same authorized BoopaDB origin allowlist as the
publisher, before contacting a remote. A wrong checkout/origin cannot yield a
misleading verification receipt. This check is covered by a mocked regression.
The HTTPS checker's configured wait is a bounded polling window; an individual
network request can additionally take up to its 15-second request timeout.

## v4 verified-output and complete-child-search contract

See V4-RERUN.md for operational instructions. Safe rerender requires an externally
pinned source snapshot manifest, exact inventory/hashes, trusted static assets,
and JSON-only bootstrap extraction. It retains all 59 data hashes and raw source
provenance, adds `raw_rebuild_performed:false`, and uses a fresh atomic output.
It does not substitute for a new collection or raw rebuild.

Active relationship candidates now require both the 75-file preview bundle and
10-file complete inverse bundle. Complete inverse is independently reconstructed
from all 64 approved outgoing shards and checked for exact full sets, buckets,
internal hashes, totals and version binding; no capped preview is accepted. All
three script queries are bound to their approved content hashes on both pages.
No-bundle fixtures remove all three known imports and retain the disabled gate.

The planner checks the exact expected target commit before creating a plan. It
refuses to withdraw already-live relationship UI or complete child search and
refuses to replace a target static asset with a different pinned older version.
Current released UI reference: a485fbe9c40eb779e1f3517f89ced8a27d3808ec.
This does not authorize publication or installation. Local-test approval scope
continues to block the separately gated publisher.
