# Freshness fix integration

The repository contains generated pages, not their Python builders. To preserve
this fix on the next generation, update the shared page head in every builder
(the pages reference `build_prototype.py`, `build_pages_extra.py`, and
`build_sale.py` in comments):

1. Replace the inline `navigator.serviceWorker.register("sw.js")` snippet with
   `<script src="site-update.js?v=1" defer></script>`.
2. Copy `site-update.js` and the revised `sw.js` into every generated output.
3. Do not restore the old stale-while-revalidate worker. Do not clear localStorage.
4. A deployment must update the Last-Modified value of changed files. GitHub Pages currently
   serves a deployment-wide Last-Modified header. The client also probes the visible banner and lists_full.json, so a banner-only
   or list-only deployment is detected even when the HTML timestamp is unchanged.
   If only data changes on another host, this page watcher does not detect those changes; that host needs its own
   data-refresh strategy. Same-origin JSON requests bypass the HTTP/SW cache.

The client checks when opened/resumed/online and once per two minutes while
visible. Check cycles are throttled to one per 30 seconds (two HEAD requests, or three when
a banner is present). A fresh HEAD response is
requested with a unique query and `cache: no-store`; only a strictly newer
Last-Modified triggers reload. The attempted combined revision is retained in
sessionStorage and the transient reload URL to prevent HEAD-new/GET-old CDN
propagation loops. A failed attempt for the same revision requires a normal
manual reload or a later revision; it does not repeatedly disrupt the user. The existing query/hash and persistent bookmarks
are preserved. Focused form fields defer the reload. Offline errors do not reload.
Old shell responses are copied into the new cache before the old cache is removed,
preserving offline fallback across worker migration. An already-open page with the old registration snippet needs an ordinary reload
once to obtain the new client. We intentionally do not forcibly navigate every
old tab from service-worker activation.

Tests: `node --test tests/freshness.test.cjs`. Browser regression script:
`python tests/test_freshness.py` (requires Playwright and Chromium). The latter was
not executable in the supplied sandbox: Chromium socket creation was blocked,
and the approved-launch wrapper failed to create its sessions mount. Real iPad
Safari/Chrome and BFCache behaviour remain unverified.

## Stable initial hero (reload flash)

The home hero must use the same six ranked products on first paint and after
`lists_full.json` arrives. Preserve these changes in `build_prototype.py`:

1. Keep `selectHeroEntries` (between `HERO_SELECTOR_START/END`) as the single
   selection rule: newest and sale by likes, alternating, unique IDs, maximum six.
2. Keep the `HERO_BOOTSTRAP_DATA` marker, normalization, immutable rendered
   signature, and `renderHeroFromLists` comparison. Do not restore the old
   sample-sale/active five-item initial hero or the ID-only comparison.
3. After generating **both** index.html and lists_full.json, run
   `node scripts/embed-hero.cjs`, then `node scripts/embed-hero.cjs --check`.
   Publish the two outputs together. The script uses the browser's actual selector
   and safely escapes embedded JSON. It embeds only six products (~2.3 KB), not
   the full catalog, so first paint does not wait for a multi-megabyte fetch.
4. Keep `buildHero(items, preserveCurrent)` so genuine data updates retain the
   selected product if it remains present. Unchanged data must not rebuild DOM,
   discard loaded images/metadata, reset navigation, or restart the timer.

Verification: `node --test tests/hero-bootstrap.test.cjs` covers initial/fetched
parity, enrichment without rebuild, unchanged DOM/position/timer, changed prices
and text for the same IDs, ranking changes, removal fallback, duplicate filtering,
and the six-item limit. These are Node/DOM-double regressions, not a real mobile
browser run; actual iPad/Android visual confirmation remains necessary.

## Touch activation / iPad navigation

Preserve in the home and item builders:
- Browse-row previews use `pointerenter` only when `pointerType === "mouse"`.
  Do not restore `mouseenter` DOM replacement: touch compatibility mouse events
  can alter content before the native click. Pen/touch still use normal links.
- Keep navigation visible while a pointer is down on it and for 400 ms after
  release so late momentum-scroll events cannot move the hit target away.
  Cancel/blur release the lock. Events remain passive and native; no synthetic
  touch clicks or global prevention of scrolling/zooming.
- `tests/tap-response.test.cjs` executes both complete HTML pages and covers
  compatibility mouseenter, mouse preview, late scroll, repeat taps, cancel/blur.
  This is DOM/event regression coverage, not real iPad/WebKit validation. The
  user's unspecified button symptom still needs on-device confirmation.
