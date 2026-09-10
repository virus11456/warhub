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
