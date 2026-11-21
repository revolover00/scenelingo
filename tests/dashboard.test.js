import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { authorized } from '../lib/dashboard.js';
import handler from '../api/dashboard.js';
import pg from 'pg';
process.env.BOT_TOKEN = '123:test';
pg.Client.prototype.connect = async () => {};
pg.Client.prototype.end = async () => {};
pg.Client.prototype.query = async () => ({rows:[{allowed:true}]});
const hash = createHash('sha256').update('test-password').digest('hex');
const auth = 'Basic '+Buffer.from('admin:test-password').toString('base64');
const oldHash = process.env.DASHBOARD_PASSWORD_HASH;
after(()=>{if(oldHash===undefined) delete process.env.DASHBOARD_PASSWORD_HASH; else process.env.DASHBOARD_PASSWORD_HASH=oldHash;});
function response(){return {headers:{},setHeader(k,v){this.headers[k]=v;},status(n){this.code=n;return this;},send(body){this.body=body;return this;},json(body){this.body=body;return this;}};}
test('dashboard fails closed for missing or incorrect credentials',async()=>{
 assert.equal(authorized(auth,hash),true);
 for(const bad of [undefined,'Basic !!!','Bearer test','Basic '+Buffer.from('other:test-password').toString('base64')]) assert.equal(authorized(bad,hash),false);
 assert.equal(authorized(auth,undefined),false);
 delete process.env.DASHBOARD_PASSWORD_HASH;
 let res=response();await handler({method:'GET',headers:{}},res);assert.equal(res.code,503);
 process.env.DASHBOARD_PASSWORD_HASH=hash;
 res=response();await handler({method:'GET',headers:{},query:{data:'1'}},res);assert.equal(res.code,401);assert.ok(res.headers['WWW-Authenticate']);
});
test('private dashboard serves HTML with no-store and restrictive CSP',async()=>{
 process.env.DASHBOARD_PASSWORD_HASH=hash;
 const res=response();await handler({method:'GET',headers:{authorization:auth}},res);
 assert.equal(res.code,200);assert.ok(res.body.includes('SceneLingo'));assert.equal(res.headers['Cache-Control'],'private, no-store');assert.ok(res.headers['Content-Security-Policy'].includes("script-src 'sha256-"));assert.ok(!res.body.includes('test-password'));
});
test('dashboard rejects write methods',async()=>{
 const res=response();await handler({method:'POST',headers:{authorization:auth}},res);assert.equal(res.code,405);
});

test('locked login cannot bypass throttling with a correct password',async()=>{
 process.env.DASHBOARD_PASSWORD_HASH=hash;
 const original=pg.Client.prototype.query;
 try {
  pg.Client.prototype.query=async()=>({rows:[{allowed:false}]});
  const res=response();await handler({method:'GET',headers:{authorization:auth}},res);
  assert.equal(res.code,429);assert.equal(res.headers['Retry-After'],'900');
 } finally {pg.Client.prototype.query=original;}
});

test('login limiter database outage fails closed instead of skipping protection',async()=>{
 process.env.DASHBOARD_PASSWORD_HASH=hash;
 const original=pg.Client.prototype.query;
 try {
  pg.Client.prototype.query=async()=>{throw new Error('offline');};
  const res=response();await handler({method:'GET',headers:{authorization:auth}},res);
  assert.equal(res.code,503);
 } finally {pg.Client.prototype.query=original;}
});
