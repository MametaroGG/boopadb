# Automatic update workflow wiring — local, OFF, uninstalled

## Delivered

`boopadb-daily.OFF.yml` replaces v7's unimplemented daily-build adaptations with
real executable entrypoints. It is **outside `.github/workflows`**, has **no
schedule event**, and **both jobs are literally disabled**. Nothing was installed,
dispatched, uploaded, deployed, or published. Original v7 daily, QA-review and
promote files remain byte-identical; `V7-SOURCE.json` records their original
provenance paths, unchanged source hashes and portable bundled references in
`evidence/v7-originals/`. Audit verifies those exact bundled bytes; if original
locations are available, it additionally rechecks them. Consumers do not need the
original handover directory.

The code is complete local wiring, **not a claim that production inputs/access
are available**. The legacy collector cannot yet supply the required receipt.

## Concrete execution and layout

The layout in the eventual reviewed generator checkout must preserve these three
sibling directories (this deliverable does not install them):

- `local-auto-workflow-wiring/` — this workflow, shell and typed driver;
- `local-auto-input-contract/` — actual resolver, Node selector and receipt module;
- `local-release-contract-integration/` — actual runner, validation job, contract
  adapter and its complete pinned generator/validator dependencies.

`run_stage.sh` is the actual workflow shell entrypoint. It quotes all environment
arguments and never evaluates input as shell code. `workflow_driver.py` performs:

1. `resolve`: verify generator checkout HEAD equals `GITHUB_SHA`, verify complete
   canonical generator inventory, validate explicit config and baseline digest;
   invoke `resolve_automatic_inputs.py resolve` with real supported CLI arguments.
   Resolver chooses the newest terminal eligible bounded collector observation,
   pins its successful saved commit, and reads actual live release lineage.
   No manual/latest-main SHA, guessed generation, or fallback receipt is allowed.
2. Workflow checks out **only** validated `selection.tracker_commit`, detached by
   the checkout action with credentials not persisted.
3. `build`: verify actual tracker HEAD, run unchanged canonical
   `inventory_snapshot.py`, then real resolver `finalize-context`. Require the
   exact **nine keys**: `synthetic`, `tracker_commit`, `generator_commit`, `run_id`,
   `run_attempt`, `generation`, `prev_release_digest`, `expected_date`,
   `inventory_digest`. This production path requires `synthetic:false`; collector
   run identity is never substituted for generator workflow run identity.
4. Invoke actual `run_candidate.py` with its exact CLI. It recomputes inventory,
   generates through the unchanged canonical scripts, creates the v7 release
   contract, executes all machine gates and exposes `candidate/build-artifact/`
   and its prechecked candidate QA directory only after actual checks.
5. Upload the immutable build directory and separate minimal resolver/config
   binding handoff. Each successful artifact uses one explicit root directory.
   Download into the separate `validate` job **by exact same-run artifact ID**, not
   mutable name, latest run, or an arbitrary supplied artifact.
6. The separate job checks out the same immutable generator/tracker, recomputes
   canonical inventory and exact context, and invokes real `validation_job.py`
   against the downloaded archive. Only success uploads `qa-artifact/`:
   `site-release.tar` plus `evidence/*.json` and any unchanged projection evidence.
   The tar is byte-identical, never regenerated or repacked in handoff.

Build/selection/failure names include run attempt. Final QA name deliberately
remains `boopadb-qa-<run_id>` for unchanged v7 QA-review/promote compatibility.
If a prior attempt already uploaded that QA name, a rerun cannot replace it:
`overwrite:false` makes that attempt fail closed. A new authorized run is needed;
this code neither deletes existing artifacts nor manufactures a replacement.

`failure-diagnostics.json` records only stage/run/attempt/error class. Failure
uploads list explicit safe diagnostics and generator logs, **not the resolver
working cache**. No token or signed URL is intentionally persisted/uploaded.

## v7 safeguards retained, not replaced by assertions

| v7 daily obligation | Executed implementation |
| --- | --- |
| Typed mandatory manifests, run/commit/generation/predecessor/inventory bindings | `release_contract.inputs/core_bindings/validate` |
| Source freshness, future/date regression, pinned-baseline population | canonical attestation plus `release_contract.core_bindings` |
| Deterministic archive hash/size, safe extraction, exact ledger/tree equality | unchanged R2 transport invoked by release contract |
| Actual every-file tracker inventory, symlink/collision refusal | canonical inventory plus release-contract tracker inventory |
| Canonical snapshot and exact search-core recombination | `validation_job.py` invokes pinned `validate_snapshot.py` |
| Static UI, original thumbnail proof, evidence kinds | unchanged v7 `gate_ui.py` plus release-contract evidence bindings |
| Projection raw histories, selected variant/price, actual generated payload, expiry at current evaluation time | unchanged v7 `check_projection.py`; **no clock override, renewal or omission fallback** |
| Relations/search/supplement actual bundle and approval hashes | runner plus release contract require all three genuine pairs |
| Immutable QA handoff and unchanged archived hidden files | exact tar copy, immutable upload, exact artifact-ID download |
| Human QA and publication authority | **not issued here**; existing QA-review and promote gates remain mandatory |

A successful static machine validation is not browser/runtime acceptance or human
approval. No `qa-review-record.json`, authority proof or publication permission is
created. No deploy job, pages write, id-token write, PAT, new credential, Drive
integration or promotion-gate weakening was added. Existing publication denials
are unaffected.

## Typed production inputs still genuinely required

`production-config.EXAMPLE.json` is intentionally **invalid** until real values
exist; it is not a runnable synthetic production example. Copying/renaming the
producer proposal is not review or authorization. The driver rejects proposal,
example and placeholder configured filenames, missing files, out-of-checkout
paths, duplicate/unknown keys and a baseline digest mismatch.

The real `production-config.json` must have exactly:

- `schema`: integer `1`;
- `baseline_pin`: relative path to the actual independently reviewed v7 baseline;
- `baseline_sha256`: SHA256 of those exact reviewed bytes;
- `producer_pin`: relative path to the actually reviewed/installed producer
  workflow/source pin, not the current proposal;
- `relation_inputs`: relative path to all six actual bundle-manifest/approval
  bindings consumed by the runner;
- `generation_config`: relative path to actual generation inputs in the runner's
  exact 12-key schema (three relation pairs, daily coverage/date,
  projection-work/package digest, presentation proof/digest).

Paths resolve relative to this JSON and must remain inside the immutable checkout.
The production facts not yet verified/available to this candidate are: authorized receipt-producer migration;
a real eligible bounded collection/save receipt and exact run/attempt artifact;
actual reviewed producer pins; genuine relation approvals; any required **current**
price/presentation evidence; authenticated live lineage/baseline bytes; browser QA;
and owner authorization for installation/activation. Existing approvals or baseline
material may already be held by Muse; they were not supplied/verified for this
candidate, and their nonexistence is not claimed. None is fabricated by tests.
The workflow has a committed config default for a future separately authorized
schedule; adding a schedule alone cannot bypass either literal false job lock.

## Cross-repository access: a real deployment boundary

Read-only permissions are only `contents:read` and `actions:read`. Public tracker
Git content is not equivalent to permission to download its Actions artifact.
GitHub documents that `GITHUB_TOKEN` is limited to the repository containing its
workflow. Artifact listing/get metadata allow public unauthenticated reads;
the artifact **download** endpoint separately requires Actions read access.
Therefore a workflow hosted in BoopaDB must **not assume** its default token can
download the tracker repository's receipt artifact. The resolver refuses denied,
missing or ambiguous evidence; it does not fall back to latest main or weaken
provenance. No production token access probe was run in this local test. Therefore the actual
access outcome remains **unverified**, not an observed denial or a conclusive
architecture incompatibility. Before activation, an owner-authorized read-only
probe must test the intended repository job token against the exact tracker run
metadata and artifact-download endpoint, confirming repository/run/attempt and
digest bindings without logging the token or signed URL. A denied probe stops
activation; it does not authorize a new token or repository migration.

A production repository-placement/access design needs explicit review while
retaining the no-new-credential constraint. Co-locating authorized tooling with
its producer is an architecture option, not an action taken or a permission
bypass. No alternative token, PAT, App install or privilege escalation was added.

Sources checked read-only on 2026-11-01:
- [GitHub token repository scope](https://docs.github.com/en/actions/concepts/security/github_token)
- [Artifact download versus metadata permissions](https://docs.github.com/en/rest/actions/artifacts#download-an-artifact)

## External action pins

`ACTION-PINS.json` and `evidence/` hold actual official GitHub ref API responses
and `action.yml` bytes fetched at those commits, not guessed SHA strings.
Existing v7 action majors were preserved: checkout v4, setup-python v5,
upload-artifact v4 and download-artifact v4. All four tag refs were direct commit
objects (no annotated tag peeling was needed). No action code was installed or
executed here. `audit_workflow.py` checks all 13 uses against those pins and checks
every supplied `with` field against the fetched pinned action's actual inputs.

## Reproducible local checks and their limits

From workspace root:

```sh
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s local-auto-workflow-wiring/tests -v
python local-auto-workflow-wiring/audit_workflow.py
```

`TEST-RESULTS.log`: 13 focused tests pass. They execute the real canonical inventory
CLI and real offline finalizer against a local-only Git fixture; mock external
resolver transport/process and downstream runner stages to prove command ordering
and arguments without remote operations. A real shell shim test proves quoted
config input cannot execute injected shell commands. Wrong checkout, malformed
selection, duplicate keys, placeholder config and failed resolver are rejected.
Actual sibling `--help` interfaces are exercised to reject invented CLI flags.

`WORKFLOW-AUDIT.json`: YAML parsed, all shell blocks pass `bash -n`, all 13 action
refs and actual action inputs verified, original v7 workflow bytes unchanged,
only build/validate jobs, read-only permissions, no schedule, literal false locks.
PyYAML is already present and used **only in local audit**, not installed or added
as a production dependency. This is not a GitHub server/actionlint acceptance run.

The sibling release integration owns the separate actual synthetic full-generator
and machine-QA tests. The present orchestration test is not labeled a real
production collection/build, full-dataset build, real Actions run or browser QA.
No live collection, workflow dispatch, upload, install or publication was performed.

Portable audit regression additionally copies this module to an isolated tree with
no original handover directory, passes the audit, and then proves that tampering
with the bundled original promote bytes is rejected.

`FRESH-EXTRACTION-RESULTS.log` records a fresh ZIP extraction of all three
sibling modules into a temporary directory with no `muse-handover` tree: all
13 wiring tests and the complete YAML/action/original-reference audit passed.
