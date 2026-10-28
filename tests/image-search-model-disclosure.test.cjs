const test=require('node:test'), assert=require('node:assert/strict'), fs=require('node:fs'), path=require('node:path'), vm=require('node:vm');
const sandbox={window:{}};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../image-search-faq.js'),'utf8'),sandbox);
const localServer={ja:/運営者のサーバー/,en:/operator's server/,ko:/운영자의 서버/, 'zh-Hans':/运营者的服务器/,'zh-Hant':/營運者的伺服器/};
const scopedNoAPI={ja:/この画像検索処理.*Googleの外部AI APIへ送信することはありません/,en:/not sent to Google's external AI APIs for this image-search processing/,ko:/이 이미지 검색 처리.*Google의 외부 AI API로 전송하지 않습니다/,'zh-Hans':/此图片搜索处理.*不会将图片发送到 Google 的外部 AI API/,'zh-Hant':/此圖片搜尋處理.*不會將圖片傳送到 Google 的外部 AI API/};
for(const lang of Object.keys(localServer))test(`image-search model disclosure is specific and localized: ${lang}`,()=>{
 const faq=sandbox.window.IMAGE_SEARCH_FAQ[lang];
 assert.equal(faq.cards.length,3);assert.equal(faq.items.length,8);
 const answer=faq.items[0].a;
 assert.match(answer,/Google/);assert.match(answer,/EmbeddingGemma 2/);assert.match(answer,localServer[lang]);assert.match(answer,scopedNoAPI[lang]);
 assert.equal(faq.items.filter(x=>x.a.includes('EmbeddingGemma 2')).length,1);
});
