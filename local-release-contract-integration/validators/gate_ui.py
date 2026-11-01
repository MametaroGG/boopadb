#!/usr/bin/env python3
"""[DRAFT-ADAPTATION] Gate 4 — per-page UI regression checks.

Proposed checked-in location: generator/scripts/gate_ui.py

    gate_ui.py SITE_DIR

Checks index.html and item.html SEPARATELY (never concatenated).
Function bodies are extracted by BRACE MATCHING with a scanner that
understands JS strings, template literals (incl. ${ } nesting) and
comments — v2's fixed-width "window search" could pass or fail on
text outside the function; v3 inspects the actual body (dot v2
review point 6). Known limitation: regex literals are not tokenized;
if a checked function body contained a regex literal with braces,
extraction could mis-split — extraction failure makes the gate FAIL
(closed), never pass.

Every expected shape below is pinned from the verified published
baseline (commit 06fc871a5b86287ce91dee20d2a2ea54d86328e3; index blob
cebee521935ebe0cb72723d0faa443fa6d422c9d, item blob
aa523fc3ea5b5b654b1110a5a80fe742027359b2) and from the canonical
overlay source where noted. If the canonical generator legitimately
refactors one of these shapes, the gate must be re-pinned by review —
not loosened silently.

v4 additions (dot v3 review — UI acceptance fixtures): extraction now
runs on a COMMENT-STRIPPED copy of the page (JS comments inside
<script> blocks and HTML comments are blanked length-preservingly
first), so a definition that exists only inside a comment does NOT
count; and every checked function must be defined EXACTLY ONCE — a
duplicate definition fails. Check 6 is expanded from URL presence to
the guard itself (see below). fixtures/ in this package proves the
pass/fail pattern against the published baseline and mutations.

Per page, ALL of the following are required:
1. historySaleLabel: EXACTLY ONE function definition whose
   brace-matched body carries the sale-observed label
   (「セール観測」 / 'Sale observed') and does NOT contain
   「現在セール」 — per the published baseline the helper's role is
   sale-observed ONLY. Plus at least one call site
   `historySaleLabel()` outside the definition.
2. varBlockHTML: EXACTLY ONE function definition whose body
   - derives the current-sale flag from the LATEST history point,
     pinned shape: onSaleNow = !!s[s.length - 1][2]
     (this is where the baseline implements current-sale rendering
     for the variation block: the flag is computed there, separately
     from the label helper checked in 1);
   - calls historySaleLabel() for the chip label;
   - contains NO "pp-varprice" (R3: the heading price span was
     removed; the same-named CSS rule elsewhere in the page is
     outside this function body and is not flagged).
3. ppStats preserved (dot correction): the page contains the element
   id="ppStats" and a getElementById("ppStats") reference.
4. Negative cache (meta fetch), identifiers pinned from the canonical
   overlay source build_prototype.py (SHA
   4aa0c58e1f08d4a8cabbb62c6ae09147132f3b9d56a39cdbc33d95a343c4142d,
   fetchMeta / _metaCache): the page matches
   `const _metaCache = new Map()`; the brace-matched fetchMeta body
   contains `_metaCache`, `retryAt`, `_metaCache.delete`, and
   `Date.now() + 60000` (the 60-second negative-cache retry); plus a
   fetchMeta call site outside the definition. HARD GATE (v2 had this
   as a warning-only TODO with a guessed pattern).
5. DETAIL_HISTORY_HYDRATION: the START marker precedes the END
   marker; the span between them contains function definitions of
   hasDetailHistory, detailHistoryRequest and openItemSmart; plus an
   openItemSmart call site outside its definition.
6. Item 2625416 verifiedThumbnail correction (v4 — guard-level, not
   just URL presence): EXACTLY ONE verifiedThumbnail definition whose
   body carries the item guard branch `String(id) === "2625416"`
   returning the full corrected pximg URL; the page carries the
   pinned ORIGINAL confirmation-time literal
   2026-10-31T00:54:24.326165+00:00 (an altered/refreshed time
   fails); the image-missing-only application guard
   `!(meta && (meta.image_resized || meta.image))` is present; and
   verifiedThumbnail has a call site. (The evidence RECORD behind it
   is additionally re-verified against the pin by the evidence gate /
   promotion revalidation.)
"""

import re
import sys
from pathlib import Path

CORRECTED_2625416_URL = (
    "https://booth.pximg.net/67ca34b5-0cd7-452e-a53a-f89794950c3d"
    "/i/2625416/24cc7397-56e4-4499-87b1-21fd0cae90a9_base_resized.jpg"
)

# The ORIGINAL confirmation time of the 2625416 correction, embedded
# in the published baseline page (image_verified_at). It must never
# be refreshed to a newer time (dot: evidence times are not renewed).
PINNED_2625416_CONFIRMED_AT = "2026-10-31T00:54:24.326165+00:00"


# ---------------------------------------------------------------------------
# Brace-matched function extraction.
# ---------------------------------------------------------------------------

def _match_braces(text, open_idx):
    """Return the index of the '}' matching text[open_idx] == '{',
    or -1. String/comment/template aware (regex literals are not)."""
    depth = 0
    mode = "code"          # code | sq | dq | tpl | lc | bc
    tpl_marks = []         # depths at which a ${ opened
    i = open_idx
    n = len(text)
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if mode == "code":
            if c == "'":
                mode = "sq"
            elif c == '"':
                mode = "dq"
            elif c == "`":
                mode = "tpl"
            elif c == "/" and nxt == "/":
                mode = "lc"
                i += 1
            elif c == "/" and nxt == "*":
                mode = "bc"
                i += 1
            elif c == "{":
                depth += 1
            elif c == "}":
                if tpl_marks and depth - 1 == tpl_marks[-1]:
                    depth -= 1
                    tpl_marks.pop()
                    mode = "tpl"
                else:
                    depth -= 1
                    if depth == 0:
                        return i
        elif mode == "sq":
            if c == "\\":
                i += 1
            elif c == "'":
                mode = "code"
        elif mode == "dq":
            if c == "\\":
                i += 1
            elif c == '"':
                mode = "code"
        elif mode == "tpl":
            if c == "\\":
                i += 1
            elif c == "`":
                mode = "code"
            elif c == "$" and nxt == "{":
                tpl_marks.append(depth)
                depth += 1
                mode = "code"
                i += 1
        elif mode == "lc":
            if c == "\n":
                mode = "code"
        elif mode == "bc":
            if c == "*" and nxt == "/":
                mode = "code"
                i += 1
        i += 1
    return -1


_REGEX_PREV_CHARS = set("(,=:[!&|?{};+-*%<>^~")
_REGEX_PREV_WORDS = frozenset({
    "return", "typeof", "case", "delete", "void", "in", "of", "new",
    "instanceof", "yield", "await", "else", "do",
})


def _strip_js_comments(seg):
    """Blank // and /* */ comments in a JS segment to spaces,
    length-preserving (newlines kept). String/template aware, and —
    unlike _match_braces — REGEX-LITERAL aware via the standard
    previous-token heuristic (a '/' opens a regex unless the
    previous significant token is a value); without this, a quote
    inside a regex (e.g. /'/g) desyncs the scanner and a later
    comment is missed. The heuristic can still err on pathological
    code; downstream extraction failure fails closed."""
    out = list(seg)
    depth = 0
    mode = "code"          # code | sq | dq | tpl | lc | bc | regex
    tpl_marks = []
    prev_char = ""         # last significant char in code mode
    prev_word = ""         # last identifier/keyword in code mode
    word = ""              # identifier currently being read
    in_class = False       # inside [...] in a regex literal
    i, n = 0, len(seg)
    while i < n:
        c = seg[i]
        nxt = seg[i + 1] if i + 1 < n else ""
        if mode == "code":
            if c.isalnum() or c in "_$":
                word += c
                i += 1
                continue
            if word:
                prev_word, word = word, ""
            if c == "'":
                mode = "sq"
            elif c == '"':
                mode = "dq"
            elif c == "`":
                mode = "tpl"
            elif c == "/" and nxt == "/":
                out[i] = out[i + 1] = " "
                mode = "lc"
                i += 1
            elif c == "/" and nxt == "*":
                out[i] = out[i + 1] = " "
                mode = "bc"
                i += 1
            elif c == "/" and (
                    prev_char == "" or prev_char in _REGEX_PREV_CHARS
                    or prev_word in _REGEX_PREV_WORDS):
                mode = "regex"
                in_class = False
            elif c == "{":
                depth += 1
                prev_char = c
            elif c == "}":
                if tpl_marks and depth - 1 == tpl_marks[-1]:
                    depth -= 1
                    tpl_marks.pop()
                    mode = "tpl"
                else:
                    depth -= 1
                prev_char = c
            elif not c.isspace():
                prev_char = c
        elif mode in ("sq", "dq"):
            quote = "'" if mode == "sq" else '"'
            if c == "\\":
                i += 1
            elif c == quote:
                mode = "code"
                prev_char, prev_word = quote, ""
        elif mode == "tpl":
            if c == "\\":
                i += 1
            elif c == "`":
                mode = "code"
                prev_char, prev_word = "`", ""
            elif c == "$" and nxt == "{":
                tpl_marks.append(depth)
                depth += 1
                mode = "code"
                prev_char, prev_word = "{", ""
                i += 1
        elif mode == "regex":
            if c == "\\":
                i += 1
            elif c == "[":
                in_class = True
            elif c == "]":
                in_class = False
            elif c == "/" and not in_class:
                mode = "code"
                prev_char, prev_word = "/", ""
            elif c == "\n":
                mode = "code"  # unterminated regex: resync, fail-closed
        elif mode == "lc":
            if c == "\n":
                mode = "code"
                prev_char, prev_word = "", ""
            else:
                out[i] = " "
        elif mode == "bc":
            if c == "*" and nxt == "/":
                out[i] = out[i + 1] = " "
                mode = "code"
                prev_char, prev_word = "", ""
                i += 1
            elif c != "\n":
                out[i] = " "
        i += 1
    return "".join(out)


_SCRIPT_RE = re.compile(r"(<script\b[^>]*>)(.*?)(</script\s*>)",
                        re.S | re.I)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)


def _blank_html_comments(seg):
    def repl(m):
        return "".join("\n" if ch == "\n" else " " for ch in m.group(0))
    return _HTML_COMMENT_RE.sub(repl, seg)


def _strip_comments(text):
    """Return a same-length copy of the page in which JS comments
    inside <script> blocks and HTML comments outside them are blanked
    to spaces. Offsets are preserved, so spans found in the stripped
    copy index the original text. A function definition that exists
    only inside a comment is invisible to extraction afterwards
    (v4 — dot v3 review: comment-only definitions must FAIL)."""
    parts = []
    pos = 0
    for m in _SCRIPT_RE.finditer(text):
        parts.append(_blank_html_comments(text[pos:m.start(2)]))
        parts.append(_strip_js_comments(m.group(2)))
        pos = m.start(3)
    parts.append(_blank_html_comments(text[pos:]))
    return "".join(parts)


def extract_functions(text, name):
    """All (start, end, body) for `function name(...) { ... }`.
    start = index of the `function` keyword; end = index just past
    the matching '}'. Also matches `async function name(` because the
    search needle is the `function name(` substring."""
    out = []
    needle = f"function {name}("
    start = 0
    while True:
        i = text.find(needle, start)
        if i < 0:
            return out
        open_idx = text.find("{", i)
        if open_idx < 0:
            return out
        close_idx = _match_braces(text, open_idx)
        if close_idx < 0:
            return out
        out.append((i, close_idx + 1, text[open_idx + 1:close_idx]))
        start = close_idx + 1


def call_sites(text, name, def_spans):
    """Occurrences of `name(` that are not a definition and do not
    lie inside any definition span of `name`."""
    count = 0
    for m in re.finditer(re.escape(name) + r"\(", text):
        pos = m.start()
        if any(s <= pos < e for s, e, _ in def_spans):
            continue
        if text[max(0, pos - 9):pos] == "function ":
            continue
        count += 1
    return count


# ---------------------------------------------------------------------------
# Per-page checks.
# ---------------------------------------------------------------------------

def _single_def(fails, code, page_name, name):
    """Extract definitions of `name` from the comment-stripped code
    and require EXACTLY ONE (v4: a duplicate definition, or one that
    exists only inside a comment, fails). Returns the defs list."""
    defs = extract_functions(code, name)
    if not defs:
        fails.append(f"{page_name}: {name} definition missing "
                     "(absent, or present only inside a comment)")
    elif len(defs) > 1:
        fails.append(f"{page_name}: {name} defined {len(defs)} times "
                     "(duplicate definition)")
    return defs


def check_page(site_dir, page_name):
    fails = []
    p = site_dir / page_name
    if not p.is_file():
        return [f"{page_name}: file missing"]
    text = p.read_text(errors="replace")
    # v4: all code-level checks run on the comment-stripped copy
    # (same length, same offsets). HTML-level checks (ppStats element,
    # hydration markers — themselves comments) use the original text.
    code = _strip_comments(text)

    # 1. historySaleLabel — exactly one definition, role =
    #    sale-observed ONLY, plus a call site outside the definition.
    defs = _single_def(fails, code, page_name, "historySaleLabel")
    if len(defs) == 1:
        body = defs[0][2]
        if "セール観測" not in body or "Sale observed" not in body:
            fails.append(f"{page_name}: historySaleLabel body lacks the "
                         "sale-observed label")
        if "現在セール" in body:
            fails.append(f"{page_name}: historySaleLabel body contains "
                         "現在セール — the published helper handles "
                         "セール観測 only (role separation)")
        if call_sites(code, "historySaleLabel", defs) < 1:
            fails.append(f"{page_name}: historySaleLabel has no call site")

    # 2. varBlockHTML — current-sale derivation + label call + R3.
    defs = _single_def(fails, code, page_name, "varBlockHTML")
    if len(defs) == 1:
        body = defs[0][2]
        if not re.search(r"onSaleNow\s*=\s*!!s\[s\.length\s*-\s*1\]\[2\]", body):
            fails.append(f"{page_name}: varBlockHTML does not derive "
                         "onSaleNow from the latest point's sale flag "
                         "(pinned baseline shape)")
        if "historySaleLabel()" not in body:
            fails.append(f"{page_name}: varBlockHTML does not call "
                         "historySaleLabel() for the sale chip")
        if "pp-varprice" in body:
            fails.append(f"{page_name}: pp-varprice still present inside "
                         "varBlockHTML body (R3)")

    # 3. ppStats preserved.
    if 'id="ppStats"' not in text:
        fails.append(f"{page_name}: ppStats element missing "
                     "(must be preserved per dot correction)")
    if not re.search(r"getElementById\(\s*(['\"])ppStats\1\s*\)", code):
        fails.append(f"{page_name}: getElementById(\"ppStats\") reference missing")

    # 4. Negative cache in fetchMeta — pinned identifiers, HARD gate.
    if not re.search(r"const\s+_metaCache\s*=\s*new Map\(\)", code):
        fails.append(f"{page_name}: `const _metaCache = new Map()` missing")
    defs = _single_def(fails, code, page_name, "fetchMeta")
    if len(defs) == 1:
        body = defs[0][2]
        for token in ("_metaCache", "retryAt", "_metaCache.delete"):
            if token not in body:
                fails.append(f"{page_name}: fetchMeta body lacks {token} "
                             "(negative-cache mechanism)")
        if not re.search(r"Date\.now\(\)\s*\+\s*60000", body):
            fails.append(f"{page_name}: fetchMeta body lacks "
                         "`Date.now() + 60000` (60s negative-cache retry)")
        if call_sites(code, "fetchMeta", defs) < 1:
            fails.append(f"{page_name}: fetchMeta has no call site")

    # 5. DETAIL_HISTORY_HYDRATION block. The markers are comments, so
    #    they are located in the ORIGINAL text; the definitions inside
    #    the span are checked in the stripped copy (same offsets).
    start_marker = "// DETAIL_HISTORY_HYDRATION_START"
    end_marker = "// DETAIL_HISTORY_HYDRATION_END"
    si = text.find(start_marker)
    ei = text.find(end_marker, si + 1) if si >= 0 else -1
    if si < 0 or ei < 0:
        fails.append(f"{page_name}: DETAIL_HISTORY_HYDRATION markers missing "
                     "or out of order")
    else:
        span = code[si:ei]
        for fname in ("hasDetailHistory", "detailHistoryRequest", "openItemSmart"):
            if f"function {fname}(" not in span:
                fails.append(f"{page_name}: {fname} definition missing inside "
                             "the DETAIL_HISTORY_HYDRATION block")
        defs = _single_def(fails, code, page_name, "openItemSmart")
        if len(defs) == 1 and call_sites(code, "openItemSmart", defs) < 1:
            fails.append(f"{page_name}: openItemSmart has no call site")

    # 6. 2625416 verifiedThumbnail correction — guard-level (v4):
    #    exactly one definition whose body carries the item guard
    #    branch returning the full corrected URL; the ORIGINAL
    #    confirmation-time literal is present unaltered; the
    #    image-missing-only application guard is present; and there
    #    is a call site.
    defs = _single_def(fails, code, page_name, "verifiedThumbnail")
    if len(defs) == 1:
        body = defs[0][2]
        if not re.search(r'String\(id\)\s*===\s*"2625416"', body):
            fails.append(f"{page_name}: verifiedThumbnail body lacks the "
                         "2625416 item guard branch")
        if CORRECTED_2625416_URL not in body:
            fails.append(f"{page_name}: verifiedThumbnail does not return "
                         "the corrected 2625416 pximg URL")
        if call_sites(code, "verifiedThumbnail", defs) < 1:
            fails.append(f"{page_name}: verifiedThumbnail has no call site")
    if PINNED_2625416_CONFIRMED_AT not in code:
        fails.append(f"{page_name}: pinned 2625416 confirmation time "
                     f"{PINNED_2625416_CONFIRMED_AT} missing or altered "
                     "(evidence times are never refreshed)")
    if not re.search(r"!\s*\(\s*meta\s*&&\s*\(\s*meta\.image_resized\s*"
                     r"\|\|\s*meta\.image\s*\)\s*\)", code):
        fails.append(f"{page_name}: image-missing-only application guard "
                     "for verifiedThumbnail missing")

    return fails


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    site_dir = Path(argv[1])
    fails = []
    for page in ("index.html", "item.html"):
        fails.extend(check_page(site_dir, page))
    if fails:
        for f in fails:
            print(f"::error::{f}")
        return 1
    print("UI regression checks OK (index.html and item.html, per page, "
          "brace-matched function bodies)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
