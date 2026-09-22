const {JSDOM}=require('jsdom'),fs=require('fs'),assert=require('assert');
(async()=>{
 const report=JSON.parse(fs.readFileSync('research/pizza-backtest.json'));
 const dom=new JSDOM('<section id="pizza-backtest"></section>',{runScripts:'outside-only',url:'https://warhub.test/'});
 const w=dom.window;w.fetch=async url=>({ok:true,json:async()=>url.includes('pizza-reviews')?JSON.parse(fs.readFileSync('research/pizza-reviews.json')):report});w.WarhubI18n={language:'zh-TW'};
 w.eval(fs.readFileSync('pizza-backtest.js','utf8'));w.document.dispatchEvent(new w.Event('DOMContentLoaded'));await new Promise(r=>setTimeout(r,10));
 const host=w.document.querySelector('#pizza-backtest');assert.ok(host.textContent.includes('觀測到跨越門檻'));assert.ok(!host.textContent.includes('NaN'));
 assert.equal(host.querySelectorAll('.pizza-study-stats strong')[0].textContent,'0');
 assert.ok(host.querySelector('.pizza-study-evidence'));
 assert.ok(host.querySelector('.pizza-study-evidence').textContent.includes('查到'));
 assert.ok(host.querySelector('.pizza-study-evidence a[href*="stripes.com"]'));
 assert.ok(host.querySelector('.pizza-study-evidence').textContent.includes('2026-09'));
 host.querySelector('[data-pizza-threshold="2"]').click();assert.equal(host.querySelectorAll('.pizza-study-stats strong')[0].textContent,'0');
 assert.equal(host.querySelector('.pizza-study-rate strong').textContent,'尚不能估計');
 w.WarhubI18n.language='en';w.document.dispatchEvent(new w.Event('warhub-language-change'));assert.ok(!/[\u3400-\u9fff]/.test(host.textContent));
 const old=JSON.parse(JSON.stringify(report));old.as_of='2020-01-01T00:00:00Z';old.groups['2'].detected_crossings=999;w.renderPizzaBacktest(old);assert.ok(!host.textContent.includes('999'));
 w.WarhubI18n.language='zh-TW';w.document.dispatchEvent(new w.Event('warhub-language-change'));assert.ok(host.textContent.includes('仍不確定'));
 dom.window.close();console.log('Pizza study DOM: tabs, language, unknown rates and stale response passed');
})();
