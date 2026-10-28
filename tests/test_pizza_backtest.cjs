const {JSDOM}=require('jsdom'),fs=require('fs'),assert=require('assert');
(async()=>{
 const report=JSON.parse(fs.readFileSync('research/pizza-backtest.json'));
 const dom=new JSDOM('<section id="pizza-backtest"></section>',{runScripts:'outside-only',url:'https://warhub.test/'});
 const w=dom.window;const fetched=[];w.fetch=async url=>{fetched.push(url);return{ok:true,json:async()=>report}};w.WarhubI18n={language:'zh-TW'};
 w.eval(fs.readFileSync('pizza-backtest.js','utf8'));w.document.dispatchEvent(new w.Event('DOMContentLoaded'));await new Promise(r=>setTimeout(r,10));
 const host=w.document.querySelector('#pizza-backtest');assert.ok(!host.textContent.includes('NaN'));
 assert.deepEqual(fetched,['/research/pizza-backtest.json']);
 // The folds are gone; every count lives in one sentence.
 assert.equal(host.querySelector('details'),null);
 const c=report.groups['3'].counts;
 const line=host.querySelector('.pizza-study-summary').textContent;
 assert.ok(line.includes(`共 ${report.groups['3'].detected_crossings} 次`),line);
 assert.ok(line.includes(`仍不確定 ${c.unreviewed} 次`)&&line.includes(`確認有行動 ${c.reviewed_yes} 次`),line);
 assert.equal(host.querySelector('.pizza-study-rate strong').textContent,'準確率尚不能估計');
 assert.equal(host.querySelectorAll('a').length,0);
 host.querySelector('[data-pizza-threshold="2"]').click();
 assert.ok(host.querySelector('.pizza-study-summary').textContent.startsWith('升到 DEFCON 2'));
 w.WarhubI18n.language='en';w.document.dispatchEvent(new w.Event('warhub-language-change'));assert.ok(!/[㐀-鿿]/.test(host.textContent));
 const old=JSON.parse(JSON.stringify(report));old.as_of='2020-01-01T00:00:00Z';old.groups['2'].detected_crossings=999;w.renderPizzaBacktest(old);assert.ok(!host.textContent.includes('999'));
 const odd=JSON.parse(JSON.stringify(report));odd.as_of='2099-01-01T00:00:00Z';odd.groups['2'].counts.uncertain_start=2;w.renderPizzaBacktest(odd);assert.ok(host.textContent.includes('2 with unknown start excluded'));
 w.WarhubI18n.language='zh-TW';w.document.dispatchEvent(new w.Event('warhub-language-change'));assert.ok(host.textContent.includes('另有 2 次起點不明'));
 dom.window.close();console.log('Pizza study DOM: one-line summary, tabs, language and stale response passed');
})();
