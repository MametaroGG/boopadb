# R2: existing flat relation manifest compatibility

## Small follow-up patch

Apply only `FLAT-MANIFEST-R2.patch` to `run_candidate.py` in the integration copy.
The original delivered ZIP and original candidate directory are unchanged.

- Original run_candidate.py SHA256:
  `ee973baf8cc0a6f0dca95c0604bc4dcdaf17d1491b4adc2b58889f2f8418614a`
- Patched run_candidate.py SHA256:
  `72dacd92b6c30e987c13251b2e773d973f6d8d238ce0831ed903190775c9b9b0`
- Patch SHA256:
  `f4b244a0a51c4850325e46a7c95e3595d8ab8b8c919a42bbe6dc83a31e366dd8`

From the integration copy's root, after checking the original hash:

```
patch -p1 < /path/FLAT-MANIFEST-R2.patch
```

This is not authorization to deploy, publish or change the scope of approvals.
No external service or repository was changed during local patch development.

## Exact change

The existing real manifest format may be a flat `{relative_path: sha256}` map;
the earlier configuration reader assumed `{files: {...}}` only. It now accepts:

- A nonempty flat path-to-SHA256 map.
- The existing wrapped inventory with `files` and supported canonical metadata
  (`schema`, `status`, `version`, `public_release_commit`, `sourceVersion`).

`files` is reserved as the wrapper discriminator. Mixed wrapper/path maps,
unsupported/ambiguous shapes, empty inventories, invalid hashes, unsafe or
noncanonical paths and normalization collisions are rejected. The SAME extracted
map must equal the existing approval.files, and every referenced bundle file
must still match its SHA256. Only the map is interpreted; source manifest bytes
are never rewritten, wrapped, canonicalized or assigned a substitute digest.
`release_contract.inputs` still checks the actual original manifest-byte SHA256
against the baseline pin before this parser runs.

No approval scope/status or production guard changed. In particular existing
`scope: local-test-only` still refuses a production context, including with a
valid flat manifest. The patch does not promote or relabel those approvals.

## Verification and evidence limits

The regression fixture uses equivalent 75/10/4 flat maps derived from bundled
existing inventories and their test approval mappings. It is **not a byte replay
of Muse's remote manifests**, which are not present in this workspace. Muse must
verify its actual unchanged manifest bytes and pins at the trial branch.

Tests cover flat/wrapped equality, real local bundle hashes, original byte-pin
binding, actual synthetic generation through full machine validation, malformed
hash/path/shape cases and the local-test-only production refusal. Tests generate
no production approvals and do not contact external services. See
`R2-ALL-TEST-RESULTS.log` and the independent review's `flat-compat/` evidence.

## Daily coverage null/null: no behavioral change

No daily coverage data is invented. This patch does not change coverage handling.
The explicit `daily_coverage_file: null` / `daily_target_date: null` pair makes the
runner omit both optional CLI flags, exactly preserving the canonical defaults:

- build_site.py defaults both optional arguments to None and calls
  build_full.read_daily_coverage(None, ...), which returns `(None, None)`.
- build_full.py `DailyPriceAccumulator` defaults the daily target to current JST,
  marks missing coverage as `reason: missing-coverage`, and emits daily
  `status: unavailable`, `unique_products: null` rather than an invented count.
- This optional receipt controls verified daily-price-change statistics and
  private receipt provenance. It does not filter catalog records, change
  cumulative counts, waive collector completion requirements, or turn off
  snapshot, population, freshness, relation, price, UI or publication gates.

Source references (unchanged original generator): build_site.py build() around
lines145–153 and CLI lines232–233; build_full.py read_daily_coverage lines208–224,
DailyPriceAccumulator lines124–199, stats assignment line459. The retained
original synthetic full-run output independently shows missing-coverage daily
statistics with cumulative/catalog data intact. A valid supplied bound receipt
would permit verified daily statistics; null/null does not claim that benefit.
