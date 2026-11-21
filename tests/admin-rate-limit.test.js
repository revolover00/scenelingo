import {test} from 'node:test';
import assert from 'node:assert/strict';
import pg from 'pg';
import {loginAttempt, loginKey} from '../lib/admin-rate-limit.js';
process.env.DASHBOARD_PASSWORD_HASH = 'a'.repeat(64);
process.env.BOT_TOKEN = '123:test';

test('login keys are salted hashes and ignore spoofable forwarding headers',()=>{
  process.env.VERCEL='1';
  const req={headers:{'x-vercel-forwarded-for':'192.0.2.1','x-forwarded-for':'spoof'}};
  const key=loginKey(req);
  assert.match(key,/^[a-f0-9]{64}$/);
  req.headers['x-forwarded-for']='different';assert.equal(loginKey(req),key);
  req.headers['x-vercel-forwarded-for']='192.0.2.2';assert.notEqual(loginKey(req),key);
  delete process.env.VERCEL;
});

test('distributed login limit uses atomic bound SQL and closes on failure',async()=>{
  let ended=0; const queries=[];
  pg.Client.prototype.connect=async()=>{};
  pg.Client.prototype.end=async()=>{ended++;};
  pg.Client.prototype.query=async(sql,params)=>{queries.push({sql,params});return {rows:[{allowed:false}]};};
  const req={headers:{},socket:{remoteAddress:'127.0.0.1'}};
  assert.equal(await loginAttempt(req),false);
  const insert=queries.find(q=>q.sql.startsWith('INSERT'));
  assert.ok(insert.sql.includes('ON CONFLICT') && insert.sql.includes('attempts<=20'));
  assert.equal(insert.params[0],loginKey(req));assert.equal(ended,1);
  assert.equal(await loginAttempt(req,true),true);
  assert.ok(queries.at(-1).sql.startsWith('DELETE'));
  pg.Client.prototype.query=async()=>{throw new Error('offline');};
  await assert.rejects(loginAttempt(req)); assert.equal(ended,3);
});
