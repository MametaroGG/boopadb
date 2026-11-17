#!/usr/bin/env python3
"""[DRAFT-ADAPTATION] Current-price projection contract verifier.

Proposed checked-in location: generator/scripts/check_projection.py

Implements, faithfully and in order, the contract of the recovered
source ``current_price_projection.py`` (BOOPADB-THREE-REQUESTS-SOURCE-
20261031.zip, source/current_price_projection.py, SHA256
e46fa290c95e11484c2fb88264e3c4bd6e4d895a9d083f20623f1f0ddac30598)
plus its selection rule in ``selected_price_selector.py`` (same
package, SHA256 512e14fd57fb8ed6547c6af5574324f4e54d2e8e8e670da2b01
9aac15ec1249a — a byte-identical copy ships in this package as
generator/scripts/selected_price_selector.py and its hash is
verified before import; a mismatch fails closed).

Contract verified per projection record (see DESIGN.md, v5):
  * projection package digest == expected package digest; schema == 1
  * per item, raw_record_sha256 == canonical digest of the raw price
    history taken from the pinned input snapshot (never from the
    candidate's own copy);
  * the snapshot's source evidence artifact bytes hash to
    source_content_sha256;
  * observed <= as_of < expires; expires - observed is > 0 and
    <= 86400 seconds (max 24 h);
  * snapshot item_id matches the raw record id;
  * per evidence, the seller-declared window contains as_of and the
    evidence source hash equals the snapshot's;
  * the selected variant binds to a raw variation key whose latest
    price equals the selected price;
  * the comparison (regular) price is an int strictly greater than
    the selected price;
  * runtime snapshot bindings satisfy: no future observation,
    artifact digest match, record digest + item id match,
    metadata-except-variations equality, variant set equality,
    historical-prefix preservation, append-only, no future new
    observation, and per-variant price match against the official
    observation.
A record failing ANY check fails the run. A record whose selection
yields selected_sale is not True applies no projection (NOT-APPLIED,
not a failure) — exactly as the contract returns None.

Evidence expiry is NEVER extended or refreshed here: an evaluation
time at or after a record's expires_at fails, including for the
recovered fixture evidence whose expiry is 2026-11-01T01:56:13Z —
after that instant the fixture is stale by design and validation
with a later evaluation time correctly fails. That is expected
behavior, not a defect.

v6 (dot v5 review, 2 remaining points):

  Point 1 — expiry is judged at EVALUATION time with a trustworthy
  clock. The caller workflow supplies --evaluation-time (its own
  current UTC: the daily validate job passes the validate run's
  current UTC; promote passes the promotion run's current UTC).
  ALL expiry / freshness / seller-window judgments inside
  verify_record use that evaluation time. The declaration's as_of
  is the generation-time value the candidate DECLARES: it is still
  recorded and sanity-checked (it must not be later than the
  evaluation time, and no record's observed_at may be later than
  it), but it never drives a freshness judgment — a candidate
  cannot keep expired evidence alive by carrying an old declared
  as_of. In verify mode, --as-of remains accepted and is treated
  as the caller-supplied evaluation time; --evaluation-time is
  the preferred spelling.

  Point 2 — evidence is bound to the ACTUAL generated payload.
  The gate additionally requires, whenever a projection is
  applied:
    * the site payload site/current-price-projection.json (the
      exact object apply_current_price_projection.py produces and
      embeds) exists, has schema 1 and non-empty entries, and its
      canonical digest equals the declaration's payload_sha256;
    * every payload entry is EXACTLY the entry the verified
      contract recomputes for that item from the pinned raw
      history + evidence artifacts (the recomputation reproduces
      the recovered payload byte-for-byte on the real fixture);
    * the applied item set is identical across the payload
      entries, the declaration's applied_items, the recomputed
      applied set, and the current_price_projection evidence
      records (no applied item without a verified record, no
      verified record silently unused);
    * the embedded createCurrentPriceProjection configuration in
      the generated pages matches the payload: index.html and
      item.html MUST carry a non-empty projection script whose
      window.CurrentPrices=createCurrentPriceProjection(<json>)
      argument parses to an object with the same canonical digest
      as the payload, and any other root page carrying the
      projection script id must embed the same configuration.
  An empty/absent payload, an empty projection script, or a
  missing embedded configuration FAILS whenever a projection is
  declared/applied (this closes the v5 test hole where an empty
  <script id="current-price-projection"></script> passed).

v7 (dot v6 review, the ONE remaining point — application
detection must not be skippable):

  * Detection scans the KNOWN generated output inventory (the
    site hash ledger the workflow already produces —
    work/hash-ledger.json, {relative path: sha256} — unioned
    with the files actually present under the site dir) BEFORE
    any "no projection" conclusion: the payload file
    current-price-projection.json ANYWHERE in the output, and
    the bootstrap/usage markers (the projection script id,
    createCurrentPriceProjection, CurrentPrices usage, the
    current-price-refresh lifecycle panel) in EVERY generated
    HTML/JS file — sale.html and every other route included, not
    just index.html/item.html. The old detection looked only at
    index/item and could early-return success, so a
    thumbnail-only declaration could hide a projection applied
    on another route; that early-success path is now reachable
    only after the full inventory scan finds nothing.
  * Embedded-config verification no longer keys on the exact
    script id: any generated page carrying bootstrap/usage
    markers must embed a createCurrentPriceProjection
    configuration that is located by the call itself and whose
    digest matches the site payload — an absent or altered
    script id does not skip verification, and usage without a
    verifiable embedded configuration fails.
  * Any additional payload file elsewhere in the output must be
    the same object as the verified root payload.

Usage (verify one package):
    check_projection.py --package FILE --expected-sha256 HEX
        --evaluation-time ISO --raw-dir DIR --evidence-dir DIR
        [--selector FILE] [--selector-sha256 HEX]
    (--as-of ISO is accepted as an alias for --evaluation-time.)

Usage (gate mode, as wired into the daily validate job and the
promote re-verification): signals that a price projection is
applied are (a) work/projection-declaration.json with applied=true,
(b) work/projection-package.json present, (c) the payload file or
bootstrap/usage markers found ANYWHERE in the known site
inventory (v7: the work/hash-ledger.json file set, unioned with
the site tree — every generated HTML/JS route, not just
index/item), (d) an evidence record of kind
current_price_projection. If ANY signal is present, the
declaration + package + payload binding + full verification at
the caller-supplied --evaluation-time are REQUIRED; a
thumbnail-only evidence list then FAILS (this closes the dot v4
review point 1 gap: the old kind check passed any thumbnail-only
list). Only if the full inventory scan finds no signal does the
gate pass with "projection not applied".
    check_projection.py --gate --work-dir DIR --site-dir DIR
        --raw-dir DIR --evaluation-time ISO
        [--site-ledger FILE] [--selector FILE]
        [--selector-sha256 HEX]
    (--site-ledger defaults to <work-dir>/hash-ledger.json when
    that file exists — both wired workflows place the site hash
    ledger there — and the inventory is unioned with the site
    tree either way.)

Raw history layout: tracker data files, <raw-dir>/<first3>/<id>.json
or <raw-dir>/<id>.json. Evidence artifacts are content-addressed
files named by their SHA256 hex digest.

Exit code 0 = verified (or gate passes with no projection applied);
1 = any contract failure or gate violation.
"""

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

# Pinned hash of the recovered selector (see module docstring).
PINNED_SELECTOR_SHA256 = (
    "512e14fd57fb8ed6547c6af5574324f4e54d2e8e8e670da2b019aac15ec1249a"
)
JST = dt.timezone(dt.timedelta(hours=9))


class ProjectionError(Exception):
    pass


def canonical(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def parse_dt(value):
    if not isinstance(value, str):
        raise ProjectionError(f"expected ISO datetime string, got {value!r:.80}")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProjectionError(f"bad datetime {value!r}: {exc}")
    if parsed.tzinfo is None:
        raise ProjectionError(f"datetime requires a timezone: {value!r}")
    return parsed


def load_json_file(path):
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ProjectionError(f"cannot read {path}: {exc}")
    try:
        return json.loads(text)
    except ValueError as exc:
        raise ProjectionError(f"{path}: invalid JSON: {exc}")


def load_selector(selector_path, expected_sha256):
    blob = Path(selector_path).read_bytes()
    actual = hashlib.sha256(blob).hexdigest()
    if actual != expected_sha256:
        raise ProjectionError(
            f"selector hash mismatch: {selector_path} hashes to {actual}, "
            f"expected pinned {expected_sha256} — refusing to import")
    spec = importlib.util.spec_from_file_location(
        "selected_price_selector", selector_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.select_price


def load_raw_record(raw_dir, item_id):
    candidates = [
        Path(raw_dir) / item_id[:3] / f"{item_id}.json",
        Path(raw_dir) / f"{item_id}.json",
    ]
    for path in candidates:
        if path.is_file():
            raw = load_json_file(path)
            if not isinstance(raw, dict):
                raise ProjectionError(f"raw record {path} is not an object")
            return raw
    raise ProjectionError(
        f"raw history for item {item_id} not found under {raw_dir} "
        f"(tried {candidates[0].name} layout and flat layout)")


def load_artifact(evidence_dir, sha256):
    path = Path(evidence_dir) / sha256
    if not path.is_file():
        return None
    return path.read_bytes()


def verify_record(item, proof, raw, as_of, artifacts, select_price):
    """Mirror CurrentPriceProjection.for_item. `as_of` is the
    caller-supplied EVALUATION time (v6): every expiry, freshness
    and seller-window judgment uses it. Returns the recomputed
    payload entry dict (exactly the object for_item produces) when
    the projection applies, or None when the selection yields no
    sale (the contract's None). Raises ProjectionError on any
    contract violation."""
    if proof.get("raw_record_sha256") != digest(raw):
        raise ProjectionError(f"projection raw changed: {item}")
    snap = proof["snapshot"]
    observed = parse_dt(snap["observed_at"])
    expires = parse_dt(proof["expires_at"])
    source_hash = snap["source_content_sha256"]
    artifact = artifacts.get(source_hash)
    if not isinstance(artifact, bytes) or \
            hashlib.sha256(artifact).hexdigest() != source_hash:
        raise ProjectionError(
            f"source evidence artifact missing/mismatched: {item}")
    if not observed <= as_of < expires:
        raise ProjectionError(
            f"projection stale/future: {item} "
            f"(observed={snap['observed_at']}, as_of={as_of.isoformat()}, "
            f"expires={proof['expires_at']})")
    if not 0 < (expires - observed).total_seconds() <= 86400:
        raise ProjectionError(f"projection freshness exceeds 24h: {item}")
    if snap["item_id"] != item:
        raise ProjectionError(f"projection item mismatch: {item}")
    for evidence in proof["evidence"]:
        if evidence.get("seller_declared_start") and \
                as_of < parse_dt(evidence["seller_declared_start"]):
            raise ProjectionError(f"promotion not started: {item}")
        if evidence.get("seller_declared_end") and \
                as_of > parse_dt(evidence["seller_declared_end"]):
            raise ProjectionError(f"promotion ended: {item}")
        if evidence["source_content_sha256"] != snap["source_content_sha256"]:
            raise ProjectionError(f"evidence hash mismatch: {item}")
    out = select_price(snap, proof["evidence"], proof.get("legacy_variant_id"))
    if out["selected_sale"] is not True:
        return None
    key = raw.get("variation_keys", {}).get(out["selected_variant_id"])
    if not key:
        raise ProjectionError(f"selected variant not bound to raw history: {item}")
    series = raw.get("variations", {}).get(key)
    if not series:
        raise ProjectionError(f"selected series missing: {item}")
    latest = max(series, key=lambda p: p["date"])
    if latest["price"] != out["selected_price"]:
        raise ProjectionError(
            f"selected current price differs from raw latest: {item}")
    try:
        evidence = next(
            e for e in proof["evidence"]
            if e["evidence_id"] == out["selected_sale_evidence_id"])
    except StopIteration:
        raise ProjectionError(
            f"selected sale evidence id not found in proof: {item}")
    regular = evidence.get("regular_price")
    if type(regular) is not int or regular <= out["selected_price"]:
        raise ProjectionError(f"unverified comparison price: {item}")
    # Build the payload entry EXACTLY as for_item does (v6 point 2:
    # the gate compares the site's payload entries against this
    # recomputation, so the construction must not drift).
    legacy_series = max(raw["variations"].values(), key=len)
    legacy_prices = [p["price"] for p in
                     sorted(legacy_series, key=lambda p: p["date"])]
    out["legacy"] = {"cur": legacy_prices[-1], "base": max(legacy_prices),
                     "lowest": min(legacy_prices)}
    out.update(cur=out["selected_price"], base=regular,
               lowest=min(p["price"] for p in series),
               sale=True, on_sale=True, selected_variant_key=key,
               expires_at=proof["expires_at"],
               raw_record_sha256=proof["raw_record_sha256"])
    out["observed_display_variant_id"] = out["selected_variant_id"]
    out["observed_display_variant_key"] = out["selected_variant_key"]
    out["observed_display_price"] = out["cur"]
    out["observed_display_at"] = snap["observed_at"]
    sorted_series = sorted(series, key=lambda p: p["date"])
    stride = max(1, len(sorted_series) // 24)
    out["observed_display_spark"] = [
        [p["date"], p["price"]] for i, p in enumerate(sorted_series)
        if i % stride == 0 or i == len(sorted_series) - 1]
    accepted = [proof["raw_record_sha256"]]
    for binding in proof.get("runtime_snapshot_bindings", []):
        if parse_dt(binding["observed_at"]) > as_of:
            raise ProjectionError(
                f"runtime snapshot captured in future: {item}")
        artifact = artifacts.get(binding["artifact_sha256"])
        if not isinstance(artifact, bytes) or \
                hashlib.sha256(artifact).hexdigest() != binding["artifact_sha256"]:
            raise ProjectionError(
                f"runtime snapshot artifact mismatch: {item}")
        try:
            newer = json.loads(artifact)
        except ValueError as exc:
            raise ProjectionError(
                f"runtime snapshot artifact is not JSON: {item}: {exc}")
        if digest(newer) != binding["record_sha256"] or \
                newer.get("id") != raw["id"]:
            raise ProjectionError(f"runtime snapshot identity mismatch: {item}")
        if {k: v for k, v in newer.items() if k != "variations"} != \
                {k: v for k, v in raw.items() if k != "variations"}:
            raise ProjectionError(f"runtime snapshot metadata changed: {item}")
        if set(newer["variations"]) != set(raw["variations"]):
            raise ProjectionError(f"runtime snapshot variant set changed: {item}")
        for vkey, old_series in raw["variations"].items():
            recent = newer["variations"][vkey]
            if recent[:len(old_series)] != old_series:
                raise ProjectionError(
                    f"runtime snapshot changed historical prefix: {item}")
            if old_series and any(
                    p["date"] <= max(q["date"] for q in old_series)
                    for p in recent[len(old_series):]):
                raise ProjectionError(
                    f"runtime snapshot is not append-only: {item}")
            if any(p["date"] > as_of.astimezone(JST).date().isoformat()
                   for p in recent[len(old_series):]):
                raise ProjectionError(
                    f"runtime snapshot observation is in future: {item}")
        for variant in snap["variants"]:
            bkey = newer.get("variation_keys", {}).get(variant["id"]) or \
                proof.get("identity_bindings", {}).get(variant["id"])
            if not bkey or bkey not in newer["variations"]:
                raise ProjectionError(
                    f"runtime snapshot SKU binding missing: {item}")
            if max(newer["variations"][bkey],
                   key=lambda p: p["date"])["price"] != variant["price"]:
                raise ProjectionError(
                    f"runtime snapshot price differs from official "
                    f"observation: {item}")
        accepted.append(binding["record_sha256"])
    out["accepted_raw_record_sha256"] = list(dict.fromkeys(accepted))
    return out


def verify_package(package, expected_sha256, as_of, raw_dir, evidence_dir,
                   select_price):
    """Full package verification at the evaluation time `as_of`.
    Returns (entries, not_applied): entries maps each applied item
    to its recomputed payload entry (v6 point 2); not_applied lists
    the items whose selection yields no sale. Raises
    ProjectionError on the first failure."""
    if digest(package) != expected_sha256:
        raise ProjectionError("projection package hash mismatch")
    if package.get("schema") != 1:
        raise ProjectionError("projection schema mismatch")
    records = package["records"]
    if not isinstance(records, dict):
        raise ProjectionError("projection records required")
    artifacts = {}
    for path in Path(evidence_dir).iterdir():
        if path.is_file():
            blob = path.read_bytes()
            # Content-addressed lookup (the contract keys artifacts by
            # SHA256 of their bytes). This covers both conventions:
            # files named by their digest and descriptively named
            # files whose content hashes to the lookup key.
            artifacts[hashlib.sha256(blob).hexdigest()] = blob
    entries, not_applied = {}, []
    for item in sorted(records):
        proof = records[item]
        raw = load_raw_record(raw_dir, item)
        if str(raw["id"]) != item:
            raise ProjectionError(
                f"raw record id {raw['id']!r} does not match record key {item!r}")
        try:
            entry = verify_record(item, proof, raw, as_of, artifacts,
                                  select_price)
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise ProjectionError(f"{item}: contract check failed: {exc}")
        if entry is None:
            not_applied.append(item)
            print(f"projection {item}: NOT-APPLIED")
        else:
            entries[item] = entry
            print(f"projection {item}: APPLIED")
    return entries, not_applied


PROJECTION_SCRIPT_ID = 'id="current-price-projection"'
EMBED_ANCHOR = "window.CurrentPrices=createCurrentPriceProjection("

# v7 detection surface: the payload file name and the
# bootstrap/usage markers searched across the WHOLE known site
# inventory (not just index/item). "current-price-refresh" is the
# panel id of the lifecycle adapter the apply path inlines into
# every transformed page; it references CurrentPrices throughout,
# so the CurrentPrices marker catches it too — both are listed so
# a partially-stripped page is still detected.
PROJECTION_PAYLOAD_NAME = "current-price-projection.json"
PROJECTION_MARKERS = (
    PROJECTION_SCRIPT_ID,
    "createCurrentPriceProjection",
    "CurrentPrices",
    "current-price-refresh",
)
SCAN_SUFFIXES = {".html", ".htm", ".js", ".mjs", ".cjs"}
PAGE_SUFFIXES = {".html", ".htm"}


def site_inventory(site_dir, ledger_path):
    """The KNOWN generated output inventory (v7): the union of
    the site hash ledger the workflow already produces
    (hash-ledger.json: {relative path: sha256}, written by the
    build and carried in the work/evidence set of both wired
    jobs) and the files actually present under the site dir.
    Returns sorted POSIX-style relative paths."""
    rels = set()
    if ledger_path is not None and Path(ledger_path).is_file():
        ledger = load_json_file(ledger_path)
        if isinstance(ledger, dict):
            for key in ledger:
                rel = str(key).replace("\\", "/")
                while rel.startswith("./"):
                    rel = rel[2:]
                rels.add(rel.lstrip("/"))
    site_dir = Path(site_dir)
    if site_dir.is_dir():
        for path in site_dir.rglob("*"):
            if path.is_file():
                rels.add(path.relative_to(site_dir).as_posix())
    return sorted(rels)


def read_site_text(site_dir, rel):
    path = Path(site_dir) / rel
    if not path.is_file():
        return None
    return path.read_text(errors="replace")


def extract_embedded_config(text):
    """Extract the object embedded by apply_current_price_projection
    as window.CurrentPrices=createCurrentPriceProjection(<json>).
    Returns the parsed object, or None when the page carries no
    projection bootstrap call. Raises ProjectionError when the call
    is present but malformed (unparseable, duplicated, or not
    closed by ')')."""
    count = text.count(EMBED_ANCHOR)
    if count == 0:
        return None
    if count != 1:
        raise ProjectionError(
            f"embedded projection config anchor occurs {count} times, "
            f"expected exactly 1")
    start = text.index(EMBED_ANCHOR) + len(EMBED_ANCHOR)
    try:
        value, end = json.JSONDecoder().raw_decode(text[start:])
    except ValueError as exc:
        raise ProjectionError(f"embedded projection config is not "
                              f"parseable JSON: {exc}")
    if text[start + end:start + end + 1] != ")":
        raise ProjectionError(
            "embedded projection config is not closed by ')'")
    if not isinstance(value, dict):
        raise ProjectionError("embedded projection config is not an object")
    return value


def gate(args):
    """Projection-applied detection + mandatory verification."""
    work_dir = Path(args.work_dir)
    site_dir = Path(args.site_dir)
    declaration_path = work_dir / "projection-declaration.json"
    package_path = work_dir / "projection-package.json"
    evidence_records_path = work_dir / "evidence-records.json"

    signals = []
    declaration = None
    if declaration_path.is_file():
        declaration = load_json_file(declaration_path)
        if declaration.get("applied") is True:
            signals.append("declaration applied=true")
    if package_path.is_file():
        signals.append("projection-package.json present")
    # v7 (dot v6 review): BEFORE any "no projection" conclusion,
    # scan the KNOWN generated output inventory — the payload
    # file anywhere in the output, and bootstrap/usage markers in
    # EVERY generated HTML/JS file (sale.html and all other
    # routes included), not just index.html/item.html. The
    # inventory is the site hash ledger the workflow already
    # produces (default <work-dir>/hash-ledger.json), unioned
    # with the files actually present under the site dir.
    ledger_path = Path(args.site_ledger) if args.site_ledger else \
        work_dir / "hash-ledger.json"
    inventory = site_inventory(site_dir, ledger_path)
    payload_rels = [rel for rel in inventory
                    if Path(rel).name == PROJECTION_PAYLOAD_NAME]
    for rel in payload_rels:
        signals.append(f"site payload present: {rel}")
    for rel in inventory:
        if Path(rel).suffix.lower() not in SCAN_SUFFIXES:
            continue
        text = read_site_text(site_dir, rel)
        if text is not None and \
                any(m in text for m in PROJECTION_MARKERS):
            signals.append(f"projection markers in {rel}")
    projection_records = []
    if evidence_records_path.is_file():
        records_obj = load_json_file(evidence_records_path)
        for rec in records_obj.get("records", []):
            if rec.get("kind") == "current_price_projection":
                projection_records.append(rec)
        if projection_records:
            signals.append(
                f"evidence records kind=current_price_projection "
                f"({len(projection_records)} record(s))")
    if not signals:
        # v7: this early success is reachable ONLY after the full
        # inventory scan above found no payload file and no
        # bootstrap/usage marker on any generated route — a
        # thumbnail-only declaration can no longer hide a
        # projection applied elsewhere.
        print("projection gate: no projection-applied signal in "
              "the declaration, the evidence records, or any "
              "file of the known site inventory; projection not "
              "applied, gate passes")
        return 0
    # v6 point 1: once any projection-applied signal exists, the
    # caller MUST supply a trustworthy evaluation time (its own
    # current UTC). Without it the gate cannot judge expiry and
    # fails closed — the candidate's declared as_of is never a
    # substitute.
    if not args.evaluation_time:
        print("::error::projection gate: --evaluation-time is "
              "required from the caller workflow whenever a "
              "projection is applied (expiry is judged at evaluation "
              "time, not at the candidate's declared as_of)")
        return 1
    try:
        evaluation = parse_dt(args.evaluation_time)
    except ProjectionError as exc:
        print(f"::error::projection gate: --evaluation-time invalid: {exc}")
        return 1
    if declaration is None or declaration.get("applied") is not True:
        print(f"::error::projection gate: applied signals present "
              f"({', '.join(signals)}) but no declaration with "
              f"applied=true — undeclared projection application refused")
        return 1
    if not package_path.is_file():
        print("::error::projection gate: declaration says applied but "
              "projection-package.json is missing from the artifact")
        return 1
    if not projection_records:
        print("::error::projection gate: projection is applied but the "
              "evidence list has no current_price_projection record — "
              "a thumbnail-only evidence list must NOT pass when a "
              "projection is applied")
        return 1
    package = load_json_file(package_path)
    expected = declaration.get("package_sha256")
    if not isinstance(expected, str) or len(expected) != 64:
        print("::error::projection gate: declaration package_sha256 "
              "is missing or malformed")
        return 1
    if digest(package) != expected:
        print("::error::projection gate: declaration package_sha256 "
              "does not match the digest of the package bytes")
        return 1
    for rec in projection_records:
        if rec.get("package_sha256") != expected:
            print("::error::projection gate: evidence record "
                  "package_sha256 does not match the declaration")
            return 1
    # The declared as_of is recorded and sanity-checked ONLY (v6
    # point 1): it must not postdate the evaluation time, and no
    # record may claim an observation later than the declared
    # generation time. Freshness itself is judged at `evaluation`.
    try:
        declared_as_of = parse_dt(declaration["as_of"])
    except (ProjectionError, KeyError) as exc:
        print(f"::error::projection gate: declaration as_of invalid: {exc}")
        return 1
    if declared_as_of > evaluation:
        print(f"::error::projection gate: declaration as_of "
              f"{declaration['as_of']} is later than the evaluation "
              f"time {args.evaluation_time} — a candidate cannot "
              f"declare a generation time in the caller's future")
        return 1
    records = package.get("records")
    if isinstance(records, dict):
        for item, proof in records.items():
            try:
                observed = parse_dt(proof["snapshot"]["observed_at"])
            except (ProjectionError, KeyError, TypeError) as exc:
                print(f"::error::projection gate: record {item} "
                      f"observed_at invalid: {exc}")
                return 1
            if observed > declared_as_of:
                print(f"::error::projection gate: record {item} "
                      f"observed_at is later than the declared "
                      f"generation time (as_of) — evidence times are "
                      f"inconsistent with the declaration")
                return 1
    select_price = load_selector_or_fail(args)
    if select_price is None:
        return 1
    try:
        entries, not_applied = verify_package(
            package, expected, evaluation, args.raw_dir,
            work_dir / "projection-evidence", select_price)
    except ProjectionError as exc:
        print(f"::error::projection gate: {exc}")
        return 1
    applied = sorted(entries)
    if declaration.get("applied") is True and not applied:
        print("::error::projection gate: declaration says applied but "
              "no record produced an applied projection")
        return 1
    # The applied item set must be IDENTICAL across the verified
    # recomputation, the evidence records, and the declaration
    # (v6 point 2): no applied item without a verified record, and
    # no verified record silently unused.
    record_items = {rec.get("item_id") for rec in projection_records}
    uncovered = [item for item in applied if item not in record_items]
    if uncovered:
        print(f"::error::projection gate: applied items without a "
              f"current_price_projection evidence record: {uncovered}")
        return 1
    unused = sorted(record_items - set(applied))
    if unused:
        print(f"::error::projection gate: current_price_projection "
              f"evidence records for items with no applied "
              f"projection: {unused} — a verified record must not be "
              f"silently unused when the declaration says applied")
        return 1
    declared_items = declaration.get("applied_items")
    if not isinstance(declared_items, list) or \
            not all(isinstance(i, str) for i in declared_items):
        print("::error::projection gate: declaration applied_items "
              "is missing or not a list of item id strings")
        return 1
    if set(declared_items) != set(applied):
        print(f"::error::projection gate: declaration applied_items "
              f"{sorted(declared_items)} != verified applied set "
              f"{applied}")
        return 1
    # v6 point 2: bind the evidence to the ACTUAL generated payload
    # in the site output — the same object the apply path embeds
    # into the pages and serves as current-price-projection.json.
    payload_path = site_dir / "current-price-projection.json"
    if not payload_path.is_file():
        print("::error::projection gate: projection is applied but "
              "the site payload current-price-projection.json is "
              "missing from the site output")
        return 1
    try:
        payload = load_json_file(payload_path)
    except ProjectionError as exc:
        print(f"::error::projection gate: {exc}")
        return 1
    if not isinstance(payload, dict) or payload.get("schema") != 1 or \
            not isinstance(payload.get("entries"), dict):
        print("::error::projection gate: site payload is not a "
              "schema-1 object with an entries object")
        return 1
    if not payload["entries"]:
        print("::error::projection gate: site payload entries are "
              "empty although a projection is declared/applied")
        return 1
    payload_digest = digest(payload)
    if declaration.get("payload_sha256") != payload_digest:
        print("::error::projection gate: declaration payload_sha256 "
              "does not match the canonical digest of the actual "
              "site payload current-price-projection.json")
        return 1
    payload_items = set(payload["entries"])
    if payload_items != set(applied):
        print(f"::error::projection gate: site payload item set "
              f"{sorted(payload_items)} != verified applied set "
              f"{applied} (missing: "
              f"{sorted(set(applied) - payload_items)}, extra: "
              f"{sorted(payload_items - set(applied))})")
        return 1
    for item in applied:
        if payload["entries"][item] != entries[item]:
            print(f"::error::projection gate: site payload entry for "
                  f"{item} does not match the entry recomputed from "
                  f"the verified contract (payload tampered or "
                  f"generated from unverified inputs)")
            return 1
    # v7: any ADDITIONAL payload file elsewhere in the output
    # must be the same verified object — an unmatched payload
    # copy on another route is an unverified projection artifact.
    for rel in payload_rels:
        if rel == PROJECTION_PAYLOAD_NAME:
            continue
        try:
            extra = load_json_file(site_dir / rel)
        except ProjectionError as exc:
            print(f"::error::projection gate: {exc}")
            return 1
        if not isinstance(extra, dict) or \
                digest(extra) != payload_digest:
            print(f"::error::projection gate: additional payload "
                  f"file {rel} does not match the verified site "
                  f"payload {PROJECTION_PAYLOAD_NAME}")
            return 1
    # The embedded configuration in the generated pages must be
    # the same payload object. v7 (dot v6 review): verification
    # is keyed on the bootstrap CALL and on usage, NOT on the
    # exact script id — every generated page in the inventory
    # that carries the bootstrap call or any projection usage
    # marker must embed a configuration, located by the
    # createCurrentPriceProjection call itself, whose digest
    # matches the site payload. An absent or altered script id
    # does not skip verification, and usage without a verifiable
    # embedded configuration fails. index.html and item.html MUST
    # carry a verified embedded configuration.
    seen_embedded = set()
    for rel in inventory:
        if Path(rel).suffix.lower() not in PAGE_SUFFIXES:
            continue
        text = read_site_text(site_dir, rel)
        if text is None:
            continue
        if EMBED_ANCHOR not in text and \
                not any(m in text for m in PROJECTION_MARKERS):
            continue
        try:
            config = extract_embedded_config(text)
        except ProjectionError as exc:
            print(f"::error::projection gate: {rel}: {exc}")
            return 1
        if config is None:
            print(f"::error::projection gate: {rel} carries "
                  f"projection bootstrap/usage markers but no "
                  f"createCurrentPriceProjection configuration — "
                  f"an empty projection script must not pass, and "
                  f"verification is not skipped merely because "
                  f"the exact script id is absent or altered")
            return 1
        if digest(config) != payload_digest:
            print(f"::error::projection gate: {rel} embedded "
                  f"createCurrentPriceProjection config digest "
                  f"does not match the site payload digest")
            return 1
        seen_embedded.add(rel)
    for required_page in ("index.html", "item.html"):
        if required_page not in seen_embedded:
            print(f"::error::projection gate: {required_page} does "
                  f"not carry the embedded projection configuration "
                  f"although a projection is applied")
            return 1
    print(f"projection gate OK: applied={applied} "
          f"not_applied={not_applied} "
          f"evaluation_time={args.evaluation_time} "
          f"payload_sha256={payload_digest}")
    return 0


def load_selector_or_fail(args):
    selector_path = args.selector or str(
        Path(__file__).resolve().parent / "selected_price_selector.py")
    expected = args.selector_sha256 or PINNED_SELECTOR_SHA256
    try:
        return load_selector(selector_path, expected)
    except (OSError, ProjectionError) as exc:
        print(f"::error::projection selector unavailable: {exc}")
        return None


def main(argv):
    parser = argparse.ArgumentParser(
        description="Verify the current-price projection contract.")
    parser.add_argument("--gate", action="store_true",
                        help="gate mode: detect applied projections and "
                             "require their verification")
    parser.add_argument("--package")
    parser.add_argument("--expected-sha256")
    parser.add_argument("--as-of",
                        help="verify mode: caller-supplied evaluation "
                             "time (alias of --evaluation-time)")
    parser.add_argument("--evaluation-time",
                        help="the caller's trustworthy current time "
                             "(ISO, timezone required); ALL expiry / "
                             "freshness / seller-window judgments use "
                             "it. Required in gate mode whenever a "
                             "projection is applied.")
    parser.add_argument("--raw-dir")
    parser.add_argument("--evidence-dir")
    parser.add_argument("--work-dir")
    parser.add_argument("--site-dir")
    parser.add_argument("--site-ledger",
                        help="gate mode: the site hash ledger "
                             "({relative path: sha256}) defining "
                             "the known generated output inventory "
                             "for detection; defaults to "
                             "<work-dir>/hash-ledger.json when "
                             "present, unioned with the site tree")
    parser.add_argument("--selector")
    parser.add_argument("--selector-sha256")
    args = parser.parse_args(argv)
    if args.gate:
        for required in ("work_dir", "site_dir", "raw_dir"):
            if not getattr(args, required):
                print(f"::error::gate mode requires --{required.replace('_', '-')}")
                return 2
        return gate(args)
    evaluation_arg = args.evaluation_time or args.as_of
    if not evaluation_arg:
        print("::error::verify mode requires --evaluation-time "
              "(or its alias --as-of): expiry is judged at the "
              "caller-supplied evaluation time")
        return 2
    for required in ("package", "expected_sha256", "raw_dir",
                     "evidence_dir"):
        if not getattr(args, required):
            print(f"::error::verify mode requires --{required.replace('_', '-')}")
            return 2
    select_price = load_selector_or_fail(args)
    if select_price is None:
        return 1
    try:
        package = load_json_file(args.package)
        evaluation = parse_dt(evaluation_arg)
        entries, not_applied = verify_package(
            package, args.expected_sha256, evaluation, args.raw_dir,
            args.evidence_dir, select_price)
    except ProjectionError as exc:
        print(f"::error::{exc}")
        return 1
    print(f"projection verification OK: applied={sorted(entries)} "
          f"not_applied={not_applied}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
