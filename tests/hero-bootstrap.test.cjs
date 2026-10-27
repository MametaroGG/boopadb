const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
const full = JSON.parse(fs.readFileSync(path.join(root, 'lists_full.json'), 'utf8'));
function between(start, end) { return html.slice(html.indexOf(start), html.indexOf(end, html.indexOf(start))); }
function harness() {
  let writes = 0;
  const slide = () => ({dataset: {}, classList: {remove(){}}, cloneNode(){return slide();}});
  const track = {children: [], appendChild(x){this.children.push(x);}, insertBefore(x){this.children.unshift(x);},
    set innerHTML(s){writes++; this.children = Array.from({length: (s.match(/<slide>/g)||[]).length}, slide);}};
  const dotsEl = {querySelectorAll(){return [];}};
  const context = vm.createContext({track, dotsEl, console, tr: (k, args) => k + JSON.stringify(args || {}), yen: String,
    ribOf: () => ['sale', 'sale'], htagsArr: () => [], fillHeroMetas(){}, heroSlideHTML: () => '<slide>',
    heroPos(p){context.position = p;}, heroGo(){}, heroPlay(){throw Error('timer must not restart');}});
  vm.runInContext(between('function heroNormSale(', 'const track =') + '\nlet hi = 0, HN = heroItems.length; let heroTimer = 123;\n' +
    between('function buildHero(', 'document.getElementById("heroPrev")') +
    between('function renderHeroFromLists(', 'function renderFeatFromNewest(') + '\nbuildHero(heroItems);', context);
  return {context, run: s => vm.runInContext(s, context), writes: () => writes};
}
test('embedded six equal full-catalog selection on initial paint', () => {
  const h = harness(); h.context.full = full;
  assert.equal(h.run('heroItems.length'), 6);
  assert.equal(h.run('String(heroItems[0].id)'), h.run('String(selectHeroEntries(full)[0].item.id)'));
  assert.equal(h.run('heroSignature(normalizeHeroEntries(selectHeroEntries(full))) === heroRenderedSignature'), true);
});
test('unchanged fetch preserves nodes, position, timer including enriched metadata', () => {
  const h = harness(); h.context.full = full;
  const nodes = h.context.track.children.slice();
  h.run('hi = 3; heroItems[0].likes = 999999; heroItems[0].tags = ["enriched"]; renderHeroFromLists(full); renderHeroFromLists(full);');
  assert.equal(h.writes(), 1);
  assert.deepEqual(h.context.track.children, nodes);
  assert.equal(h.run('hi'), 3);
  assert.equal(h.run('heroTimer'), 123);
});
test('same IDs but changed price/text updates and preserves current product', () => {
  const h = harness(); h.context.full = structuredClone(full);
  h.run('hi = 3;'); const id = h.run('String(heroItems[hi].id)');
  const firstId = h.run('String(heroItems[0].id)');
  const first = h.context.full.newest.find(x => String(x.id) === firstId);
  first.cur += 100; first.name += ' updated';
  h.run('renderHeroFromLists(full)');
  assert.equal(h.writes(), 2);
  assert.equal(h.run('String(heroItems[hi].id)'), id);
  assert.equal(h.context.position, 4);
  assert.equal(h.run('heroItems[0].cur'), first.cur);
  assert.equal(h.run('heroItems[0].name'), first.name);
  assert.equal(h.context.track.children.length, 8); // six slides plus loop clones
  h.run('renderHeroFromLists(full)'); assert.equal(h.writes(), 2);
});
test('ranking change preserves selected product; removed product resets safely', () => {
  const h = harness(); h.context.full = structuredClone(full);
  h.run('hi = 2;'); const id = h.run('String(heroItems[hi].id)');
  h.context.full.newest.find(x => String(x.id) === id).likes = 999999;
  h.run('renderHeroFromLists(full)');
  assert.equal(h.run('String(heroItems[hi].id)'), id);
  assert.equal(h.run('hi'), 0);
  for (const key of ['newest', 'on_sale']) h.context.full[key] = h.context.full[key].filter(x => String(x.id) !== id);
  h.run('renderHeroFromLists(full)');
  assert.equal(h.run('hi'), 0); assert.equal(h.context.position, 1);
  assert.equal(h.run('heroTimer'), 123);
});
test('selector caps at six unique valid items even with overlaps, never mutates catalog', () => {
  const h = harness();
  const items = Array.from({length:10}, (_, i) => ({id:i, likes:10-i, image:'x', base:100}));
  h.context.input = {newest:items, on_sale:items};
  const before = JSON.stringify(h.context.input);
  assert.equal(h.run('selectHeroEntries(input).length'), 6);
  assert.equal(h.run('new Set(selectHeroEntries(input).map(x => x.item.id)).size'), 6);
  assert.equal(JSON.stringify(h.context.input), before);
  h.context.input = {newest: [{id:1, image:'x', likes:3, base:100001}], on_sale:[]};
  assert.equal(h.run('selectHeroEntries(input).length'), 0);
  h.run('renderHeroFromLists(input)'); assert.equal(h.writes(), 1);
});
