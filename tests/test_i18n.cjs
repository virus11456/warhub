const {JSDOM}=require('jsdom');
const fs=require('node:fs'),assert=require('node:assert/strict'),test=require('node:test');
const script=fs.readFileSync('i18n.js','utf8');
const tick=()=>new Promise(r=>setImmediate(r));
function create(catalog){
 const dom=new JSDOM('<html lang="zh-TW"><head><title>觀察網站</title></head><body><div data-language-control><button data-language="zh-TW">繁中</button><button data-language="en">English</button></div><p id="count" title="缺資料">已取得 40 筆／來源回報 600 筆</p><a id="news" href="https://example.com/article"><span>中文標題</span></a><svg><text>缺資料</text></svg></body></html>',{url:'https://warhub.test/',runScripts:'outside-only'});
 dom.window.WARHUB_EN=catalog;dom.window.fetch=()=>{throw Error('Language switch must not fetch')};
 dom.window.localStorage.setItem('language','en');dom.window.eval(script);
 dom.window.document.dispatchEvent(new dom.window.Event('DOMContentLoaded'));return dom;
}
const catalog={'觀察網站':'Observation site','已取得 40 筆／來源回報 600 筆':'Retrieved 40 of 600 reported notices','缺資料':'Missing data'};
test('defaults to Chinese, switches titles/attributes/SVG, preserves DOM and restores original',async()=>{
 const dom=create(catalog),w=dom.window,d=w.document;
 assert.equal(d.documentElement.lang,'zh-TW');
 const original=d.getElementById('count').textContent,link=d.getElementById('news');let clicked=0;
 link.addEventListener('click',e=>{e.preventDefault();clicked++});
 w.WarhubI18n.registerData({news:[{title_zh:'中文標題',title_en:'Original English headline',url:link.href}]});
 d.querySelector('[data-language="en"]').click();await tick();
 assert.equal(d.documentElement.lang,'en');assert.equal(d.title,'Observation site');
 assert.equal(d.querySelector('#news span').textContent,'Original English headline');
 assert.equal(d.querySelector('svg text').textContent,'Missing data');assert.equal(d.getElementById('count').title,'Missing data');
 link.click();assert.equal(clicked,1);assert.equal(link.href,'https://example.com/article');
 d.getElementById('count').textContent='已取得 20 筆／來源回報 700 筆';await tick();
 assert.equal(d.getElementById('count').textContent,'Retrieved 20 of 700 reported notices');
 d.querySelector('[data-language="zh-TW"]').click();await tick();
 assert.equal(d.getElementById('count').textContent,'已取得 20 筆／來源回報 700 筆');
 assert.equal(d.querySelector('#news span').textContent,'中文標題');
 assert.equal(d.title,'觀察網站');assert.notEqual(original,d.getElementById('count').textContent);
 dom.window.close();
 const reopened=create(catalog);assert.equal(reopened.window.document.documentElement.lang,'zh-TW');reopened.window.close();
});
test('dynamic title translations remain exact and missing English is explicit',async()=>{
 const dom=create(catalog),w=dom.window,d=w.document;
 w.WarhubI18n.registerData({english_translation_cache:{'中文標題':'Cached English headline'},taiwan_insight:{timeline:[{title:'中文標題'}]}});
 w.WarhubI18n.select('en');await tick();assert.equal(d.querySelector('#news span').textContent,'Cached English headline');
 w.WarhubI18n.registerData({news:[{title:'另一中文標題'}]});d.querySelector('#news span').textContent='另一中文標題';await tick();
 assert.equal(d.querySelector('#news span').textContent,'English translation unavailable (open source)');dom.window.close();
});
test('unknown publisher names are explicit in English and preserved in Chinese',async()=>{
 const dom=create(catalog),w=dom.window,d=w.document;
 const source=d.createElement('span');source.className='news-src';source.textContent='— 未建譯名媒體';d.body.appendChild(source);
 w.WarhubI18n.select('en');await tick();assert.equal(source.textContent,'— Source (name in Chinese mode)');
 w.WarhubI18n.select('zh-TW');await tick();assert.equal(source.textContent,'— 未建譯名媒體');dom.window.close();
});
test('inline emphasis keeps English words separated and restores Chinese',async()=>{
 const dom=create({...catalog,'先':'First','確認安全':'check safety','再求救':'then call for help'}),w=dom.window,d=w.document;
 const p=d.createElement('p');p.innerHTML='先<strong>確認安全</strong>再求救';d.body.appendChild(p);
 w.WarhubI18n.select('en');await tick();assert.equal(p.textContent,'First check safety then call for help');
 w.WarhubI18n.select('zh-TW');await tick();assert.equal(p.textContent,'先確認安全再求救');dom.window.close();
});
test('failed catalogue load keeps Chinese rather than claiming English mode',()=>{
 const dom=create({});dom.window.WarhubI18n.select('en');
 assert.equal(dom.window.document.documentElement.lang,'zh-TW');assert.equal(dom.window.document.querySelector('[data-language="en"]').disabled,true);dom.window.close();
});
test('relative ages preserve counts and use singular English only for one',()=>{
 const dom=create(catalog),w=dom.window;w.WarhubI18n.select('en');
 assert.equal(w.WarhubI18n.text('1 天前'),'1 day ago');
 assert.equal(w.WarhubI18n.text('2 天前'),'2 days ago');
 assert.equal(w.WarhubI18n.text('最新 1 時前'),'Latest: 1 hour ago');
 w.WarhubI18n.select('zh-TW');assert.equal(w.WarhubI18n.text('1 天前'),'1 天前');w.close();
});
