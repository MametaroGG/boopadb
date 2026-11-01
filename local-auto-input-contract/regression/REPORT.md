# Full producer baseline regression — final correction/readback

Immutable upstream: `MametaroGG/booth-vrc-price-tracker@4980d9bc341c85be5654751760867dce4bd57ba9`.
Tests and required source/workflows/extension fixtures were materialized read-only.
Existing local files were reused only after matching upstream Git blob IDs; changed
text files were read through the GitHub connector. Two unrelated promo PNGs were
not fetched; no test references them. This is a test-consumed source materialization,
not a claim to have downloaded the complete data repository.

Existing dependencies from `boopa-price-fix/node_modules` were reused without install:
axios 1.13.2, cheerio 1.1.2. Node v24.22.1 in this executor (production workflow targets
Node20; production Node20 execution remains unverified). Package metadata was checked
against official Git blobs. Test command, from workspace root:

```
NODE_OPTIONS="--require=$PWD/local-auto-input-contract-regression/deny-network.cjs" \
 npm --prefix local-auto-input-contract-regression/current test
```

Preload rejects Node TCP connections and UDP sends, including child Node processes;
tests use mocked requests and disposable Git file:// remotes. No scraper/network
collection, package installation or existing-repository mutation occurred.

## Results

- Original official suite before patch: **297/297 pass** (`baseline-297.log`).
- First applicable patch: **296 pass, 1 fail** (retained initial failure log).
- Final exact-byte patch: **297/297 pass** (`patched-final-297.log`).
- Separate final focused suite rerun: **39 JS + 40 Python pass**.
- Patch `git apply --check` and apply succeeded against exact official source.
- Patched filesystem tree readback matches producer pins:
  - src: `f87362be086663c18704f1dc88e730273b85283d`
  - scripts: `8d25af313c5ce0e38068fb126832ffdcf6c893fe`
  - test: `9fda80fc15cd5dde6f7ab42b6d0b2133777095dc`

## Corrections exposed by the full regression

1. Earlier connector-text materialization accidentally added one EOF newline to
   seven preserved source files. That made the old patch fail against exact workflow
   EOF and would have mismatched unchanged runtime/continuation pins. ALL seven
   source copies were corrected and verified against official Git blob IDs; the new
   original workflow test is likewise blob-verified. Source-derived patch, full
   workflow, root/file pins and manifests were regenerated. The old package was
   never uploaded/published and must not be used.
2. Five added one-minute guard/receipt steps exceeded the old timeout budget, and
   upload lacked its own explicit timeout. The final proposal gives upload one
   minute and changes checkout **20→15 minutes** to retain the original total
   **359 minutes, below 360**. This reduces checkout tolerance: it is an operational
   behavior change, not a test-only adjustment. Actual checkout duration/large-repo
   behavior under this limit has NOT been verified. No runtime scrape cap/save
   margin was changed. The upstream workflow test now expects 16 timed steps instead
   of 11, retains exact 359 / <360 assertions, and adds source-guard order assertions.

Final proposed workflow SHA256:
`2b846e818ffd9c691f733613b645876ee19e9a7e6f15ef08fdda1a953e4e6186`.
Resolver code unchanged: `6a33dba2472c4d6686f243e187f5c88af8a15f378b77306a9d56f4a3b531622d`.
Real token/artifact access, live reads, Node20 CI, scheduling and publication remain
unexecuted. These offline passes do not authorize activation.
