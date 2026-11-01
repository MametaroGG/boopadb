#!/usr/bin/env python3
"""[DRAFT-ADAPTATION] Typed binding validator for BoopaDB workflow manifests.

Proposed checked-in location: generator/scripts/validate_bindings.py

Why this exists (dot v2 review point 3): v2 checked several bindings
only "when present" (e.g. attestation tracker_commit, snapshot
max_date) and the promote workflow had a fallback for a missing
attestation commit. Presence-only checks let incomplete evidence pass.
This validator makes every manifest contract MANDATORY and TYPED:
a missing field, a wrong type, a malformed hash/date, a duplicate
JSON key, or a ledger with duplicate / normalization-colliding paths
is a hard failure.

Usage:
    validate_bindings.py KIND FILE [FILE ...]

Kinds: attestation, run-manifest, qa-archive, validation-results,
review-record, release-manifest, baseline-pin, evidence-records,
snapshot-manifest, input-inventory-summary, prepared-input,
workflow-pins, ledger
("ledger" covers input-inventory.json and hash-ledger.json:
a non-empty {path: sha256} object with confined paths.)

v4 additions (dot v3 review points 1, 3, 4): the input inventory
commitment (inventory_digest / inventory_count) is a REQUIRED typed
field of attestation, run-manifest, validation-results,
release-manifest and prepared-input, so the same digest can be
asserted end-to-end; run-manifest / release-manifest / validation-
results carry prev_release_digest (the generation lineage anchor);
run-manifest and baseline-pin carry the relations bundle+approval
binding set; the review record binds the qa-approval environment
and the pinned workflow blob SHAs; workflow-pins has its own spec.

v5 additions (dot v4 review point 1): evidence-records accepts two
record shapes — verified_thumbnail (correction fields) and
current_price_projection (package_sha256 + as_of) — and the
projection-declaration spec (applied / package_sha256 / as_of)
pins the generator's declaration that a projection is applied.
Presence-when-applied is enforced by check_projection.py's gate,
not by this kind check alone.

v6 additions (dot v5 review point 2): the projection-declaration
spec also requires payload_sha256 (canonical digest of the actual
site payload) and applied_items (the exact applied item set), so
the gate binds declaration, payload, embedded configuration and
recomputation to one another.

Exit code 0 = all files satisfy their kind's contract; 1 otherwise.
Extra fields are tolerated (forward compatibility) but never required
ones; equality BETWEEN manifests is asserted by the calling gate,
using load_typed() from this module.
"""

import datetime as dt
import json
import re
import sys
import unicodedata
from pathlib import Path, PurePosixPath


class BindingError(Exception):
    pass


# ---------------------------------------------------------------------------
# Strict JSON loading: duplicate object keys are an error, not last-wins.
# ---------------------------------------------------------------------------

def _no_dup_pairs(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise BindingError(f"duplicate JSON key: {key!r}")
        obj[key] = value
    return obj


def load_strict_json(path):
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise BindingError(f"cannot read {path}: {exc}")
    try:
        return json.loads(text, object_pairs_hook=_no_dup_pairs)
    except BindingError:
        raise
    except ValueError as exc:
        raise BindingError(f"{path}: invalid JSON: {exc}")


# ---------------------------------------------------------------------------
# Scalar type checkers. Each returns True/False; bool is NOT an int here.
# ---------------------------------------------------------------------------

def _is_str(v):
    return isinstance(v, str) and len(v) > 0


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _is_sha256(v):
    return isinstance(v, str) and re.fullmatch(r"[0-9a-f]{64}", v) is not None


def _is_sha40(v):
    return isinstance(v, str) and re.fullmatch(r"[0-9a-f]{40}", v) is not None


def _is_digits(v):
    return isinstance(v, str) and re.fullmatch(r"[0-9]+", v) is not None


def _is_date(v):
    if not isinstance(v, str):
        return False
    try:
        parsed = dt.date.fromisoformat(v)
    except ValueError:
        return False
    return parsed.isoformat() == v


def _is_datetime(v):
    if not isinstance(v, str):
        return False
    try:
        dt.datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _is_url(v):
    return isinstance(v, str) and v.startswith("https://")


def _is_bool(v):
    return isinstance(v, bool)


CHECKERS = {
    "str": _is_str,
    "int": _is_int,
    "sha256": _is_sha256,
    "sha40": _is_sha40,
    "digits": _is_digits,
    "date": _is_date,
    "datetime": _is_datetime,
    "url": _is_url,
    "bool": _is_bool,
}


def _check(spec, value, where):
    """spec: a checker name, or ["list", subspec], or ["object", {..}]."""
    if isinstance(spec, str):
        if not CHECKERS[spec](value):
            raise BindingError(f"{where}: expected {spec}, got {value!r:.80}")
        return
    kind, sub = spec
    if kind == "list":
        if not isinstance(value, list):
            raise BindingError(f"{where}: expected list, got {type(value).__name__}")
        for i, item in enumerate(value):
            _check(sub, item, f"{where}[{i}]")
        return
    if kind == "object":
        if not isinstance(value, dict):
            raise BindingError(f"{where}: expected object, got {type(value).__name__}")
        for field, fspec in sub.items():
            if field not in value:
                raise BindingError(f"{where}: missing required field {field!r}")
            _check(fspec, value[field], f"{where}.{field}")
        return
    raise BindingError(f"internal: unknown spec {spec!r}")


# ---------------------------------------------------------------------------
# Ledger contract (input inventory / site hash ledger).
# ---------------------------------------------------------------------------

def check_ledger(obj, where="ledger"):
    if not isinstance(obj, dict) or not obj:
        raise BindingError(f"{where}: ledger must be a non-empty object")
    folded = {}
    for rel, digest in obj.items():
        if not isinstance(rel, str) or not rel:
            raise BindingError(f"{where}: ledger path must be a non-empty string")
        pp = PurePosixPath(rel)
        if pp.is_absolute() or ".." in pp.parts or "" in pp.parts:
            raise BindingError(f"{where}: unconfined ledger path: {rel!r}")
        if rel == ".git" or rel.startswith(".git/"):
            raise BindingError(f"{where}: .git path in ledger: {rel!r}")
        if not _is_sha256(digest):
            raise BindingError(f"{where}: bad sha256 for {rel!r}")
        key = unicodedata.normalize("NFC", rel).casefold()
        if key in folded:
            raise BindingError(
                f"{where}: normalization/case collision: {rel!r} vs {folded[key]!r}")
        folded[key] = rel
    return obj


# ---------------------------------------------------------------------------
# Manifest contracts. EVERY field listed is required and typed.
# These specs are the contract the [DRAFT-ADAPTATION] entry points
# (attest_snapshot.py etc.) must satisfy at migration time.
# ---------------------------------------------------------------------------

_EVIDENCE_RECORD = ["object", {
    "item_id": "str",
    "kind": "str",
    "corrected_url": "url",
    "proof_sha256": "sha256",
    "confirmed_at": "datetime",
    "applies_when": "str",
}]

# A price-projection evidence record (v5, dot v4 review point 1).
# It does NOT carry thumbnail fields: it binds an item to the
# projection package whose contract check_projection.py verifies.
# The package_sha256 must equal the declaration's package_sha256
# and the digest of the actual package bytes.
_PROJECTION_EVIDENCE_RECORD = ["object", {
    "item_id": "str",
    "kind": "str",
    "package_sha256": "sha256",
    "as_of": "datetime",
}]

# The relations bundle + approval binding set, pinned from the
# producer config's build_inputs (producer-install/config/
# producer-config.json, itself SHA-pinned). The candidate's build
# records the hashes of the ACTUAL files it consumed; validate
# asserts them against the pinned set in baseline-pin.
_RELATIONS_BINDING = ["object", {
    "relations_bundle_manifest_sha256": "sha256",
    "relations_approval_sha256": "sha256",
    "relation_search_bundle_manifest_sha256": "sha256",
    "relation_search_approval_sha256": "sha256",
    "supplement_bundle_manifest_sha256": "sha256",
    "supplement_approval_sha256": "sha256",
}]

SPECS = {
    "attestation": {
        "expected_date": "date",
        "tracker_commit": "sha40",
        "completion_scope": "str",
        "inventory_digest": "sha256",
        "inventory_count": "int",
    },
    "run-manifest": {
        "run_id": "digits",
        "run_attempt": "digits",
        "tracker_commit": "sha40",
        "generator_commit": "sha40",
        "expected_date": "date",
        "product_count": "int",
        "site_files": "int",
        "generation": "int",
        "inventory_digest": "sha256",
        "inventory_count": "int",
        "prev_release_digest": "sha256",
        "relations_binding": _RELATIONS_BINDING,
    },
    "qa-archive": {
        "archive": "str",
        "sha256": "sha256",
        "bytes": "int",
    },
    "validation-results": {
        "status": "str",
        "run_id": "digits",
        "tracker_commit": "sha40",
        "generator_commit": "sha40",
        "expected_date": "date",
        "product_count": "int",
        "generation": "int",
        "qa_archive": "str",
        "qa_archive_sha256": "sha256",
        "inventory_digest": "sha256",
        "prev_release_digest": "sha256",
        "gates": ["list", "str"],
        "baseline_pin": ["object", {
            "baseline_commit": "sha40",
            "product_count": "int",
            "max_date": "date",
            "generation": "int",
        }],
    },
    "review-record": {
        "schema": "int",
        "source_run_id": "digits",
        "artifact_digest": "sha256",
        "verdict": "str",
        "qa_run_id": "digits",
        "qa_report_ref": "str",
        "reviewer": "str",
        "reviewed_at": "datetime",
        "environment": "str",
        "source_workflow_blob": "sha40",
        "qa_workflow_blob": "sha40",
    },
    "release-manifest": {
        "schema": "int",
        "generation": "int",
        "source_date": "date",
        "product_count": "int",
        "tracker_commit": "sha40",
        "generator_commit": "sha40",
        "run_id": "digits",
        "inventory_digest": "sha256",
        "prev_release_digest": "sha256",
    },
    "baseline-pin": {
        "schema": "int",
        "baseline_commit": "sha40",
        "product_count": "int",
        "max_date": "date",
        "index_html_blob": "sha40",
        "item_html_blob": "sha40",
        "generation": "int",
        "baseline_prev_release_sentinel": "sha256",
        "relations_binding": _RELATIONS_BINDING,
        "evidence": ["object", {
            "thumbnail_correction_2625416": ["object", {
                "item_id": "str",
                "corrected_url": "url",
                "proof_sha256": "sha256",
                "confirmed_at": "datetime",
                "applies_when": "str",
            }],
        }],
    },
    "evidence-records": {
        "schema": "int",
        # "records" is validated per kind by validate_typed's
        # evidence-records special case below (thumbnail shape vs
        # projection shape); a single list spec cannot express the
        # union.
    },
    "projection-declaration": {
        "applied": "bool",
        "package_sha256": "sha256",
        "as_of": "datetime",
        # v6 (dot v5 review point 2): the declaration also binds the
        # ACTUAL site payload (canonical digest of
        # site/current-price-projection.json) and the exact applied
        # item set, so the gate can require payload + embedded
        # config + declaration + recomputation to agree exactly.
        "payload_sha256": "sha256",
        "applied_items": ["list", "str"],
    },
    "snapshot-manifest": {
        "validation": ["object", {
            "rows": "int",
            "max_date": "date",
        }],
    },
    "input-inventory-summary": {
        "files": "int",
        "non_json_files": ["list", "str"],
        "inventory_digest": "sha256",
        "inventory_count": "int",
    },
    "prepared-input": {
        "inventory_digest": "sha256",
        "tracker_commit": "sha40",
        "expected_date": "date",
    },
    "workflow-pins": {
        "schema": "int",
        "workflows": ["object", {
            "boopadb-daily.yml": "sha40",
            "boopadb-promote.yml": "sha40",
            "boopadb-qa-review.yml": "sha40",
        }],
    },
}


# ---------------------------------------------------------------------------
# Evidence kinds (v5, dot v4 review point 1): every evidence type
# the generator/promotion actually relies on is enumerated in
# DESIGN.md. A candidate carrying an evidence record of ANY other
# kind is REJECTED — unsupported features are refused, not passed
# through. AND the kind check alone is not enough: when a price
# projection is applied, check_projection.py's gate REQUIRES a
# current_price_projection record plus a verified package — a
# thumbnail-only list must NOT pass in that case.
# ---------------------------------------------------------------------------

EVIDENCE_KINDS_ALLOWED = frozenset(
    {"verified_thumbnail", "current_price_projection"})


def check_evidence_kinds(evidence_records_obj, where="evidence-records"):
    records = evidence_records_obj.get("records", [])
    for i, rec in enumerate(records):
        kind = rec.get("kind")
        if kind not in EVIDENCE_KINDS_ALLOWED:
            raise BindingError(
                f"{where}: records[{i}] has unsupported evidence kind "
                f"{kind!r} (allowed: {sorted(EVIDENCE_KINDS_ALLOWED)}); "
                "unlisted evidence types are rejected, not passed through")
    return evidence_records_obj


def validate_typed(kind, obj, where="<memory>"):
    if kind == "ledger":
        return check_ledger(obj, where)
    spec = SPECS.get(kind)
    if spec is None:
        raise BindingError(f"unknown manifest kind: {kind!r}")
    if not isinstance(obj, dict):
        raise BindingError(f"{where}: expected a JSON object for kind {kind!r}")
    for field, fspec in spec.items():
        if field not in obj:
            raise BindingError(f"{where} ({kind}): missing required field {field!r}")
        _check(fspec, obj[field], f"{where} ({kind}).{field}")
    if kind == "evidence-records":
        # Per-kind record shapes (v5): thumbnail records carry the
        # correction fields; projection records bind an item to a
        # projection package. Any other kind is rejected here as
        # well as by check_evidence_kinds.
        records = obj.get("records")
        if not isinstance(records, list):
            raise BindingError(f"{where} (evidence-records): "
                               f"missing required field 'records' as a list")
        for i, rec in enumerate(records):
            if not isinstance(rec, dict):
                raise BindingError(
                    f"{where} (evidence-records).records[{i}]: "
                    f"expected object")
            rec_kind = rec.get("kind")
            if rec_kind == "verified_thumbnail":
                _check(_EVIDENCE_RECORD, rec,
                       f"{where} (evidence-records).records[{i}]")
            elif rec_kind == "current_price_projection":
                _check(_PROJECTION_EVIDENCE_RECORD, rec,
                       f"{where} (evidence-records).records[{i}]")
            else:
                raise BindingError(
                    f"{where} (evidence-records).records[{i}]: "
                    f"unsupported evidence kind {rec_kind!r}")
    return obj


def load_typed(kind, path):
    return validate_typed(kind, load_strict_json(path), str(path))


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    kind, files = argv[1], argv[2:]
    failed = False
    for f in files:
        try:
            load_typed(kind, f)
            print(f"typed OK [{kind}]: {f}")
        except BindingError as exc:
            print(f"::error::{exc}")
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
