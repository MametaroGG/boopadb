// Structural/CSS contract tests, NOT browser layout tests (jsdom does not lay out).
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {JSDOM} = require('jsdom');
const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
const dom = new JSDOM(html);
const document = dom.window.document;
function rule(selector, media) {
  const found = [];
  function visit(rules, condition) {
    for (const r of rules) {
      if (r.cssRules) visit(r.cssRules, r.conditionText);
      else if (r.selectorText === selector && condition === media) found.push(r.style);
    }
  }
  for (const sheet of document.styleSheets) visit(sheet.cssRules);
  assert.ok(found.length, `Missing CSS rule ${selector}`);
  return found.at(-1);
}
function px(value) { assert.match(value, /^\d+px$/); return Number.parseFloat(value); }
test('search shell stays border-box and bounded, with shrinkable text input', () => {
  assert.equal(rule('*').getPropertyValue('box-sizing'), 'border-box');
  assert.equal(rule('.sp-inner').width, '100%');
  assert.equal(rule('.sp-inner')['min-width'], '0');
  assert.equal(rule('.sp-search')['max-width'], '100%');
  const input = rule('.sp-search input#spQ');
  assert.equal(input.flex, '1 1 0%');
  assert.equal(input.width, '0');
  assert.equal(input['min-width'], '0');
  assert.equal(document.querySelector('#spQ').parentElement.className, 'sp-search');
  assert.ok(document.querySelector('#spQ').parentElement.contains(document.querySelector('#spImgBtn')));
});
test('camera offset outranks the later generic clear-button offset', () => {
  assert.equal(rule('.sp-search .sp-imgbtn').right, '8px');
  assert.equal(rule('.sp-search.has-query .sp-imgbtn').right, '54px');
  assert.equal(rule('.sp-search input#spQ')['padding-right'], '58px');
  assert.equal(rule('.sp-search.has-query input#spQ')['padding-right'], '104px');
  assert.equal(rule('.sp-clear').right, '8px');
});
test('CSS box-budget at phone, iPad portrait/landscape and desktop widths', () => {
  const inner = rule('.sp-inner');
  const leftInset = px(rule('.sp-inner', '(min-width:900px)')['padding-left']);
  const search = rule('.sp-search');
  const horizontalPadding = px(search.padding.split(' ')[1]);
  const icon = px(rule('.sp-search svg').width), gap = px(search.gap);
  const reservedControls = px(rule('.sp-search.has-query input#spQ')['padding-right']);
  const camera = rule('.sp-search.has-query .sp-imgbtn'), clear = rule('.sp-clear');
  const controlWidth = px(clear.width);
  for (const viewport of [320,375,768,810,899,900,1080,1194,1280,1920]) {
    // Model these declared CSS constraints only, not actual WebKit rendering.
    // Use 10px for a desktop scrollbar, conservatively even on overlay-scrollbar iPad.
    const outerWidth = Math.min(viewport - 32 - 10, px(inner['max-width']));
    const contentWidth = outerWidth - (viewport >= 900 ? leftInset : 0);
    const inputWidth = contentWidth - 2 - horizontalPadding * 2 - icon - gap;
    assert.ok(inputWidth > reservedControls, `${viewport}: text still has positive space`);
    assert.ok(px(camera.right) >= px(clear.right) + controlWidth, `${viewport}: buttons do not overlap`);
    assert.ok(contentWidth + (viewport >= 900 ? leftInset : 0) <= viewport - 32,
      `${viewport}: search content respects viewport margins`);
  }
});
