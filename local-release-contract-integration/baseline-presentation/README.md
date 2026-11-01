# Exact public-baseline presentation recovery (read-only)

Source: MametaroGG/boopadb commit `06fc871a5b86287ce91dee20d2a2ea54d86328e3`, read via GitHub connector on 2026-11-01.

- Public Git tree is untruncated; root `current-price-projection.json` is absent (also 404 on exact-commit fetch).
- Public index/item contain no `current-price-projection`, `createCurrentPriceProjection`, or `CurrentPrices` markers. Other routes were not individually scanned.
- Index blob `cebee521935ebe0cb72723d0faa443fa6d422c9d`; item blob `aa523fc3ea5b5b654b1110a5a80fe742027359b2`. Local baseline fixture bytes independently hash to these public blobs.
- `presentation-proof.exact.json` is the exact UTF-8 JSON substring embedded in BOTH pinned pages, without added newline or reserialization.
- Canonical digest: `1d98251b5d5b3ffd9e038e13b2f440f18c111db703dcc698c4a8f29031df4517`.
- Four existing outlier comparison-suppression records: 8328795, 8350004, 8372235, 8422085. Original observation dates remain 2026-10-29. All variant coverage remains `unknown`. No current availability, sale review, or completeness was invented.

## Corrected scope
Fresh sale-projection authorization is not demonstrated to be needed merely to preserve this exact nonprojected public baseline. Preserve these existing conditional comparison suppressions, not an invented empty presentation proof. New verified sale selection still requires genuine current evidence and an authenticated review/import boundary, which the existing contracts do not define.

`generation-price-fields.json` is only the four price fields for the EXISTING `run_candidate` configuration, not a complete runnable configuration. All actual relations bundle/approval inputs, daily coverage/date, tracker, release context, predecessor and generation checks remain required. The proof is baseline preservation metadata, NOT a fresh authenticated observation or production import approval.

## Verified
Run `PYTHONDONTWRITEBYTECODE=1 python local-price-baseline-review/check_baseline.py`.
Exact public blob identities; identical embedded original JSON bytes; canonical digest; unchanged `apply_presentation` accepts the proof, preserves four entries plus historySaleLabel/ppStats and comparison helpers, mints no projection, rejects a wrong digest. Existing evidence-builder 32 tests also pass; every file in its OUTPUT-HASHES ledger remains unchanged.

## Not established
No full current-generation build or browser acceptance, no full site marker scan, no source collection or new raw fetch, no reviewer authentication or deployment. Production consumers only check supplied hash/structure, NOT reviewer identity; this must not be represented as authenticated new evidence.

UI-only rerender has a separate metadata mismatch: the public baseline snapshot-manifest has no presentation_proof_sha256, and rerender_candidate requires supplied proof presence/digest to match that field. Thus supplying this recovered proof to that route fails its existing check. Do not mutate the historical manifest or claim that route was verified. Fresh run_candidate explicitly forwards proof/digest and is the applicable existing mapping; a complete real-input generation has not been run here.

Historical regression (not the public baseline): 1780665's longest raw history is free terms (0), but the expired projection runtime retains observed paid SKU13536956 at2500 while removing sale/comparison and sale-list membership. Therefore projection omission is NOT generally equivalent to expiry; it is appropriate here only because the checked public baseline is nonprojected.
