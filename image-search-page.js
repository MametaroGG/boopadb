/* Lightweight standalone host. The lens/crop/search engine is shared with index.html. */
'use strict';
const IMG_API = 'https://nucbox-m7.tailb48431.ts.net:8443';
const I18N = window.IMAGE_SEARCH_I18N || {ja:{}};
let LANG = 'ja', THEME = 'dark';
const readStore=(key,fallback)=>{try{return JSON.parse(localStorage.getItem(key)) ?? fallback;}catch{return fallback;}};
try {
 const lang=localStorage.getItem('boopadb_lang'); const n=(navigator.language||'ja').toLowerCase();
 LANG=I18N[lang]?lang:n.startsWith('en')?'en':n.startsWith('ko')?'ko':n.startsWith('zh')?(n.includes('tw')||n.includes('hk')||n.includes('hant')?'zh-Hant':'zh-Hans'):'ja';
 const theme=localStorage.getItem('boopadb_theme');THEME=theme==='light'||theme==='dark'?theme:matchMedia('(prefers-color-scheme: light)').matches?'light':'dark';
}catch{}
function tr(k,v){let s=(I18N[LANG]&&I18N[LANG][k]) || I18N.ja[k] || k;if(v)for(const key in v)s=s.split('{'+key+'}').join(String(v[key]));return s;}
const el=id=>document.getElementById(id);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function applyImageLocale(){
 document.documentElement.lang=LANG;document.title=tr('img_search')+' | BoopaDB';
 document.querySelectorAll('[data-i]').forEach(n=>n.textContent=tr(n.dataset.i));
 document.querySelectorAll('[data-i-al]').forEach(n=>n.setAttribute('aria-label',tr(n.dataset.iAl)));
 el('imageLang').value=LANG;
 const copy=window.IMAGE_SEARCH_FAQ && (window.IMAGE_SEARCH_FAQ[LANG] || window.IMAGE_SEARCH_FAQ.ja);
 if(copy){
  el('imageExplain').innerHTML=copy.cards.map(c=>'<article><h2>'+esc(c.title)+'</h2><p>'+esc(c.body)+'</p></article>').join('');
  el('imageFaq').innerHTML='<h2 id="imageFaqTitle">'+esc(copy.title)+'</h2>'+copy.items.map(f=>'<details><summary>'+esc(f.q)+'</summary><p>'+esc(f.a)+'</p></details>').join('');
 }
}
function applyImageTheme(){document.documentElement.dataset.theme=THEME;document.querySelector('meta[name="color-scheme"]').content=THEME;}
applyImageLocale();applyImageTheme();
el('imageLang').addEventListener('change',()=>{LANG=el('imageLang').value;try{localStorage.setItem('boopadb_lang',LANG);}catch{}applyImageLocale();renderCurrentResults();});
el('imageTheme').addEventListener('click',()=>{THEME=THEME==='dark'?'light':'dark';try{localStorage.setItem('boopadb_theme',THEME);}catch{}applyImageTheme();});
el('imageSearchClose').addEventListener('click',()=>{
 // Browser Back restores the previous search scroll/filter state when possible.
 try { const from=new URL(document.referrer); const home=new URL('index.html',location.href);
  if(from.origin===home.origin && (from.pathname===home.pathname || from.pathname===home.pathname.replace(/index\.html$/,'')) && history.length>1){history.back();return;}
 }catch{}
 location.href='index.html';
});
function veilSync(){document.body.style.overflow=el('lensView').hidden?'':'hidden';}
function isoFD(n){if(!n)return '';const s=String(n);return s.slice(0,4)+'-'+s.slice(4,6)+'-'+s.slice(6,8);}
function pxImg(v){return !v?'':String(v).includes('://')?String(v):'https://booth.pximg.net/c/620x620/'+v+'_base_resized.jpg';}
let fullIndex=null, indexPromise=null, currentApiResults=[], resultRecords=new Map();
function loadImageCatalog(){
 if(indexPromise)return indexPromise;
 indexPromise=Promise.all(Array.from({length:24},(_,i)=>fetch('search_index_'+i+'.json').then(r=>{if(!r.ok)throw new Error('catalog');return r.json();}))).then(parts=>{
  fullIndex=parts.flat().map(([id,name,cur,base,lowest,sale,atlow,cat,likes,img,fd,pd,shop])=>[String(id),name,'',cur,base,lowest,sale,atlow,cat,likes,pxImg(img),fd,pd,shop]);
  if(currentApiResults.length)renderCurrentResults();return fullIndex;
 }).catch(()=>{indexPromise=null;return null;});return indexPromise;
}
function imgHitsFromApi(results){
 currentApiResults=Array.isArray(results)?results:[];
 const byId=new Map((fullIndex||[]).map(e=>[e[0],e]));
 const hits=currentApiResults.filter(r=>/^\d+$/.test(String(r.item_id))).map(r=>{
  const id=String(r.item_id),e=byId.get(id);
  return {id,name:e?e[1]:'BOOTH #'+id,shop:e?e[13]||'':'',image:r.image||(e&&e[10])||'',cur:e?e[3]:null,base:e?e[4]:null,sale:e?!!e[6]:false,at_lowest:e?!!e[7]:false};
 });resultRecords=new Map(hits.map(h=>[h.id,h]));return hits;
}
function savedBookmarks(){const b=readStore('boopadb_bm',[]);return Array.isArray(b)?b:[];}
function safeImage(url){try{const u=new URL(url);return /^https?:$/.test(u.protocol)?u.href:'';}catch{return '';}}
function saleCard(x){
 const saved=savedBookmarks().some(b=>String(b.id)===x.id),image=safeImage(x.image),price=x.cur==null?'':new Intl.NumberFormat(LANG,{style:'currency',currency:'JPY',maximumFractionDigits:0}).format(x.cur);
 return '<article class="image-result" data-id="'+esc(x.id)+'"><a href="index.html#item-'+encodeURIComponent(x.id)+'">'+(image?'<img src="'+esc(image)+'" alt="" loading="lazy" referrerpolicy="no-referrer">':'')+'</a><div class="image-result-body"><h3><a href="index.html#item-'+encodeURIComponent(x.id)+'">'+esc(x.name)+'</a></h3><p>'+esc(x.shop)+'</p><div class="image-result-price">'+(x.base>x.cur&&x.cur!=null?'<del>'+esc(new Intl.NumberFormat(LANG,{style:'currency',currency:'JPY',maximumFractionDigits:0}).format(x.base))+'</del> ':'')+esc(price)+(x.base>x.cur&&x.cur!=null?' <small>−'+Math.round((1-x.cur/x.base)*100)+'%</small>':'')+'</div><p><a href="https://booth.pm/'+LANG+'/items/'+encodeURIComponent(x.id)+'" target="_blank" rel="noopener">'+esc(tr('pp_booth'))+' ↗</a></p><button type="button" data-bookmark="'+esc(x.id)+'" aria-pressed="'+saved+'">'+esc(tr(saved?'pp_bmed':'pp_bm'))+'</button></div></article>';
}
function fillCardPrice(){} // Standalone result renderer already includes catalog prices.
function fillImgs(){if(!fullIndex)loadImageCatalog();}
function renderCurrentResults(){if(!currentApiResults.length)return;const hits=imgHitsFromApi(currentApiResults);el('lvResults').innerHTML=hits.map(saleCard).join('');el('lvCount').textContent=tr('sp_count',{n:hits.length});}
el('lvResults').addEventListener('click',e=>{
 const button=e.target.closest('[data-bookmark]');if(!button)return;
 const id=button.dataset.bookmark,record=resultRecords.get(id);if(!record)return;
 let saved=savedBookmarks();const exists=saved.some(b=>String(b.id)===id);
 saved=exists?saved.filter(b=>String(b.id)!==id):[{id:record.id,name:record.name,shop:record.shop,image:record.image,cur:record.cur},...saved];
 try{localStorage.setItem('boopadb_bm',JSON.stringify(saved));button.setAttribute('aria-pressed',String(!exists));button.textContent=tr(exists?'pp_bm':'pp_bmed');}catch{ /* Keep UI unchanged if storage is unavailable. */ }
});
el('spImgFile').addEventListener('change',()=>{if(el('spImgFile').files.length){currentApiResults=[];loadImageCatalog();}});
el('spImgDrop').addEventListener('drop',e=>{if(window.BoopaImageDrop && !BoopaImageDrop.validate(e.dataTransfer && e.dataTransfer.files)){currentApiResults=[];loadImageCatalog();}});
window.addEventListener('storage',e=>{if(e.key==='boopadb_bm')renderCurrentResults();});
