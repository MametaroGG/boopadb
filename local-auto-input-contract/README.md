# BoopaDB automatic input selection — implemented locally, not activated

## Result / exact remaining boundary

The missing collector→immutable-commit and automatic release-lineage selection
are now implemented as a **local producer patch + executable read-only resolver**.
`resolve_automatic_inputs.py` polls GitHub metadata, validates an immutable
run-attempt artifact and reviewed source identity, reads exact live lineage bytes,
and emits the selection; `finalize-context` emits the exact release-builder context
after inventory creation. All network tests are mocked. No service execution,
repository write, workflow dispatch, installation, credential change or publication
was performed.

**Current tracker cannot yet supply the new receipt.** Remaining activation work is
review/authorized installation of the concrete producer/consumer files and pins,
a real successful bounded collection save, verification of existing token access,
and authorized smoke/end-to-end execution. These are deployment/access/verification
prerequisites, not missing resolver code. Existing publication denials remain intact.

## Actual source evidence (not inferred from latest main)

Read-only GitHub source snapshot:
`MametaroGG/booth-vrc-price-tracker@4980d9bc341c85be5654751760867dce4bd57ba9`.
`evidence/` preserves the inspected source and Git tree metadata; `SOURCE.json`
records hashes. Source links are
`https://github.com/MametaroGG/booth-vrc-price-tracker/blob/4980d9bc341c85be5654751760867dce4bd57ba9/<path>`.

* `src/scraper.js:515–545`: real result states are completed/paused/partial/failed.
  The final checkpoint calls `client.finish()` even after partial/failed collection.
* `src/collection-runtime.js` `finish()`: `reservation.completed=true` is accounting
  cleanup, **not** successful collection. Current saved ledger at inspected commit
  has reservation `41280238039-1`, `completed:false`.
* `src/scraper.js` CLI emits only `continue_collection`; outcome/metrics are not a
  durable publication receipt.
* `.github/workflows/daily_scrape.yml`: scraper has `continue-on-error:true`, and
  final save runs on success **or failure**. The reporting step exposes failures.
  Checkout uses the current default branch, not necessarily event `github.sha`.
* `scripts/push-data.sh`: reservation and final-data commits can be rebased against
  advancing main; success previously returned no final immutable saved SHA.
* `docs/collection-runtime.md`: filtered searches, 3,333-page limit and bounded
  time do not establish complete BOOTH catalog coverage.

Thus latest main, event SHA, commit message/date and completed request accounting
cannot stand in for successful bounded observation + immutable final save.

## Concrete producer implementation

`producer-receipt.PROPOSAL.patch` includes all source changes **and full workflow
wiring**. Full modified files live in `proposed/`; `build_proposal.py` reproducibly
regenerates patch, full workflow, source guard and `producer-pin.PROPOSAL.json`
from preserved source/tree metadata. It performs no network/git writes.

1. `collection-receipt.js` records final actual result, metrics, drained/checkpointed
   state, retry count, times, reservation closure, run ID/attempt and executed source
   checkout commit into `data/collection_receipt.json`, committed with histories.
   CLI emits separate eligibility. A write failure fails the scraper.
2. `push-data.sh` outputs final `saved_commit` only after a successful push, **after
   rebase**; no-change/failed/uncertain paths emit none. The commit is not embedded
   self-referentially in its own tree.
3. `write-save-receipt.cjs` rereads that exact Git commit and creates
   `saved-collection.json`, binding repo/run/attempt, original scraper/save outcomes,
   saved commit and exact collection-receipt digest. Workflow uploads one uniquely
   named `boopadb-collector-<run_id>-<attempt>` artifact, overwrite disabled.
4. The full workflow has **trusted inline isolated-Python source guards** before
   dependencies, after reservation rebase immediately before scraper, and after
   final-save rebase before continuation/artifact code. They pin all tracked root
   source trees/blobs except mutable data/meta and workflow directory, verify clean
   worktree and reject untracked source/config/.npmrc. The workflow itself is
   SHA256-pinned by the resolver. Source SHA is recorded after reservation rebase.
   `python3 -I -` prevents a malicious checkout `json.py`/`subprocess.py` from
   executing before the guard. No gate is loaded from mutable checkout code.
5. Resolver independently checks pre-collection **and final-save** source root
   trees, exact source files, workflow definition at event SHA and successful guard
   steps. A receipt's self-declared old source SHA cannot authorize changed source.

Upload action is concretely pinned to verified upstream v4.6.2 commit
`ea165f8d65b6e75b540449e92b4886f43607fa02` (read-only evidence retained). These
are proposed reviewed-source values, not a claim they are installed/approved.
Any later collector/source-tree change needs reviewed pin/workflow regeneration.
Data and metadata changes alone do not require repinning.

## Eligible means healthy bounded observation — never all-catalog completion

All required counters/times/identity fields are typed; `failed` is false, reservation
is closed, at least one product was saved and an HTTP attempt charged, no run-local
item/search failures occurred, and no cooldown remains. Accepted terminal forms:

* `completed`, no reason, no retry-pending result; or
* `paused/deadline` at actual runtime boundary (existing 2-second tolerance and
  60-second minimum); or
* `paused/day-boundary` with an actual JST date crossing.

Partial, failed, unknown, legacy/missing receipt, arbitrary early pause, daily-budget
pause, empty work, incomplete reservation/save and ambiguous proof fail closed.
Existing collector continuation permits isolated deferred failures; publication
selection deliberately does not. Inherited retry backlog may remain during a
healthy bounded pause and its count is explicit. No catalog-success ledger or
whole-catalog claim is invented. Even a completed filtered segment is not BOOTH's
entire catalog. Every selection says `whole_catalog_complete:false` and scope
`bounded-filtered-search-observation`.

## Resolver and exact integration CLI

Requires Python stdlib, Node builtins and GitHub-hosted/source-gate Git; no install.
The resolver makes **GET only**, with fixed repository/API/live-site origins.

```sh
python local-auto-input-contract/resolve_automatic_inputs.py resolve \
  --workdir work/auto-selection \
  --baseline-pin generator/baseline_pin.json \
  --baseline-pin-sha256 '<reviewed exact-byte SHA256>' \
  --producer-pin '<reviewed installed producer-pin.json>'
```

`workdir` must be new. `GITHUB_TOKEN` is read from the environment only. Output:
`work/auto-selection/resolved-inputs.json`, with `selection.tracker_commit`,
`generation`, `prev_release_digest`, `expected_date`, bounded scope and provenance.
No token or signed download URL is persisted or logged. Signed artifact redirects
are host-restricted and never receive Authorization; all other redirects fail.

Polling rule: newest **terminal** collector run number, not newest successful run.
A newer terminal failure/partial/legacy run prevents fallback to older success.
A newer active successor is intentionally not a completed candidate: the previous
healthy immutable bounded snapshot may still be selected while continuous collection
runs. Selected run/attempt and newest-terminal choice are rechecked at the end to
reject a rerun/new completion racing downloads. Observation/run freshness is at
most 24 hours, no future receipt timestamps, source date today/yesterday JST.

Metadata binds fixed repo/workflow/default branch/event/run/attempt, exact job and
step conclusions, unique unexpired artifact ID/run/head and SHA256 of archive bytes.
Original scraper/save outcomes come from the artifact produced by the pinned
workflow's explicit `steps.*.outcome` guards—not from masked API step conclusions.
Artifact ZIP accepts exactly `saved-collection.json`, bounded size, no extra entries.
Receipt/ledger/checkpoint bytes come from the immutable saved Git commit via
GitHub contents API, with blob/size checking; no mutable main fallback.

Then check out **selection.tracker_commit**, generate canonical inventory using
unchanged `generator/inventory_snapshot.py`, and finalize:

```sh
python local-auto-input-contract/resolve_automatic_inputs.py finalize-context \
  --selection work/auto-selection/resolved-inputs.json \
  --inventory '<exact inventory_snapshot.py output>' --output context.json
```

Reads workflow identity from `GITHUB_ACTIONS=true`, `GITHUB_SHA`, `GITHUB_RUN_ID`,
`GITHUB_RUN_ATTEMPT`; the workflow/runner must verify actual generator checkout SHA.
Emits exactly: `synthetic`, `tracker_commit`, `generator_commit`, `run_id`,
`run_attempt`, `generation`, `prev_release_digest`, `expected_date`, `inventory_digest`.
Collector run provenance stays in the separate selection receipt, never overwrites
generator run IDs. `inventory_digest` is SHA256 of exact unchanged inventory bytes.
The parent workflow wires this to `local-release-contract-integration/run_candidate.py`
and its independent validation job; all evidence/population/relation/promotion gates
remain required. Files alone are not authentication: only consume this receipt from
the trusted immediately preceding resolver step in the same job, not user-provided JSON.

## Lineage / authority

Fixed actual live site is `https://mametarogg.github.io/boopadb`. Existing valid
`release-manifest.json` supplies generation+1 and predecessor SHA256 of exact bytes.
Only a positive HTTP404 permits first-release fallback; failed/unknown reads never
mean absence. First release requires explicitly hash-pinned baseline JSON plus
matching live index/item Git blobs and snapshot bytes/count/date. Malformed present
release fails, never falls back. Live-manifest reread brackets materialization and
rejects concurrent change. Promotion must still re-read live lineage immediately
before use under existing serialization; a stale candidate cannot promote.

`select-input.cjs` is the underlying offline consistency adapter, tested separately.
Its raw result says `offline-consistency-only`; only the executable resolver after
all authenticated reads/checks stamps `authenticated-github-read-and-live-lineage`.
Neither result is independent QA, catalog completeness or publication authorization.

## Existing-token access — UNKNOWN until authorized smoke read

The consuming workflow needs existing `GITHUB_TOKEN` **contents:read and actions:read
on the tracker repository**. A BoopaDB-hosted token is scoped to its hosting repo;
public repository contents do **not** establish artifact-download access. This task
has not executed an artifact API request with a real token, so access is **unverified**,
not observed denied and not claimed impossible. HTTP401/403/404 fail explicitly,
without alternate unauthenticated receipt, latest-main fallback, new PAT or credential.

Before enabling, an authorized smoke read must establish access to the exact tracker
run/job/artifact endpoints and archive using the existing token in the intended
workflow. If unavailable, deployment needs an authorized existing execution/app
access arrangement; this deliverable does not create credentials or broaden access.

## Verification

```sh
node --test local-auto-input-contract/tests/*.test.cjs
python -m unittest discover -s local-auto-input-contract/tests -p 'test_*.py' -v
python local-auto-input-contract/build_proposal.py
```

At this revision: **39 JS + 40 Python focused tests pass**, plus full upstream baseline and patched suites **297/297 each**. Python tests cover mocked
GitHub/live success and refusal, wrong repo/workflow/attempt, changed code/source gates,
rebase changes, newest-run race, partial/failed runs, token forwarding/leaks, artifact
digest/ZIP ambiguity, lineage/freshness, and exact builder context. JS tests cover
receipt semantics, exact saved Git commit vs newer HEAD, and lineage. Test logs are
`test-results.txt`, `resolver-test-results.txt`. JS/shell/Python syntax and patch
application checks pass. Independent review lives in sibling
`local-auto-input-contract-independent-review/`.

The existing full tracker npm suite now passes **297/297 baseline and 297/297 patched**, using existing dependencies only and a network-denying preload. See `regression/REPORT.md` and retained logs for the exact-source EOF correction, initial timeout regression and final readback. The proposal now reduces checkout timeout **20→15 minutes** to fund five new 1-minute steps while preserving total 359 / <360; real checkout tolerance is unverified. Production Node20, actual GitHub permission/artifact/run behavior, actual live fetch, real push/readback, scheduled execution and publication QA are **not run**.
Tests create only disposable local synthetic repositories with no remotes. No
writes to existing repositories or external state were attempted.
