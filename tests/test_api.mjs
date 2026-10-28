import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
const source=fs.readFileSync(new URL('../api/data.js',import.meta.url),'utf8');
const {default:handler}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
function response(){return{code:null,headers:{},status(n){this.code=n;return this},setHeader(k,v){this.headers[k]=v},json(x){this.body=x},send(x){this.body=JSON.parse(x)}}}
test('denies files outside allowlist without requesting GitHub',async()=>{global.fetch=()=>{throw Error('should not fetch')};const r=response();await handler({query:{f:'../../.env'}},r);assert.equal(r.code,400)});
test('valid JSON snapshot and explicit CDN source',async()=>{global.fetch=async()=>({ok:true,json:async()=>({updated_at:'2026-09-11T00:00:00Z'})});const r=response();await handler({query:{}},r);assert.equal(r.code,200);assert.equal(r.headers['X-Warhub-Source'],'github')});
test('upstream auth failure is uncacheable',async()=>{global.fetch=async()=>({ok:false,status:404});const r=response();await handler({query:{}},r);assert.equal(r.code,502);assert.equal(r.headers['Cache-Control'],'no-store')});
test('invalid successful response fails closed',async()=>{global.fetch=async()=>({ok:true,json:async()=>({foo:'bar'})});const r=response();await handler({query:{}},r);assert.equal(r.code,502)});

test('preview reads deployment branch while production ignores requested ref',async()=>{
  const env=process.env.VERCEL_ENV, branch=process.env.VERCEL_GIT_COMMIT_REF;
  let url;global.fetch=async(u)=>{url=new URL(u);return{ok:true,json:async()=>({updated_at:'2026-09-11T00:00:00Z'})}};
  try{
    process.env.VERCEL_ENV='preview';process.env.VERCEL_GIT_COMMIT_REF='codex/data-integrity-audit';
    await handler({query:{ref:'main'}},response());assert.equal(url.searchParams.get('ref'),'codex/data-integrity-audit');
    process.env.VERCEL_ENV='production';await handler({query:{ref:'attacker-branch'}},response());assert.equal(url.searchParams.get('ref'),'main');
  }finally{if(env===undefined)delete process.env.VERCEL_ENV;else process.env.VERCEL_ENV=env;if(branch===undefined)delete process.env.VERCEL_GIT_COMMIT_REF;else process.env.VERCEL_GIT_COMMIT_REF=branch;}
});

test('data.json drops server-only bookkeeping but keeps what the page reads',async()=>{
  const snap={updated_at:'2026-09-11T00:00:00Z',translation_cache:{a:'b'},english_translation_cache:{x:'y'},_notify:{bucket:1},trade_api:{},
    notams:{taiwan:{danger:3,observed_at:'t',stale:false,sync_state:{records:{a:1}}},bad:null},
    taiwan_insight:{version:1,timeline:[1],news_observations:[2],market_observations:[3]},regions:[{key:'taiwan'}]};
  const before=JSON.stringify(snap);
  global.fetch=async()=>({ok:true,json:async()=>JSON.parse(before)});
  const r=response();await handler({query:{}},r);
  assert.equal(r.code,200);
  for(const k of ['translation_cache','_notify','trade_api'])assert.ok(!(k in r.body),k);
  assert.deepEqual(r.body.notams.taiwan,{danger:3,observed_at:'t',stale:false});
  assert.equal(r.body.notams.bad,null);
  assert.deepEqual(r.body.taiwan_insight,{version:1,timeline:[1],news_observations:[2]});
  assert.deepEqual(r.body.english_translation_cache,{x:'y'});
  assert.deepEqual(r.body.regions,[{key:'taiwan'}]);
  // Other allowlisted files pass through untouched.
  global.fetch=async()=>({ok:true,json:async()=>({translation_cache:1,_notify:2})});
  const h=response();await handler({query:{f:'history.json'}},h);assert.deepEqual(h.body,{translation_cache:1,_notify:2});
});
