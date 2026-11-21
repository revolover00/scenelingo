import { createHash, timingSafeEqual } from 'node:crypto';
import pg from 'pg';
import { postgresOptions } from './postgres-config.js';

export function authorized(header, expectedHash) {
  if (!/^[a-f0-9]{64}$/.test(expectedHash || '') || !header?.startsWith('Basic ')) return false;
  const credentials = Buffer.from(header.slice(6), 'base64').toString();
  const separator = credentials.indexOf(':');
  if (separator < 0 || credentials.slice(0, separator) !== 'admin') return false;
  const hash = createHash('sha256').update(credentials.slice(separator + 1)).digest();
  return timingSafeEqual(hash, Buffer.from(expectedHash, 'hex'));
}

export async function snapshot({page = 1, search = ''} = {}) {
  page = Number.isSafeInteger(Number(page)) && Number(page)>0 ? Math.min(Number(page),100000) : 1;
  search = typeof search === 'string' ? search.trim().slice(0,100) : '';
  const pageSize = 50;
  const botId = (process.env.BOT_TOKEN || '').split(':')[0];
  if (!/^\d+$/.test(botId)) throw new Error('Missing bot identity');
  const client = new pg.Client(postgresOptions(process.env.DATABASE_URL));
  await client.connect();
  try {
    await client.query('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY');
    await client.query(`SET LOCAL search_path TO "bot_${botId}"`);
    // Counts and distributions use exactly the same eligibility rule as scheduling.
    const result = await client.query(`WITH audience AS (
      SELECT s.is_active, s.level, s.subscribed_at,
        COALESCE(p.learning_language, 'en') AS learning,
        COALESCE(p.explanation_language, 'ar') AS explanation,
        COALESCE(p.interval_minutes, 180) AS minutes,
        LEFT(COALESCE(p.input_state, ''), 6) = 'setup_' AS in_setup,
        COALESCE(p.next_due_at, s.subscribed_at + interval '3 hours') AS due_at
      FROM subscribers s LEFT JOIN subscriber_preferences p USING (chat_id)
    ) SELECT json_build_object(
      'total', count(*),
      'active', count(*) FILTER (WHERE is_active AND NOT in_setup),
      'setup', count(*) FILTER (WHERE is_active AND in_setup),
      'stopped', count(*) FILTER (WHERE NOT is_active),
      'due', count(*) FILTER (WHERE is_active AND NOT in_setup AND due_at <= now()),
      'next_due', min(due_at) FILTER (WHERE is_active AND NOT in_setup),
      'groups', COALESCE((SELECT json_agg(g) FROM (
        SELECT learning, explanation, level, minutes, count(*) AS subscribers,
          count(*) FILTER (WHERE due_at <= now()) AS due
        FROM audience WHERE is_active AND NOT in_setup
        GROUP BY learning, explanation, level, minutes ORDER BY learning, level, minutes
      ) g), '[]'::json)
    ) AS summary FROM audience`);
    const recent = await client.query('SELECT level, learning_language, phrase, video_title, sent_at FROM sent_phrases ORDER BY sent_at DESC LIMIT 20');
    const exists = await client.query("SELECT to_regclass('delivery_runs') AS name");
    const runs = exists.rows[0]?.name ? await client.query('SELECT * FROM delivery_runs ORDER BY id DESC LIMIT 30') : { rows: [] };
    const reliable = await client.query("SELECT to_regclass('delivery_attempts') AS name");
    let delivery = { sent:0, failed:0, uncertain:0, blocked:0, cached:0, saved:0, reports:0, errors:[] };
    let ai = {requests:0,failed:0,prompt_tokens:0,completion_tokens:0,unreported:0};
    if (reliable.rows[0]?.name) {
      const counts = await client.query(`SELECT
        count(*) FILTER(WHERE status='sent')::int AS sent,
        count(*) FILTER(WHERE status='failed')::int AS failed,
        count(*) FILTER(WHERE status IN ('uncertain','sending'))::int AS uncertain,
        count(*) FILTER(WHERE status='blocked')::int AS blocked,
        (SELECT count(*)::int FROM lesson_content WHERE telegram_file_id IS NOT NULL) AS cached,
        (SELECT count(*)::int FROM saved_lessons) AS saved,
        (SELECT count(*)::int FROM lesson_feedback) AS reports FROM delivery_attempts`);
      const errors = await client.query(`SELECT status,error_code,updated_at FROM delivery_attempts
        WHERE error_code IS NOT NULL ORDER BY updated_at DESC LIMIT 20`);
      delivery = {...counts.rows[0],errors:errors.rows};
      const usage = await client.query(`SELECT count(*)::int AS requests,count(*) FILTER(WHERE status='failed')::int AS failed,
        COALESCE(sum(prompt_tokens),0)::float AS prompt_tokens, COALESCE(sum(completion_tokens),0)::float AS completion_tokens,
        count(*) FILTER(WHERE prompt_tokens IS NULL AND completion_tokens IS NULL)::int AS unreported FROM ai_usage`);
      ai = usage.rows[0];
    }
    let preparation = {ready:0,media_bytes:0,media_items:0,runs:[]};
    const prepExists = await client.query("SELECT to_regclass('preparation_runs') AS name");
    if (prepExists.rows[0]?.name) {
      const prep = await client.query(`SELECT
        (SELECT count(*)::int FROM prepared_slots p
          JOIN subscribers s USING(chat_id)
          JOIN subscriber_preferences prefs USING(chat_id)
          JOIN lesson_content c ON c.id=p.content_id
          WHERE s.is_active AND LEFT(COALESCE(prefs.input_state,''),6)<>'setup_'
            AND p.due_at=prefs.next_due_at AND p.settings_updated_at IS NOT DISTINCT FROM prefs.updated_at
            AND EXISTS(SELECT 1 FROM lesson_captions cap WHERE cap.content_id=c.id AND cap.explanation_language=prefs.explanation_language)
            AND (c.telegram_file_id IS NOT NULL OR EXISTS(SELECT 1 FROM prepared_media m WHERE m.content_id=c.id AND m.expires_at>now()))
            AND NOT EXISTS(SELECT 1 FROM delivery_attempts a WHERE a.chat_id=p.chat_id AND a.due_at=p.due_at
              AND a.status IN ('sent','uncertain','blocked','skipped','sending'))) AS ready,
        count(*)::int AS media_items, COALESCE(sum(octet_length(payload)),0)::float AS media_bytes
        FROM prepared_media WHERE expires_at>now()`);
      const prepRuns = await client.query('SELECT prepared_count,failed_count,duration_seconds,finished_at FROM preparation_runs ORDER BY id DESC LIMIT 20');
      preparation = {...prep.rows[0], runs:prepRuns.rows};
    }
    const filter = `($1='' OR strpos(lower(COALESCE(s.username,'')),lower($1))>0
      OR strpos(lower(COALESCE(s.first_name,'')),lower($1))>0 OR strpos(s.chat_id::text,$1)>0)`;
    const userCount = await client.query(`SELECT count(*)::int AS total FROM subscribers s WHERE ${filter}`, [search]);
    const people = await client.query(`SELECT s.chat_id::text AS chat_id,s.username,s.first_name,s.subscribed_at,s.is_active,s.level,
      COALESCE(p.ui_language,'ar') AS ui_language,COALESCE(p.learning_language,'en') AS learning_language,
      COALESCE(p.explanation_language,'ar') AS explanation_language,COALESCE(p.interval_minutes,180) AS interval_minutes,
      COALESCE(p.next_due_at,s.subscribed_at+interval '3 hours') AS next_due_at,p.updated_at,p.input_state
      ${reliable.rows[0]?.name ? ',last.status AS last_status,last.error_code AS last_error,last.updated_at AS last_delivery_at,last.phrase AS last_phrase' : ',NULL AS last_status,NULL AS last_error,NULL AS last_delivery_at,NULL AS last_phrase'}
      FROM subscribers s LEFT JOIN subscriber_preferences p USING(chat_id)
      ${reliable.rows[0]?.name ? `LEFT JOIN LATERAL (SELECT a.status,a.error_code,a.updated_at,c.phrase
        FROM delivery_attempts a LEFT JOIN lesson_content c ON c.id=a.content_id
        WHERE a.chat_id=s.chat_id ORDER BY a.updated_at DESC,a.id DESC LIMIT 1) last ON TRUE` : ''}
      WHERE ${filter} ORDER BY s.subscribed_at DESC,s.chat_id LIMIT $2 OFFSET $3`, [search,pageSize,(page-1)*pageSize]);
    const subscribers = {rows:people.rows,page,page_size:pageSize,total:userCount.rows[0]?.total??0,search};
    await client.query('COMMIT');
    return { ...result.rows[0].summary, recent: recent.rows, runs: runs.rows, delivery, ai, preparation, subscribers, updated_at: new Date().toISOString() };
  } finally { await client.end(); }
}
