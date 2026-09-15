/* Shared presentation-only language switch. Never fetches source data. */
(() => {
  'use strict';
  let language='zh-TW';
  const original=new WeakMap(), attributes=new WeakMap(), titles=new Map();
  const linkTitles=new Map(), initialTitle=document.title;
  const normalize=s=>String(s).replace(/\s+/g,' ').trim();
  const hasZh=s=>/[\u3400-\u9fff]/u.test(s);
  const escape=s=>s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
  const catalog={...(window.WARHUB_EN||{})};
  // The existing icon renderer replaces emoji with SVG before translation.
  // Keep matching whole labels after that presentation change.
  const withoutIcons=s=>normalize(s.replace(/[\p{Extended_Pictographic}\p{Regional_Indicator}\uFE0F\u200D]/gu,''));
  for(const [zh,en] of Object.entries(catalog)){
    const plain=withoutIcons(zh);
    if(plain&&plain!==zh&&!Object.hasOwn(catalog,plain))catalog[plain]=withoutIcons(en);
  }
  let phrases, titlePhrases;
  const numeric=[];
  for(const [zh,en] of Object.entries(catalog)) {
    const numbers=zh.match(/\d+(?:[.,:]\d+)*/g);
    if(!numbers||!hasZh(zh))continue;
    const unused=numbers.map((value,index)=>({value,index}));
    const format=en.replace(/\d+(?:[.,:]\d+)*/g,n=>{
      const pos=unused.findIndex(x=>x.value===n);
      return pos<0?n:'\u0001'+unused.splice(pos,1)[0].index+'\u0001';
    });
    if(unused.length)continue;
    const pieces=zh.split(/\d+(?:[.,:]\d+)*/g);
    numeric.push([new RegExp('^'+pieces.map(escape).join('(\\d+(?:[.,:]\\d+)*)')+'$'),format]);
  }
  function rebuild(){
    const keys=Object.keys(catalog).filter(Boolean).sort((a,b)=>b.length-a.length);
    phrases=keys.length?new RegExp(keys.map(escape).join('|'),'gu'):null;
    const names=[...titles.keys()].filter(Boolean).sort((a,b)=>b.length-a.length);
    titlePhrases=names.length?new RegExp(names.map(escape).join('|'),'gu'):null;
  }
  function english(text){
    const clean=normalize(text);
    if(!clean)return text;
    if(titles.has(clean))return titles.get(clean);
    if(Object.hasOwn(catalog,clean))return catalog[clean];
    for(const [pattern,format] of numeric){
      const m=pattern.exec(clean);
      if(m)return format.replace(/\u0001(\d+)\u0001/g,(_,i)=>m[Number(i)+1]);
    }
    // Freeze exact article/contract titles before UI fragment translation.
    const held=[];
    let value=titlePhrases?text.replace(titlePhrases,s=>{
      held.push(titles.get(s));return '\u0002'+(held.length-1)+'\u0002';
    }):text;
    value=phrases?value.replace(phrases,(s,offset,whole)=>{
      let translated=catalog[s];
      if(/[A-Za-z0-9]/.test(whole[offset-1]||'')&&/^[A-Za-z]/.test(translated))translated=' '+translated;
      if(/[A-Za-z]$/.test(translated)&&/[A-Za-z0-9]/.test(whole[offset+s.length]||''))translated+=' ';
      return translated;
    }):value;
    return value.replace(/\u0002(\d+)\u0002/g,(_,i)=>held[Number(i)]);
  }
  function text(value){return language==='en'?english(value):String(value);}
  function registerData(data){
    for(const [zh,en] of Object.entries(data.english_translation_cache||{}))if(hasZh(zh)&&typeof en==='string'&&!hasZh(en))titles.set(normalize(zh),en);
    const rows=[...(data.news||[]),...(data.tw_news||[]),...(data.polymarket||[]),
      ...(data.taiwan_insight?.markets||[]),...(data.taiwan_insight?.timeline||[]),
      ...(data.taiwan_insight?.news_observations||[])];
    for(const row of rows){
      const zh=row.question_zh||row.title_zh||row.title;
      const candidates=[row.title_english,row.question,row.title_en,row.title];
      const en=candidates.find(x=>typeof x==='string'&&x.trim()&&!hasZh(x));
      if(typeof zh==='string'&&hasZh(zh)&&(en||row.kind!=='official')&&(en||!titles.has(normalize(zh))))titles.set(normalize(zh),en||'English translation unavailable (open source)');
      if(en){
        if(row.url)linkTitles.set(row.url,en);
        if(row.slug)linkTitles.set('https://polymarket.com/market/'+encodeURIComponent(row.slug),en);
      }
    }
    rebuild();
    if(language==='en')apply(document.body);
  }
  function updateNode(node){
    if(!node.parentElement||node.parentElement.closest('script,style,[data-language-control]'))return;
    let saved=original.get(node);
    if(!saved||node.nodeValue!==saved.last)saved={zh:node.nodeValue,last:node.nodeValue};
    const sourceTitle=linkTitles.get(node.parentElement.closest('a')?.href);
    let next=language==='en'?(saved.zh.includes('中文翻譯暫時無法取得')&&sourceTitle?sourceTitle:english(saved.zh)):saved.zh;
    if(language==='en'&&saved.zh.trim())next=saved.zh.match(/^\s*/)[0]+next.trim()+saved.zh.match(/\s*$/)[0];
    if(language==='en'&&node.parentElement.closest('.news-src')&&hasZh(next))next='— Source (name in Chinese mode)';
    if(node.nodeValue!==next)node.nodeValue=next;
    saved.last=next;original.set(node,saved);
  }
  function updateAttributes(el){
    if(el.closest('[data-language-control]'))return;
    let saved=attributes.get(el)||{};
    for(const key of ['title','aria-label','alt','placeholder']){
      if(!el.hasAttribute(key))continue;
      const current=el.getAttribute(key);
      if(!saved[key]||current!==saved[key].last)saved[key]={zh:current,last:current};
      const next=language==='en'?english(saved[key].zh):saved[key].zh;
      if(current!==next)el.setAttribute(key,next);
      saved[key].last=next;
    }
    attributes.set(el,saved);
  }
  function apply(root){
    if(root.nodeType===3){updateNode(root);return;}
    if(root.nodeType!==1)return;
    updateAttributes(root);
    const walk=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);let node;
    while(node=walk.nextNode())updateNode(node);
    for(const el of root.querySelectorAll('[title],[aria-label],[alt],[placeholder]'))updateAttributes(el);
  }
  function select(next){
    if(!['zh-TW','en'].includes(next))return;
    if(next==='en'&&!Object.keys(catalog).length)return;
    language=next;document.documentElement.lang=next;
    document.title=next==='en'?english(initialTitle):initialTitle;
    apply(document.body);
    for(const b of document.querySelectorAll('[data-language]'))b.setAttribute('aria-pressed',String(b.dataset.language===next));
    document.dispatchEvent(new CustomEvent('warhub-language-change',{detail:{language:next}}));
  }
  window.WarhubI18n={text,registerData,select,get language(){return language;}};
  rebuild();
  function start(){
    // No local/sessionStorage or browser-language preference: fresh opens use Chinese.
    select('zh-TW');
    for(const button of document.querySelectorAll('[data-language]'))button.addEventListener('click',()=>select(button.dataset.language));
    if(!Object.keys(catalog).length){
      const button=document.querySelector('[data-language="en"]');
      if(button){button.disabled=true;button.title='英文資源載入失敗，請重新整理';}
    }
    new MutationObserver(records=>{
      for(const record of records){
        if(record.type==='characterData')updateNode(record.target);
        else if(record.type==='attributes')updateAttributes(record.target);
        else for(const node of record.addedNodes)apply(node);
      }
    }).observe(document.body,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['title','aria-label','alt','placeholder']});
    // Canvas labels use the same catalogue; SVG labels are ordinary DOM text.
    const proto=window.CanvasRenderingContext2D?.prototype;
    if(proto){
      for(const method of ['fillText','strokeText','measureText']){
        const native=proto[method];
        proto[method]=function(value,...args){return native.call(this,text(value),...args);};
      }
    }
    document.dispatchEvent(new Event('warhub-i18n-ready'));
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
})();
