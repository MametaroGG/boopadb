# BoopaDB

BOOTH（VRChat向けデジタルアイテム）の価格推移データベース。

- サイト: https://mametarogg.github.io/boopadb/
- 価格データ: [booth-vrc-price-tracker](https://github.com/MametaroGG/booth-vrc-price-tracker) が収集した公開データを利用

現在はプロトタイプ版です。BOOTHの全件データ（約20万件）と接続して動作しています。

> BoopaDB は非公式の個人プロジェクトであり、BOOTH および pixiv株式会社とは関係ありません。BOOTH は pixiv株式会社の商標です。

## Home recommendations

The hero and featured row rotate on six-hour UTC windows (00:00 / 06:00 /
12:00 / 18:00). The window is captured once per page visit, so a page left open
never swaps products at the boundary. Reloading in the same window uses the
same selection for the same catalog. Existing carousel animation is independent.

Candidates are the top 40 valid, illustrated products by likes in each of
`newest` and `on_sale`. The hero alternates new/sale (six products when enough
candidates exist); featured selects ten new products excluding hero IDs. Each
section allows at most two products per shop, and can show fewer when candidates
are limited. Selection does not alter source prices or discount semantics.

After updating the catalog, run `node scripts/embed-hero.cjs` to embed the compact
candidate pools, and `node scripts/embed-hero.cjs --check` before publishing.
The same selector runs before and after the full catalog loads to avoid replacing
unchanged cards. This is client-side rotation, not an additional catalog-fetch job.

Regression checks (with test dependency `jsdom@26.1.0` available):
`node --test tests/*.test.cjs`. The separate `tests/test_freshness.py`
requires an authorized working Chromium/Playwright environment; Node DOM tests
do not substitute for browser pixel verification.
