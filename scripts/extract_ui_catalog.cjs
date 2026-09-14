// Offline only. Parse source rather than executing collectors or webpage code.
const fs=require('node:fs');
const {JSDOM}=require('jsdom');
const acorn=require('acorn');
const hasZh=s=>/[\u3400-\u9fff]/u.test(s);
const units=new Set();
function add(s){s=s.replace(/\s+/g,' ').trim();if(hasZh(s)&&s.length<=4000)units.add(s);}
function markup(s){
 const doc=new JSDOM(s).window.document;
 const walker=doc.createTreeWalker(doc,4);let n;
 while(n=walker.nextNode())if(!n.parentElement?.closest('script,style'))add(n.nodeValue);
 for(const el of doc.querySelectorAll('[title],[aria-label],[alt],[placeholder]'))
  for(const a of ['title','aria-label','alt','placeholder'])if(el.hasAttribute(a))add(el.getAttribute(a));
}
function literal(s){
 if(!hasZh(s))return;
 // Quasis provide fallback fragments; exact full messages take precedence.
 markup(s);
 for(const p of s.match(/[\u3400-\u9fff][\u3400-\u9fff\u3000-\u303f\uff00-\uffef、；：！？（）「」『』—–／·％℃ ]*/gu)||[])add(p);
}
function visit(n){
 if(!n||typeof n!=='object')return;
 if(n.type==='Literal'&&typeof n.value==='string')literal(n.value);
 if(n.type==='TemplateElement')literal(n.value.cooked||n.value.raw);
 for(const [k,v] of Object.entries(n))if(k!=='value'){
  if(Array.isArray(v))v.forEach(visit);else if(v&&typeof v==='object')visit(v);
 }
}
const files=['index.html',...fs.readdirSync('guides').filter(f=>f.endsWith('.html')).map(f=>'guides/'+f)];
for(const file of files){
 const html=fs.readFileSync(file,'utf8');markup(html);
 if(file==='index.html')for(const m of html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g))
  visit(acorn.parse(m[1],{ecmaVersion:'latest'}));
}
fs.mkdirSync('locales',{recursive:true});
fs.writeFileSync('locales/source.json',JSON.stringify([...units].sort(),null,2)+'\n');
console.log(`${units.size} distinct UI/guide translation units (offline)`);
