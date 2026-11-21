import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import pg from 'pg';
import rawHandler from '../api/telegram.js';
import { webhookSecret } from '../lib/webhook-auth.js';
const handler = (req, res) => rawHandler({...req, headers: {'x-telegram-bot-api-secret-token': webhookSecret(process.env.BOT_TOKEN)}}, res);

process.env.BOT_TOKEN = '123456:test-token';
const queries = [];
const calls = [];
let inputState = null;
let setupSettings = null;
let uiLanguage = null;
pg.Client.prototype.connect = async () => {};
pg.Client.prototype.end = async () => {};
pg.Client.prototype.query = async (sql, values) => {
  queries.push({ sql, values });
  if (sql.startsWith('SELECT ui_language')) return { rows: uiLanguage ? [{ ui_language: uiLanguage }] : [] };
  if (sql.startsWith('SELECT p.*, s.level')) return { rowCount: setupSettings ? 1 : 0, rows: setupSettings ? [{ ...setupSettings }] : [] };
  if (sql.startsWith('SELECT input_state')) return { rowCount: 1, rows: [{ input_state: inputState }] };
  if (sql.startsWith('UPDATE subscribers SET level')) return { rowCount: 1, rows: [{ level: values[0] }] };
  if (sql.startsWith('SELECT level FROM')) return { rowCount: 1, rows: [{ level: 'A2' }] };
  return { rowCount: 1, rows: [] };
};
const oldFetch = globalThis.fetch;
globalThis.fetch = async (url, options) => {
  calls.push({ url, body: JSON.parse(options.body) });
  return { ok: true, json: async () => ({ ok: true }) };
};
after(() => { globalThis.fetch = oldFetch; });
function res() { return { status(code) { assert.equal(code, 200); return this; }, send() {} }; }

test('start shows first guided language step and keeps existing level on conflict', async () => {
  queries.length = 0; calls.length = 0;
  await handler({ method: 'POST', body: { message: { chat: { id: 1, type: 'private' }, from: { id: 1 }, text: '/start' } } }, res());
  const insert = queries.find(q => q.sql.includes('INSERT INTO subscribers'));
  assert.ok(insert);
  assert.ok(!insert.sql.includes('level = EXCLUDED'));
  assert.equal(calls.at(-1).body.reply_markup.inline_keyboard[0].length, 2);
});

test('user can change level from a private callback', async () => {
  queries.length = 0; calls.length = 0;
  await handler({ method: 'POST', body: { callback_query: { id: 'cb', from: { id: 1 }, message: { message_id: 42, chat: { id: 1, type: 'private' } }, data: 'level:C1' } } }, res());
  assert.deepEqual(queries.find(q => q.sql.startsWith('UPDATE subscribers SET level')).values, ['C1', 1]);
  assert.match(calls.at(-1).body.text, /C1/);
});

test('invalid callback is rejected without database update', async () => {
  queries.length = 0; calls.length = 0;
  await handler({ method: 'POST', body: { callback_query: { id: 'cb', from: { id: 1 }, message: { message_id: 42, chat: { id: 1, type: 'private' } }, data: 'level:ZZ' } } }, res());
  assert.equal(queries.length, 0);
  assert.ok(calls.at(-1).url.endsWith('/answerCallbackQuery'));
});

test('language selection records the requested language', async () => {
  queries.length = 0; calls.length = 0;
  await handler({ method: 'POST', body: { callback_query: { id: 'cb', from: { id: 1 }, message: { message_id: 42, chat: { id: 1, type: 'private' } }, data: 'learn:es' } } }, res());
  const query = queries.find(q => q.sql.includes('INSERT INTO subscriber_preferences') && q.sql.includes('learning_language'));
  assert.deepEqual(query.values, ['es', 1]);
  assert.match(query.sql, /subscribed_at \+ interval '3 hours'/);
  assert.match(calls.at(-1).body.text, /Español/);
});

test('typed intervals never save settings and show preset buttons', async () => {
  setupSettings = { input_state: 'interval' };
  for (const typed of ['٣٠', '1440', '45', 'نص ساعة']) {
    queries.length = 0; calls.length = 0;
    await handler({ method: 'POST', body: { message: { chat: { id: 1, type: 'private' }, text: typed } } }, res());
    assert.match(calls.at(-1).body.text, /الأزرار/);
    assert.equal(calls.at(-1).body.reply_markup.inline_keyboard.length, 7);
    assert.ok(!queries.some(q => q.sql.includes('SET interval_minutes = $1')));
  }
  setupSettings = null;
});

test('start explains ordered setup instead of a command dump', async () => {
  calls.length = 0;
  await handler({ method: 'POST', body: { message: { chat: { id: 1, type: 'private' }, from: { id: 1 }, text: '/start' } } }, res());
  assert.match(calls.at(-1).body.text, /لغة البوت/);
  assert.equal(calls.at(-1).body.reply_markup.inline_keyboard[0][0].callback_data, 'setup_ui:ar');
});


test('opening interval input preserves a new preferences row due time', async () => {
  queries.length = 0; calls.length = 0;
  await handler({ method: 'POST', body: { message: { chat: { id: 1, type: 'private' }, from: { id: 1 }, text: '/interval' } } }, res());
  const query = queries.find(q => q.sql.includes("'interval'") && q.sql.includes('INSERT INTO subscriber_preferences'));
  assert.match(query.sql, /subscribed_at \+ interval '3 hours'/);
});

test('webhook returns failure for Telegram errors so updates can retry', async () => {
  const previous = globalThis.fetch;
  const previousError = console.error;
  let status;
  globalThis.fetch = async () => { throw new Error('temporary'); };
  console.error = () => {};
  try {
    await handler({ method: 'POST', body: { message: { chat: { id: 1, type: 'private' }, from: { id: 1 }, text: '/help' } } },
      { status(code) { status = code; return this; }, send() {} });
    assert.equal(status, 500);
  } finally {
    console.error = previousError;
    globalThis.fetch = previous;
  }
});

const callbackUpdate = data => ({ method: 'POST', body: { callback_query: { id: 'cb', from: { id: 1 }, message: { message_id: 42, chat: { id: 1, type: 'private' } }, data } } });

test('guided choices advance through all steps and schedule only on confirmation', async () => {
  setupSettings = { input_state: 'setup_ui', learning_language: 'en', explanation_language: 'ar', level: 'A2', interval_minutes: 180 };
  for (const [kind, value, next, pattern] of [
    ['ui', 'ar', 'learn', /١ من ٤/],
    ['learn', 'es', 'level', /٢ من ٤/],
    ['level', 'B2', 'explain', /٣ من ٤/],
    ['explain', 'ar', 'interval', /٤ من ٤/],
    ['interval', '30', 'confirm', /كل حاجة جاهزة/],
    ['confirm', 'yes', null, /اشتراكك جاهز/],
  ]) {
    queries.length = 0; calls.length = 0;
    await handler(callbackUpdate(`setup_${kind}:${value}`), res());
    assert.match(calls.at(-1).body.text, pattern);
    assert.ok(calls.at(-1).url.endsWith('/editMessageText'));
    assert.equal(calls.at(-1).body.message_id, 42);
    assert.ok(!calls.some(call => call.url.endsWith('/sendMessage')));
    if (!next) assert.deepEqual(calls.at(-1).body.reply_markup.inline_keyboard, []);
    const saved = queries.find(q => q.sql.includes('SET input_state = $1'));
    assert.equal(saved.values[0], next ? `setup_${next}` : null);
    setupSettings.input_state = next ? `setup_${next}` : null;
  }
  setupSettings = null;
});

test('stale setup buttons redisplay current step without saving', async () => {
  setupSettings = { input_state: 'setup_level' };
  queries.length = 0; calls.length = 0;
  await handler(callbackUpdate('setup_confirm:yes'), res());
  assert.match(calls.at(-1).body.text, /٢ من ٤/);
  assert.ok(!queries.some(q => q.sql.includes('SET input_state = $1')));
  setupSettings = null;
});

test('interval callback validates minimum and maximum', async () => {
  for (const value of ['29', '1441', '-1', '30.5', '45', '90', '030']) {
    queries.length = 0;
    await handler(callbackUpdate(`interval:${value}`), res());
    assert.equal(queries.length, 0);
  }
  for (const value of ['30', '1440']) {
    queries.length = 0;
    await handler(callbackUpdate(`interval:${value}`), res());
    assert.ok(queries.some(q => q.sql.includes('SET interval_minutes = $1')));
  }
});

test('typing minutes during setup does not advance to confirmation', async () => {
  setupSettings = { input_state: 'setup_interval', level: 'B1', learning_language: 'en', explanation_language: 'ar' };
  queries.length = 0; calls.length = 0;
  await handler({ method: 'POST', body: { message: { chat: { id: 1, type: 'private' }, text: '١٤٤٠' } } }, res());
  assert.match(calls.at(-1).body.text, /٤ من ٤/);
  assert.equal(calls.at(-1).body.reply_markup.inline_keyboard[0][0].callback_data, 'setup_interval:30');
  assert.ok(!queries.some(q => q.sql.includes('SET input_state = $1')));
  setupSettings = null;
});

test('English interface choice localizes the very next step', async () => {
  setupSettings = { input_state: 'setup_ui', ui_language: 'ar' };
  calls.length = 0;
  await handler(callbackUpdate('setup_ui:en'), res());
  assert.match(calls.at(-1).body.text, /1 of 4/);
  const saved = queries.findLast(q => q.sql.includes('SET ui_language = $1'));
  assert.deepEqual(saved.values, ['en', 1]);
  setupSettings = null;
});

test('saved interface language takes precedence over Telegram language', async () => {
  uiLanguage = 'en'; calls.length = 0;
  await handler({ method: 'POST', body: { message: { chat: { id: 1, type: 'private' }, from: { language_code: 'ar' }, text: '/help' } } }, res());
  assert.match(calls.at(-1).body.text, /Message frequency/);
  uiLanguage = null;
});

test('bot language changes do not overwrite learning or explanation preferences', async () => {
  queries.length = 0; calls.length = 0;
  await handler(callbackUpdate('ui:en'), res());
  const query = queries.find(q => q.sql.includes('INSERT INTO subscriber_preferences'));
  assert.deepEqual(query.values, ['en', 1]);
  assert.ok(!query.sql.includes('learning_language'));
  assert.ok(!query.sql.includes('explanation_language'));
  assert.match(calls.at(-1).body.text, /Bot language changed to English/);
});

test('back button returns to previous step without overwriting choices', async () => {
  setupSettings = { input_state: 'setup_interval', ui_language: 'en' };
  queries.length = 0; calls.length = 0;
  await handler(callbackUpdate('setup_back:yes'), res());
  assert.match(calls.at(-1).body.text, /3 of 4/);
  assert.equal(queries.find(q => q.sql.includes('SET input_state = $1')).values[0], 'setup_explain');
  assert.ok(!queries.some(q => q.sql.includes('SET interval_minutes = $1')));
  setupSettings = null;
});


test('webhook isolates tables by the current bot identity', async () => {
  queries.length = 0;
  await handler({ method: 'POST', body: { message: { chat: { id: 1, type: 'private' }, text: '/help' } } }, res());
  assert.ok(!queries.some(q => q.sql.includes('CREATE SCHEMA')));
  assert.ok(queries.some(q => q.sql === 'SET search_path TO "bot_123456"'));
});


test('restart and back edit the original setup message', async () => {
  for (const action of ['setup_back:yes', 'setup_restart:yes']) {
    setupSettings = { input_state: 'setup_interval', ui_language: 'en' };
    calls.length = 0;
    await handler(callbackUpdate(action), res());
    assert.ok(calls.at(-1).url.endsWith('/editMessageText'));
    assert.equal(calls.at(-1).body.message_id, 42);
    assert.ok(!calls.some(call => call.url.endsWith('/sendMessage')));
  }
  setupSettings = null;
});

test('an unchanged screen is a successful no-op, not a retry or new message', async () => {
  const previous = globalThis.fetch;
  setupSettings = { input_state: 'setup_level' };
  const methods = [];
  globalThis.fetch = async (url) => {
    methods.push(url.split('/').at(-1));
    return url.endsWith('/editMessageText')
      ? { ok: false, json: async () => ({ ok: false, error_code: 400, description: 'Bad Request: message is not modified' }) }
      : { ok: true, json: async () => ({ ok: true }) };
  };
  try {
    await handler(callbackUpdate('setup_confirm:yes'), res());
    assert.deepEqual(methods, ['answerCallbackQuery', 'editMessageText']);
  } finally { globalThis.fetch = previous; setupSettings = null; }
});

test('other edit errors remain failures without sending duplicate messages', async () => {
  const previous = globalThis.fetch;
  const previousError = console.error;
  setupSettings = { input_state: 'setup_level' };
  const methods = [];
  let status;
  globalThis.fetch = async (url) => {
    methods.push(url.split('/').at(-1));
    return url.endsWith('/editMessageText')
      ? { ok: false, json: async () => ({ ok: false, error_code: 400, description: 'Bad Request: message to edit not found' }) }
      : { ok: true, json: async () => ({ ok: true }) };
  };
  console.error = () => {};
  try {
    await handler(callbackUpdate('setup_confirm:yes'), { status(code) { status = code; return this; }, send() {} });
    assert.equal(status, 500);
    assert.ok(!methods.includes('sendMessage'));
  } finally { globalThis.fetch = previous; console.error = previousError; setupSettings = null; }
});


test('unauthenticated updates are rejected before database or Bot API access', async () => {
  queries.length = 0; calls.length = 0;
  const response = {status(code){assert.equal(code,403);return this;},send(){}};
  await rawHandler({method:'POST',body:{message:{text:'/start',chat:{id:1,type:'private'}}}}, response);
  assert.equal(queries.length,0); assert.equal(calls.length,0);
});

test('webhook requests never run database migrations', async () => {
  queries.length = 0; calls.length = 0;
  await handler({ method: 'POST', body: { message: { chat: { id: 1, type: 'private' }, from: { id: 1 }, text: '/level' } } }, res());
  assert.ok(queries.some(q => q.sql.includes('SET search_path')));
  assert.ok(!queries.some(q => /CREATE|ALTER TABLE|DROP CONSTRAINT/.test(q.sql)));
});
