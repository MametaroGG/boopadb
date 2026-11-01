# v7 release-contract integration — local, not deployed

This is executable build-artifact plumbing, not another workflow design and not
an authority issuer. `release_contract.py` joins the previously isolated R2
archive transport to the already-reviewed v7 run/release/evidence contracts.
Original R2, v7 and production generator files remain unchanged.

## What it does

`prepare` consumes a newly generated site and its four bound producer/prepared
input records. It copies them to a private staging tree, adds a release manifest,
run manifest and exact evidence enumeration, binds the six ACTUAL relation
manifest/approval file hashes to the caller-pinned baseline, and runs unchanged
v7 static UI and current-time projection gates. It packs one deterministic
archive using the unchanged R2 packer, and runs the receiving validator against
that exact archive before making a new artifact directory visible.

`validate` requires the caller's independent expected context and baseline pin
hash again, rechecks the actual tracker `data/` and `meta/` bytes, extracts safely,
checks exact site inventory and all manifests, and reruns UI/projection checks.
No successful destination is exposed on validation failure. Existing source
site/work/output trees are never overwritten.

The new output has v7's `site-release.tar` + `work/` layout, including:

- attestation.json, prepared-input.json, input-inventory.json,
  input-inventory-summary.json (original bytes)
- hash-ledger.json, qa-archive.json
- run-manifest.json, evidence-records.json
- contract-context.json (additional explicit synthetic/run-input boundary)
- optional unchanged projection-package.json, projection-declaration.json,
  projection-evidence/<sha256>

The archived site additionally contains release-manifest.json. No original
snapshot manifest or rendered page is rewritten. No projection is dropped,
refreshed or synthesized. Undeclared projection markers anywhere in the site
are rejected by the original v7 gate. No new clock override is available.

## Explicit inputs

Context JSON must contain exactly:

```
synthetic: boolean
tracker_commit: full lowercase SHA40
generator_commit: full lowercase SHA40
run_id: positive decimal string
run_attempt: positive decimal string
generation: positive integer
prev_release_digest: lowercase SHA256
expected_date: YYYY-MM-DD
inventory_digest: SHA256 of the exact input-inventory.json bytes
```

The producer attestation, prepared-input and snapshot must all carry explicit
`fixture` booleans matching `synthetic`. A production context cannot consume
fixture inputs. A synthetic context never becomes a deployable result.

`relation-inputs.json` maps precisely these six keys to actual local paths
(relative paths resolve from that JSON's directory):

```
relations_bundle_manifest_sha256
relations_approval_sha256
relation_search_bundle_manifest_sha256
relation_search_approval_sha256
supplement_bundle_manifest_sha256
supplement_approval_sha256
```

These must be the files actually passed to the generator. Their digests must
match the independently pinned baseline. The adapter does not invent approval
files or prove the signer's authority; existing review/production gates remain.

The source work directory must contain the four R2 records. Projection inputs,
when applied, must already be supplied in the exact v7 shape. The review-only
evidence-builder envelope is rejected; it is never unwrapped here. Passing the
unchanged v7 semantic proof verifier is not a new grant of reviewer authority.

## CLI

```
python release_contract.py prepare \
  --site NEW_GENERATED_SITE --work BUILD_WORK --dest NEW_BUILD_ARTIFACT \
  --context EXPECTED_CONTEXT.json \
  --baseline-pin REVIEWED_BASELINE_PIN.json --baseline-sha256 EXPECTED_PIN_SHA256 \
  --relation-inputs ACTUAL_RELATION_INPUTS.json --tracker-root FROZEN_TRACKER

python release_contract.py validate \
  --artifact NEW_BUILD_ARTIFACT --dest NEW_CHECKED_SITE \
  --context EXPECTED_CONTEXT.json \
  --baseline-pin REVIEWED_BASELINE_PIN.json --baseline-sha256 EXPECTED_PIN_SHA256 \
  --relation-inputs ACTUAL_RELATION_INPUTS.json --tracker-root FROZEN_TRACKER
```

All destinations' parents must already exist. `prepare` refuses a source already
containing a release/run/evidence contract rather than overwriting its lineage.
Both commands print a machine-readable report with `deployable: false` and an
explicit list of facts they do **not** establish.

## Remaining production steps, not silently bypassed

- Verify actual checkout identities and collector completion, and select the
  completed tracker commit, exact next generation and live predecessor digest.
  This adapter accepts those explicit values; it does not select them or claim
  that inventory integrity proves collector completion. The separate selection
  adapter owns that stage, and promote must recheck live currentness.
- Run canonical snapshot/search-core validation and browser/runtime QA against
  the exact archived candidate. Static UI gate success is not browser acceptance.
- Supply genuinely current authorized price proof if projection is used, and
  keep established reviewer-authority requirements. No expired fixture works
  around this requirement.
- Preserve v7 independent QA, workflow identity, protection and promote gates.
  This module does not generate `validation-results.json`, `qa-review-record.json`
  or a publishable receipt. Those stages must run, not be asserted here.
- Obtain the existing required authorization before any workflow placement,
  activation/run, repository mutation, settings change or production publication.

The old disabled fixture workflow is unchanged; this adapter does not activate
scheduling. Full unattended updating still needs completion-to-commit selection
and production acceptance/authorized migration. Drive unattended upload and
additional optional hardening are not dependencies of this contract adapter.

## Local tests

```
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -v
```

Tests deliberately use synthetic source/work/context/relations while copying the
existing v7 baseline HTML/pin bytes as test references. They are contract tests,
not real full-dataset builds, production approval or a substitute for unchanged
canonical generator and browser acceptance. Historical evidence timestamps are
not renewed. See RESULTS.log for the actual executed result.

## End-to-end executable entrypoint (added in this integration)

`run_candidate.py` now connects **actual canonical generation** to the above
contract adapter and `validation_job.py`, rather than leaving these as standalone
building blocks. The canonical generator is copied unchanged from R2 and its full
file inventory is checked before any generator command executes.

```
python run_candidate.py \
  --dest NEW_RUN_DIRECTORY \
  --context RESOLVED_CONTEXT.json \
  --baseline-pin REVIEWED_BASELINE_PIN.json --baseline-sha256 EXPECTED_PIN_SHA256 \
  --relation-inputs ACTUAL_RELATION_INPUTS.json \
  --tracker-root FROZEN_TRACKER \
  --generation-config GENERATION_INPUTS.json
```

It runs inventory_snapshot → attest_snapshot → prepare_inputs → build_site,
then release-contract prepare/revalidate, then the full machine validation job.
Every actual generator command gets a saved log. Failures retain `FAILED.txt`
and diagnostics; success produces `build-artifact/`, `qa-artifact/`, `RESULT.json`.
The run must have a new destination. No GitHub/HTTP transport is implemented or
called by this entrypoint.

The separate automatic-input selection stage supplies the context. In production
it must obtain authenticated collector provenance, completed immutable commit
and actual current live lineage; merely calling this runner does not prove those
facts. Collector metadata belongs in its separate provenance receipt, not in the
exact context object. The generator's run_id/run_attempt must remain the current
build workflow's identity, not be overwritten with the collector's identifiers.

Generation config has exactly these keys; paths are relative to its own file:

```
relations_bundle, relations_approval
relation_search_bundle, relation_search_approval
supplement_bundle, supplement_approval
daily_coverage_file, daily_target_date
projection_work, projection_package_sha256
presentation_proof, presentation_sha256
```

All three relation pairs are mandatory and passed to the real generator. The
approval paths must equal those in relation-inputs.json, and bundle inventories
must match the actual bytes. Production refuses explicitly local/test/synthetic
approval files. No production approvals are created. The static package is the
unchanged pinned generator/pinned-static.

Other pairs must be explicitly null together if not used, or explicitly supplied
together. This is not authorization to remove an existing required feature.
Price-feature preservation still requires the genuine intended projection and
presentation inputs; the no-projection synthetic case does not establish that.
`projection_work` contains projection-package.json and content-addressed
projection-evidence/. The package's canonical digest is checked before generation.
After the generator actually succeeds, the runner derives the declaration's
payload digest/items/as_of from that actual generated payload and snapshot.
These are transport bindings, not new observations or approval. No evidence
bytes, observation timestamps, expiry or claimed reviewer statuses are rewritten.

## Executable validation job and QA artifact

The earlier statement that release_contract alone does not issue validation
results still holds. **validation_job.py now supplies that separate executable
stage**: it invokes release-contract validation, pins the hero executable before
running it, and executes the unchanged canonical snapshot/search-core validator.
Only when every actual check succeeds does it write normal v7
validation-results.json (`status: passed`) and stage `qa-artifact/evidence/`.
The site-release.tar bytes are copied unchanged, never rebuilt/repacked.

```
python validation_job.py --artifact BUILD_ARTIFACT --dest NEW_QA_ARTIFACT \
  --context EXPECTED_CONTEXT.json \
  --baseline-pin REVIEWED_BASELINE_PIN.json --baseline-sha256 EXPECTED_PIN_SHA256 \
  --relation-inputs ACTUAL_RELATION_INPUTS.json --tracker-root FROZEN_TRACKER
```

Synthetic status and `deployable: false` remain explicit even when machine checks
pass. No qa-review-record is generated. Browser QA, reviewer authority, real
workflow identity/protection and promote/live-lineage checks still remain.

The actual end-to-end test uses freshly created synthetic raw histories and
explicit local-test-only relation approvals. It exercises all three relation
features, real generator CLIs and full machine validation; no real price proof is
renewed and no external service is contacted. Separate contract tests exercise
current synthetic projection and unchanged expired-proof refusal.
