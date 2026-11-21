import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { PGlite } from '@electric-sql/pglite';
import { applyLessonAction } from '../lib/lesson-actions.js';
const read=file=>readFileSync(new URL('../'+file,import.meta.url),'utf8');
test('durable slot claims, feedback ownership and spaced self-review execute in Postgres',async()=>{
 const db=new PGlite();
 try{
  for(const file of ['schema.sql','scheduling.sql','reliability.sql'])await db.exec(read(file));
  await db.exec("INSERT INTO subscribers(chat_id) VALUES(1),(2); INSERT INTO lesson_content(content_key,phrase,topic,level,learning_language,clip_id,video_title,source_url,telegram_file_id) VALUES('key','Good for you','social','B1','en','clip','Movie','https://example.com','file'); INSERT INTO lesson_captions VALUES(1,'ar','شرح محفوظ');");
  // Execute the Python worker's exact production claim statement in Postgres.
  let query=read('delivery_store.py').match(/cur.execute\("""(INSERT INTO delivery_attempts[\s\S]*?)"""/)[1];let i=0;query=query.replace(/%s/g,()=>'$'+(++i));
  const args=[1,'2026-11-19T10:00:00Z',1,'ar'];
  assert.equal((await db.query(query,args)).rows.length,1);
  assert.equal((await db.query(query,args)).rows.length,0);
  const client={query:async(q,p)=>{const result=await db.query(q,p);return {...result,rowCount:result.affectedRows??result.rows.length};}};
  assert.equal((await applyLessonAction(client,2,'lesson_save','1')).kind,'missing');
  await db.exec("UPDATE delivery_attempts SET status='failed', retry_at=now()-interval '1 minute';");
  assert.equal((await db.query(query,args)).rows.length,1);
  assert.equal((await db.query('SELECT attempts FROM delivery_attempts')).rows[0].attempts,2);
  await db.exec("UPDATE delivery_attempts SET status='sent';");
  assert.equal((await db.query(query,args)).rows.length,0);
  assert.equal((await applyLessonAction(client,1,'lesson_save','1')).kind,'saved');
  assert.equal((await applyLessonAction(client,1,'lesson_save','1')).kind,'saved');
  assert.equal((await db.query('SELECT count(*)::int AS n FROM saved_lessons')).rows[0].n,1);
  assert.equal((await applyLessonAction(client,1,'lesson_show','1')).caption,'شرح محفوظ');
  assert.equal((await applyLessonAction(client,1,'lesson_clip','1')).kind,'reported');
  await applyLessonAction(client,1,'lesson_clip','1');
  assert.equal((await db.query('SELECT count(*)::int AS n FROM lesson_feedback')).rows[0].n,1);
  assert.equal((await applyLessonAction(client,1,'lesson_known','1')).kind,'reviewed');
  assert.equal((await applyLessonAction(client,1,'lesson_known','1')).kind,'missing');
  assert.equal((await db.query('SELECT review_days FROM saved_lessons')).rows[0].review_days,2);
 }finally{await db.close();}
});

test('prepared slots persist media and require matching settings, caption and unexpired media',async()=>{
 const db=new PGlite();
 try {
  for(const file of ['schema.sql','scheduling.sql','reliability.sql'])await db.exec(read(file));
  // Migration is repeatable by webhook and worker initialization.
  await db.exec(read('reliability.sql'));
  await db.exec("INSERT INTO subscribers(chat_id) VALUES(1); INSERT INTO lesson_content(content_key,phrase,topic,level,learning_language,clip_id,video_title,source_url) VALUES('k','hello','greeting','B1','en','clip','Film','https://example.com');");
  const source=read('preparation.py');
  const extract=prefix=>{let i=0;return source.match(new RegExp("cur.execute\\('''("+prefix+"[\\s\\S]*?)'''"))[1].replace(/%s/g,()=>'$'+(++i));};
  const reserve=extract('INSERT INTO prepared_slots');
  const ready=extract('SELECT p.content_id');
  const due='2026-11-19T10:30:00Z',version='2026-11-19T10:00:00Z';
  await db.query(reserve,[1,due,version,1]);
  const args=[1,due,version,true,'ar'];
  assert.equal((await db.query(ready,args)).rows.length,0);
  await db.query('INSERT INTO prepared_media(content_id,payload) VALUES(1,$1)',[new Uint8Array([1,2,3])]);
  assert.equal((await db.query(ready,args)).rows.length,0);
  assert.equal((await db.query(ready,[1,due,version,false,'ar'])).rows.length,1);
  await db.exec("INSERT INTO lesson_captions VALUES(1,'ar','شرح');");
  assert.equal((await db.query(ready,args)).rows[0].content_id,1);
  assert.equal((await db.query(ready,[1,due,null,true,'ar'])).rows.length,0);
  assert.equal((await db.query(ready,[1,'2026-11-19T11:00:00Z',version,true,'ar'])).rows.length,0);
  await db.exec("UPDATE prepared_media SET expires_at=now()-interval '1 minute';");
  assert.equal((await db.query(ready,args)).rows.length,0);
  await db.exec("UPDATE lesson_content SET telegram_file_id='reusable';");
  assert.equal((await db.query(ready,args)).rows.length,1);
 } finally {await db.close();}
});

test('dashboard preparation aggregates execute in PostgreSQL', async()=>{
 const db=new PGlite();
 try {
  for(const file of ['schema.sql','scheduling.sql','reliability.sql'])await db.exec(read(file));
  const query=read('lib/dashboard.js').match(/const prep = await client.query\(`([\s\S]*?)`\)/)[1];
  const result=await db.query(query);
  assert.equal(result.rows[0].ready,0);
  assert.equal(result.rows[0].media_items,0);
  assert.equal(result.rows[0].media_bytes,0);
 } finally {await db.close();}
});

test('shared library assigns oldest unseen lesson per person, not per interval cohort',async()=>{
 const db=new PGlite();
 try {
  for(const file of ['schema.sql','scheduling.sql','reliability.sql'])await db.exec(read(file));
  await db.exec("INSERT INTO subscribers(chat_id) VALUES(1),(2); INSERT INTO lesson_content(content_key,phrase,topic,level,learning_language,clip_id,video_title,source_url,telegram_file_id) VALUES('one','one','t','B1','en','1','Film','https://example.com','file1'),('two','two','t','B1','en','2','Film','https://example.com','file2'),('foreign','foreign','t','B1','fr','3','Film','https://example.com','file3'); INSERT INTO delivery_attempts(chat_id,due_at,content_id,status) VALUES(1,now(),1,'sent');");
  let i=0;
  const query=read('delivery_store.py').match(/cur.execute\("""(SELECT recipient.chat_id[\s\S]*?)"""/)[1].replace(/%s/g,()=>'$'+(++i));
  let result=await db.query(query,[[1,2],'B1','en']);
  const map=Object.fromEntries(result.rows.map(r=>[r.chat_id,r.id]));
  assert.equal(map[1],2); // fast subscriber already saw lesson 1
  assert.equal(map[2],1); // slower subscriber gets lesson 1, not a fresh generation
  await db.exec("INSERT INTO delivery_attempts(chat_id,due_at,content_id,status) VALUES(2,now()+interval '1 minute',1,'uncertain');");
  result=await db.query(query,[[2],'B1','en']);assert.equal(result.rows[0].id,2);
  result=await db.query(query,[[2],'C2','en']);assert.equal(result.rows[0].id,null);
  await db.exec("UPDATE lesson_content SET telegram_file_id=NULL WHERE id=2; INSERT INTO prepared_media(content_id,payload) VALUES(2,'\\x01');");
  result=await db.query(query,[[2],'B1','en']);assert.equal(result.rows[0].id,2);
  await db.exec("UPDATE prepared_media SET expires_at=now()-interval '1 minute';");
  result=await db.query(query,[[2],'B1','en']);assert.equal(result.rows[0].id,null);
 }finally{await db.close();}
});

test('admin throttling SQL locks after twenty guesses and expires safely',async()=>{
 const db=new PGlite();
 try{
  await db.exec(read('schema.sql'));
  const query=read('lib/admin-rate-limit.js').match(/client.query\(`(INSERT INTO admin_login_limits[\s\S]*?)`, \[key\]\)/)[1];
  for(let n=1;n<=21;n++) assert.equal((await db.query(query,['salted-test-key'])).rows[0].allowed,n<=20);
  await db.exec("UPDATE admin_login_limits SET expires_at=now()-interval '1 second'");
  assert.equal((await db.query(query,['salted-test-key'])).rows[0].allowed,true);
  assert.equal((await db.query('SELECT attempts FROM admin_login_limits')).rows[0].attempts,1);
  assert.equal((await db.query(query,['different-key'])).rows[0].allowed,true);
 }finally{await db.close();}
});
