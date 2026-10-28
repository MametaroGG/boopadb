const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {JSDOM}=require('jsdom');
const css=fs.readFileSync(path.join(__dirname,'../image-search.css'),'utf8');
test('result cards stretch their content and anchor the price/action group without truncating titles',()=>{
 for(const lang of ['ja','en','ko','zh-Hans','zh-Hant'])for(const theme of ['dark','light']){
  const title={ja:'長い商品名と対応アバターについての説明',en:'A long descriptive product title with supported avatars',ko:'지원 아바타에 관한 설명이 포함된 긴 상품명','zh-Hans':'包含支持角色说明的较长商品名称','zh-Hant':'包含支援角色說明的較長商品名稱'}[lang];
  const dom=new JSDOM(`<html lang="${lang}" data-theme="${theme}"><head><style>${css}</style></head><body><div class="image-result-grid">${[1,3].map(n=>`<article class="image-result"><a href="#"><img src="x" alt=""></a><div class="image-result-body"><h3>${title.repeat(n)}</h3><p>Shop ${'long name '.repeat(n)}</p><div class="image-result-price">¥1,500</div><p><a href="#">BOOTH ↗</a></p><button data-bookmark="1">${n===1?'ブックマーク':'ブックマーク済み'}</button></div></article>`).join('')}</div></body></html>`);
  try{const d=dom.window.document,style=n=>dom.window.getComputedStyle(n);
   for(const card of d.querySelectorAll('.image-result')){
    assert.equal(style(card).display,'flex');assert.equal(style(card).flexDirection,'column');
    const body=card.querySelector('.image-result-body');assert.equal(style(body).display,'flex');assert.equal(style(body).flexDirection,'column');assert.equal(style(body).flexGrow,'1');
    assert.equal(style(body.querySelector('.image-result-price')).marginTop,'auto');assert.equal(body.lastElementChild.tagName,'BUTTON');
    assert.equal(style(body.lastElementChild).width,'100%');assert.equal(style(body.lastElementChild).minHeight,'44px');
    assert.ok(body.querySelector('h3').textContent.includes(title));assert.notEqual(style(body.querySelector('h3')).whiteSpace,'nowrap');
   }
  }finally{dom.window.close();}
 }
});
test('alignment is shared across grid widths and does not introduce fixed card heights or line clamps',()=>{
 assert.match(css,/\.image-result-grid\{display:grid;grid-template-columns:repeat\(auto-fill,minmax\(160px,1fr\)\)/);
 assert.match(css,/@media\(max-width:650px\)/);assert.match(css,/\.image-result-grid\{grid-template-columns:repeat\(2,minmax\(0,1fr\)\)\}/);
 assert.doesNotMatch(css,/line-clamp/);
 const rules=css.match(/\.image-result(?:-body)?\{[^}]+\}/g).join('');assert.doesNotMatch(rules,/(?:^|;)height:/);
});
