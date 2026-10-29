/* Reviewed relationship UI. Production activation remains separately gated.
 * Snapshot provenance approved; runtime integration still under local review.
 * Never map refs/base_refs/category heuristics into this model.
 */
(function(root, factory){
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.BoopaRelationshipDraft = factory();
})(typeof globalThis !== 'undefined' ? globalThis : this, function(){
  'use strict';
  const kinds = ['parents', 'prerequisites', 'thumbnail'];
  const labels = {
    ja: ['親作品', '動作に必要な作品・ツール', 'サムネイルに使用された作品', '関係情報は未確認です', '確認済みの関係はありません', '商品情報を取得できません', '無料', '前へ', '次へ'],
    en: ['Parent works', 'Required works and tools', 'Works used in the thumbnail', 'Relationships not verified', 'No verified relationships', 'Product information unavailable', 'Free', 'Previous', 'Next'],
    ko: ['부모 작품', '작동에 필요한 작품·도구', '썸네일에 사용된 작품', '관계 정보 미확인', '확인된 관계 없음', '상품 정보를 가져올 수 없습니다', '무료', '이전', '다음'],
    'zh-Hans': ['父作品', '运行所需的作品和工具', '缩略图中使用的作品', '关系信息尚未确认', '没有已确认的关系', '无法获取商品信息', '免费', '上一页', '下一页'],
    'zh-Hant': ['父作品', '執行所需的作品與工具', '縮圖中使用的作品', '關係資訊尚未確認', '沒有已確認的關係', '無法取得商品資訊', '免費', '上一頁', '下一頁']
  };
  const childrenLabels = {ja:['子作品','もっと見る','表示'],en:['Derivative works','Show more','Shown'],ko:['파생 작품','더 보기','표시'], 'zh-Hans':['子作品','查看更多','显示'],'zh-Hant':['子作品','查看更多','顯示']};
  const capLabels={ja:'子作品は人気順で最大2,000件まで表示します。',en:'Up to 2,000 derivative works are available, sorted by popularity.',ko:'인기순으로 최대 2,000개의 파생 작품을 표시합니다.','zh-Hans':'按人气顺序最多显示2,000个子作品。','zh-Hant':'按人氣順序最多顯示2,000個子作品。'};
  const allKinds = [...kinds, 'children'];
  const visibleIds = (model,kind,options) => (model.groups[kind] || []).slice(0,(options.limits && options.limits[kind]) || 30);
  const esc = value => String(value == null ? '' : value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const idOf = value => typeof value === 'string' && /^[1-9]\d{0,15}$/.test(value) ? value : null;
  // All three groups must have explicit reviewed arrays. {} is UNKNOWN, not empty.
  function adaptSynthetic(input, selfId){
    const unknown = {status:'unknown', groups:{}};
    if (!input || input.schema !== 'synthetic-relationship-view-v1' || input.reviewed !== true || !kinds.every(k => Array.isArray(input[k]))) return unknown;
    return normalizeGroups(input, selfId);
  }
  function normalizeGroups(input, selfId){
    const unknown = {status:'unknown', groups:{}};
    const groups = {};
    for (const kind of kinds) {
      const seen = new Set(); groups[kind] = [];
      for (const raw of input[kind]) {
        const id = idOf(raw);
        if (!id) return unknown; // malformed data is not evidence of absence
        if (id !== selfId && !seen.has(id)) { seen.add(id); groups[kind].push(id); }
      }
    }
    return {status:'verified', groups};
  }
  // Approval belongs to the caller; passing structural checks is NOT approval.
  // Optional correctedVerdicts provides explicit reviewed-none coverage. An
  // absent full row alone never proves absence; nonempty omitted rows are errors.
  function adaptGenerated(full, selfId, options = {}){
    const unknown = {status:'unknown', groups:{}};
    const has = (o,k) => o && Object.prototype.hasOwnProperty.call(o,k);
    const shape = v => v && typeof v === 'object' && !Array.isArray(v) && kinds.every(k => has(v,k) && Array.isArray(v[k]));
    if (options.artifactVerified !== true || !idOf(selfId) || !full || typeof full !== 'object' || Array.isArray(full)) return unknown;
    const master = options.correctedVerdicts;
    if (!has(full,selfId)) {
      const none = has(master,selfId) && master[selfId];
      return shape(none) && kinds.every(k => none[k].length === 0) ? normalizeGroups(none,selfId) : unknown;
    }
    const entry = full[selfId];
    if (!shape(entry)) return unknown;
    const model = normalizeGroups(entry,selfId);
    if (master) {
      if (!has(master,selfId) || !shape(master[selfId])) return unknown;
      const reviewed = normalizeGroups(master[selfId],selfId);
      if (reviewed.status !== 'verified' || JSON.stringify(reviewed.groups) !== JSON.stringify(model.groups)) return unknown;
    }
    return model;
  }
  function safeImage(value){
    try { const u = new URL(value); return u.protocol === 'https:' && !u.username && !u.password ? u.href : ''; } catch { return ''; }
  }
  function card(id, meta, index, options){
    const l = labels[options.lang] || labels.ja;
    const img = safeImage(meta && (meta.image_resized || meta.image));
    // Existing bookmark helper receives validated digits only. It is trusted app code.
    const bookmark = options.bookmarkHTML ? options.bookmarkHTML(id) : '';
    const href = 'item.html?id=' + id;
    const price = meta && typeof meta.price === 'number' && Number.isFinite(meta.price) && meta.price >= 0 ? meta.price : null;
    const priceText = price === null ? '—' : price === 0 ? l[6] : '¥' + price.toLocaleString('ja-JP');
    return `<div class="card" data-pid="${id}" style="animation-delay:${index % 30 * 45}ms"><a class="thumbwrap" href="${href}">${img ? `<img decoding="async" src="${esc(img)}" alt="" loading="lazy" referrerpolicy="no-referrer">` : '<span class="phcard" aria-hidden="true"></span>'}${bookmark}</a><div class="cbody"><div class="cname"><a href="${href}">${esc(meta && meta.name || l[5] + ' (#' + id + ')')}</a></div><div class="cshop">${esc(meta && meta.shop && meta.shop.name)}</div><div class="crow"><span class="price solo">${esc(priceText)}</span></div></div></div>`;
  }
  function render(model, metadata, options = {}){
    model = {...model,groups:model.groups || {}};
    const l = labels[options.lang] || labels.ja;
    const cl = childrenLabels[options.lang] || childrenLabels.ja;
    let html = model.status !== 'verified' ? `<p role="status">${esc(l[3])}</p>` : '';
    allKinds.forEach((kind, index) => {
      const ids = visibleIds(model,kind,options);
      const total = kind === 'children' ? model.childrenTotal : (model.groups[kind] || []).length;
      const title = kind === 'children' ? cl[0] : l[index];
      if (!ids.length) return;
      // data attribute, rather than a global ID, supports independently mounted hosts.
      html += `<section data-relation-kind="${kind}" aria-label="${esc(title)}"><div class="pp-sec">${esc(title)}（${total}）</div><div class="relwrap"><div class="relrow">${ids.map((id,i) => card(id, metadata[id], i, options)).join('')}</div><button type="button" class="relbtn prev" data-draft-rel-scroll="-1" aria-label="${esc(l[7])}">‹</button><button type="button" class="relbtn next" data-draft-rel-scroll="1" aria-label="${esc(l[8])}">›</button></div>${(model.groups[kind] || []).length > ids.length ? `<button type="button" class="relmore" data-relation-more="${kind}">${esc(cl[1])}</button>` : ''}${kind === 'children' && total > ids.length ? `<span class="cshop">${esc(cl[2])}: ${ids.length} / ${total}</span>` : ''}${kind === 'children' && total > (model.groups.children || []).length ? `<p class="cshop">${esc(capLabels[options.lang] || capLabels.ja)}</p>` : ''}</section>`;
    });
    return html || `<p role="status">${esc(l[4])}</p>`;
  }
  // Every mount invalidates older responses, including A -> B -> A and same-ID retries.
  const mounts = new WeakMap();
  async function mountModel(host, model, options = {}){
    const previous=mounts.get(host);if(previous && previous.observer)previous.observer.disconnect();
    const token = {}; mounts.set(host, token);
    const current = () => mounts.get(host) === token && host.isConnected && (!options.isCurrent || options.isCurrent());
    if (!current()) return false;
    const metadata=options._metadata || Object.create(null);
    const sync=()=>host.querySelectorAll('.relrow').forEach(row=>row.parentElement.classList.toggle('hasmore',row.scrollWidth-row.clientWidth>8));
    const imageFallback=()=>host.querySelectorAll('img').forEach(img=>{img.onerror=()=>{const placeholder=host.ownerDocument.createElement('span');placeholder.className='phcard';img.replaceWith(placeholder);};});
    // Render relationships immediately: slow metadata must not hide known edges.
    host.innerHTML = render(model, metadata, options);
    host.onclick = e => {
      const more=e.target.closest('[data-relation-more]');
      if(more && host.contains(more)){const k=more.dataset.relationMore;const limits={...options.limits,[k]:((options.limits&&options.limits[k])||30)+30};mountModel(host,model,{...options,limits,_metadata:metadata});return;}
      const b=e.target.closest('[data-draft-rel-scroll]');if(!b||!host.contains(b))return;
      const row=b.parentElement.querySelector('.relrow');row.scrollBy({left:Number(b.dataset.draftRelScroll)*row.clientWidth*.9,behavior:'smooth'});
    };
    sync();imageFallback();
    const ViewResizeObserver=host.ownerDocument.defaultView.ResizeObserver;
    if(ViewResizeObserver){token.observer=new ViewResizeObserver(sync);token.observer.observe(host);}
    const ids=[...new Set(allKinds.flatMap(k=>visibleIds(model,k,options)))].filter(id=>!Object.prototype.hasOwnProperty.call(metadata,id));
    let cursor=0;
    await Promise.all(Array.from({length:Math.min(6,ids.length)},async()=>{
      while(current() && cursor<ids.length){const id=ids[cursor++];let timer;let value;
        try{value=options.fetchMeta?await Promise.race([options.fetchMeta(id),new Promise(resolve=>{timer=setTimeout(()=>resolve(null),options.metadataTimeoutMs||8000);})]):null;}
        catch{value=null;}finally{clearTimeout(timer);}
        if(!current())return;
        metadata[id]=value;
        host.querySelectorAll(`[data-pid="${id}"]`).forEach(node=>{node.outerHTML=card(id,value,0,options);});
        imageFallback();sync();
      }
    }));
    if(!current() && token.observer)token.observer.disconnect();
    return current();
  }
  function mount(host, selfId, input, options = {}){
    return mountModel(host, adaptSynthetic(input, selfId), options);
  }
  function mountGenerated(host, selfId, full, options = {}){
    return mountModel(host, adaptGenerated(full, selfId, options), options);
  }
  function mountSnapshot(host,selfId,snapshot,options={}){
    const full = snapshot.status==='loaded' && snapshot.entry ? {[selfId]:snapshot.entry} : {};
    const model = adaptGenerated(full,selfId,{artifactVerified:snapshot.status==='loaded'});
    model.groups.children = snapshot.status==='loaded' ? snapshot.children : [];
    model.childrenTotal = snapshot.status==='loaded' ? snapshot.childrenTotal : 0;
    return mountModel(host,model,options);
  }
  function cancel(host){ const token=mounts.get(host);if(token&&token.observer)token.observer.disconnect();mounts.delete(host); host.onclick = null; host.innerHTML = ''; }
  return {adaptSynthetic, adaptGenerated, render, mount, mountGenerated, mountSnapshot, cancel, labels};
});
