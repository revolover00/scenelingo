// Telegram webhook: subscribe, change CEFR level, and see the latest expression.
import pg from 'pg';
import { postgresOptions } from '../lib/postgres-config.js';
import { authorizedWebhook } from '../lib/webhook-auth.js';
import { applyLessonAction, lessonAction } from '../lib/lesson-actions.js';
import { text, intervalLabel, validInterval, intervalKeyboard, levelKeyboard, uiKeyboard, UI_LANGUAGES } from '../bot_ui.js';

const { Client } = pg;
const LEVELS = ['A2', 'B1', 'B2', 'C1', 'C2'];
const LANGUAGES = [
  ['en', 'English'], ['zh', '中文'], ['hi', 'हिन्दी'], ['es', 'Español'],
  ['fr', 'Français'], ['ar', 'العربية'], ['pt', 'Português'], ['ru', 'Русский'],
  ['de', 'Deutsch'], ['ja', '日本語'],
];
const CODES = new Set(LANGUAGES.map(([code]) => code));
const languageKeyboard = (kind) => ({ inline_keyboard: Array.from({ length: 5 }, (_, row) =>
  LANGUAGES.slice(row * 2, row * 2 + 2).map(([code, label]) => ({ text: label, callback_data: `${kind}:${code}` }))) });
const label = code => LANGUAGES.find(([key]) => key === code)?.[1] || code;
const fallbackLanguage = user => user?.language_code?.toLowerCase().startsWith('en') ? 'en' : 'ar';
async function interfaceLanguage(chatId, fallback) {
  return withDb(async client => {
    const result = await client.query('SELECT ui_language FROM subscriber_preferences WHERE chat_id = $1', [chatId]);
    return result.rows[0]?.ui_language || fallback;
  });
}

async function setupPrompt(chatId, state, settings = {}, fallback = 'ar', messageId) {
  const lang = settings.ui_language || fallback;
  const keyboards = {
    setup_ui: () => uiKeyboard('setup_ui'),
    setup_learn: () => languageKeyboard('setup_learn'),
    setup_level: () => levelKeyboard('setup_level', lang),
    setup_explain: () => languageKeyboard('setup_explain'),
    setup_interval: () => intervalKeyboard('setup_interval', lang),
  };
  if (keyboards[state]) {
    const keyboard = keyboards[state]();
    if (state !== 'setup_ui') keyboard.inline_keyboard.push([{ text: text(lang, 'back'), callback_data: 'setup_back:yes' }]);
    return renderMessage(chatId, text(lang, state), keyboard, messageId);
  }
  return renderMessage(chatId, text(lang, 'review', {
    learn: label(settings.learning_language), level: settings.level,
    explain: label(settings.explanation_language), interval: intervalLabel(settings.interval_minutes, lang),
  }), { inline_keyboard: [[{ text: text(lang, 'confirm'), callback_data: 'setup_confirm:yes' }],
    [{ text: text(lang, 'restart'), callback_data: 'setup_restart:yes' }]] }, messageId);
}

// Persist and lock each step so stale buttons cannot skip or overwrite steps.
async function setupChoice(client, chatId, kind, value) {
  await client.query('BEGIN');
  try {
    const result = await client.query(`SELECT p.*, s.level FROM subscriber_preferences p JOIN subscribers s USING (chat_id)
      WHERE p.chat_id = $1 AND s.is_active = TRUE FOR UPDATE OF p`, [chatId]);
    const settings = result.rows[0];
    if (!settings?.input_state?.startsWith('setup_')) {
      await client.query('COMMIT');
      return { missing: true };
    }
    if (kind !== settings.input_state && !['setup_restart', 'setup_back'].includes(kind)) {
      await client.query('COMMIT');
      return { state: settings.input_state, settings };
    }
    const previous = { setup_ui: 'setup_ui', setup_learn: 'setup_ui', setup_level: 'setup_learn', setup_explain: 'setup_level', setup_interval: 'setup_explain', setup_confirm: 'setup_interval' };
    const next = kind === 'setup_back' ? previous[settings.input_state] : { setup_ui: 'setup_learn', setup_learn: 'setup_level', setup_level: 'setup_explain', setup_explain: 'setup_interval', setup_interval: 'setup_confirm', setup_restart: 'setup_ui', setup_confirm: null }[kind];
    if (kind === 'setup_level') {
      await client.query('UPDATE subscribers SET level = $1 WHERE chat_id = $2', [value, chatId]);
      settings.level = value;
    }
    const column = { setup_ui: 'ui_language', setup_learn: 'learning_language', setup_explain: 'explanation_language', setup_interval: 'interval_minutes' }[kind];
    if (column) {
      settings[column] = kind === 'setup_interval' ? Number(value) : value;
      await client.query(`UPDATE subscriber_preferences SET ${column} = $1 WHERE chat_id = $2`, [settings[column], chatId]);
    }
    await client.query(`UPDATE subscriber_preferences SET input_state = $1, updated_at = now(),
      next_due_at = CASE WHEN $1::text IS NULL THEN next_delivery_at(interval_minutes) ELSE next_due_at END
      WHERE chat_id = $2`, [next, chatId]);
    await client.query('COMMIT');
    return { state: next, settings };
  } catch (error) {
    await client.query('ROLLBACK');
    throw error;
  }
}

async function withDb(fn) {
  const client = new Client(postgresOptions(process.env.DATABASE_URL));
  await client.connect();
  try {
    const botId = (process.env.BOT_TOKEN || '').split(':')[0];
    if (!/^[0-9]+$/.test(botId)) throw new Error('A valid BOT_TOKEN is required');
    // Digits-only bot ID keeps this identifier safe and stable across token rotations.
    const schema = `bot_${botId}`;
    // Schema changes belong to the setup/worker migration path, never a user request.
    // A missing migration fails closed and Telegram can retry after initialization.
    await client.query(`SET search_path TO "${schema}"`);
    return await fn(client);
  } finally {
    await client.end();
  }
}

async function telegram(method, payload) {
  const response = await fetch(`https://api.telegram.org/bot${process.env.BOT_TOKEN}/${method}`, {
    method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(payload),
  });
  const body = await response.json();
  // Repeated taps and retried callbacks may render exactly the same screen.
  if (method === 'editMessageText' && body.error_code === 400 &&
      body.description?.includes('message is not modified')) return;
  if (!response.ok || !body.ok) throw new Error(`Telegram ${method} failed: ${body.description || response.status}`);
}

async function sendMessage(chatId, text, keyboard) {
  await telegram('sendMessage', { chat_id: chatId, text, ...(keyboard ? { reply_markup: keyboard } : {}) });
}

// Only the initial command sends a message. Button navigation edits that message.
async function renderMessage(chatId, text, keyboard, messageId) {
  if (messageId == null) return sendMessage(chatId, text, keyboard);
  await telegram('editMessageText', {
    chat_id: chatId, message_id: messageId, text,
    reply_markup: keyboard || { inline_keyboard: [] },
  });
}

export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(200).send('SceneLingo webhook');
  if (!process.env.BOT_TOKEN) return res.status(503).send('Webhook unavailable');
  if (!authorizedWebhook(req.headers?.['x-telegram-bot-api-secret-token'], process.env.BOT_TOKEN)) {
    return res.status(403).send('Forbidden');
  }
  try {
    const update = req.body || {};
    const callback = update.callback_query;
    if (callback) {
      const chat = callback.message?.chat;
      const messageId = callback.message?.message_id;
      const [kind, value] = (callback.data || '').split(':');
      const valid = (lessonAction(kind) && /^[1-9][0-9]{0,15}$/.test(value)) || (['level', 'setup_level'].includes(kind) && LEVELS.includes(value)) ||
        (['ui', 'setup_ui'].includes(kind) && UI_LANGUAGES.has(value)) ||
        (['setup_learn', 'setup_explain'].includes(kind) && CODES.has(value)) ||
        (['interval', 'setup_interval'].includes(kind) && validInterval(value)) ||
        (['setup_confirm', 'setup_restart', 'setup_back'].includes(kind) && value === 'yes') ||
        (['learn', 'explain'].includes(kind) && CODES.has(value));
      if (!chat || chat.type !== 'private' || callback.from?.id !== chat.id || !valid) {
        await telegram('answerCallbackQuery', { callback_query_id: callback.id, text: text(fallbackLanguage(callback.from), 'invalid') });
        return res.status(200).send('ok');
      }
      const lang = await interfaceLanguage(chat.id, fallbackLanguage(callback.from));
      if (lessonAction(kind)) {
        const action = await withDb(client => applyLessonAction(client, chat.id, kind, value));
        const ar = lang === 'ar';
        const notices = ar ? {saved:'اتحفظ ⭐ راجعه من /saved أو /review',reported:'وصلتنا الملاحظة، شكرًا ليك',reviewed:'اتحدد موعد المراجعة الجاية ✅',missing:'التعبير غير متاح أو الاختيار اتسجل قبل كده'}
          : {saved:'Saved ⭐ Use /saved or /review',reported:'Thanks for your feedback',reviewed:'Next review scheduled ✅',missing:'Lesson unavailable or already reviewed'};
        await telegram('answerCallbackQuery', {callback_query_id:callback.id,text:notices[action.kind] || ''});
        if (action.kind === 'show') await renderMessage(chat.id, action.caption, {inline_keyboard:[[
          {text:ar?'فاكره ✅':'Remembered ✅',callback_data:`lesson_known:${value}`},
          {text:ar?'أراجعه بكرة ↻':'Review tomorrow ↻',callback_data:`lesson_repeat:${value}`}
        ]]}, messageId);
        else if (action.kind === 'reviewed') await renderMessage(chat.id, notices.reviewed, undefined, messageId);
        return res.status(200).send('ok');
      }
      if (kind.startsWith('setup_')) {
        const result = await withDb(client => setupChoice(client, chat.id, kind, value));
        await telegram('answerCallbackQuery', { callback_query_id: callback.id });
        if (result.missing) await renderMessage(chat.id, text(lang, 'missing'), undefined, messageId);
        else if (result.state) await setupPrompt(chat.id, result.state, result.settings, lang, messageId);
        else await renderMessage(chat.id, text(lang, result.settings.interval_minutes === 30 ? 'done_halfhour' : 'done', { interval: intervalLabel(result.settings.interval_minutes, lang) }), undefined, messageId);
        return res.status(200).send('ok');
      }
      const result = await withDb(async client => {
        const state = await client.query('SELECT input_state FROM subscriber_preferences WHERE chat_id = $1', [chat.id]);
        if (state.rows[0]?.input_state?.startsWith('setup_')) {
          const settings = await client.query('SELECT p.*, s.level FROM subscriber_preferences p JOIN subscribers s USING (chat_id) WHERE p.chat_id = $1', [chat.id]);
          return { setup: state.rows[0].input_state, settings: settings.rows[0] };
        }
        if (kind === 'ui') return client.query(`INSERT INTO subscriber_preferences (chat_id, ui_language, next_due_at)
          SELECT chat_id, $1, subscribed_at + interval '3 hours' FROM subscribers WHERE chat_id = $2 AND is_active = TRUE
          ON CONFLICT (chat_id) DO UPDATE SET ui_language = EXCLUDED.ui_language, updated_at = now() RETURNING chat_id`, [value, chat.id]);
        if (kind === 'interval') return client.query(`UPDATE subscriber_preferences p SET interval_minutes = $1,
          next_due_at = next_delivery_at($1::integer), input_state = NULL, updated_at = now()
          FROM subscribers s WHERE p.chat_id = $2 AND s.chat_id = p.chat_id AND s.is_active = TRUE RETURNING p.chat_id`, [Number(value), chat.id]);
        if (kind === 'level') return client.query(
          'UPDATE subscribers SET level = $1 WHERE chat_id = $2 AND is_active = TRUE RETURNING level', [value, chat.id]);
        // Insert only for active subscribers, preserving all other preferences.
        const column = kind === 'learn' ? 'learning_language' : 'explanation_language';
        return client.query(`INSERT INTO subscriber_preferences (chat_id, ${column}, next_due_at)
          SELECT chat_id, $1, subscribed_at + interval '3 hours' FROM subscribers WHERE chat_id = $2 AND is_active = TRUE
          ON CONFLICT (chat_id) DO UPDATE SET ${column} = EXCLUDED.${column}, updated_at = now()
          RETURNING ${column}`, [value, chat.id]);
      });
      await telegram('answerCallbackQuery', { callback_query_id: callback.id });
      if (result.setup) {
        await setupPrompt(chat.id, result.setup, result.settings, lang, messageId);
        return res.status(200).send('ok');
      }
      const displayValue = kind === 'interval' ? intervalLabel(value, lang) : label(value);
      await renderMessage(chat.id, result.rowCount
        ? text(kind === 'ui' ? value : lang, kind === 'interval' && value === '30' ? 'saved_interval_halfhour' : `saved_${kind}`, { value: displayValue })
        : text(lang, 'subscribe'), undefined, messageId);
      return res.status(200).send('ok');
    }
    const message = update.message || {};
    const chat = message.chat;
    if (!chat || chat.type !== 'private') return res.status(200).send('ok');
    const command = (message.text || '').trim().split(/\s+/)[0].split('@')[0].toLowerCase();
    const chatId = chat.id;
    const lang = await interfaceLanguage(chatId, fallbackLanguage(message.from));
    if (command === '/saved' || command === '/review') {
      const rows = await withDb(async client => (await client.query(`SELECT s.content_id,c.phrase,c.learning_language
        FROM saved_lessons s JOIN lesson_content c ON c.id=s.content_id
        WHERE s.chat_id=$1 ${command === '/review' ? 'AND s.next_review_at<=now()' : ''}
        ORDER BY s.next_review_at LIMIT 10`, [chatId])).rows);
      const ar = lang === 'ar';
      if (!rows.length) await sendMessage(chatId, ar?'مفيش تعبيرات مستحقة للمراجعة أو محفوظة لسه. احفظ تعبير من الزر تحت المقطع ⭐':'No saved lessons or reviews due yet. Save an expression below a clip ⭐');
      else if (command === '/saved') await sendMessage(chatId, (ar?'⭐ تعبيراتك المحفوظة (أول ١٠)\n\n':'⭐ Your saved expressions (first 10)\n\n')+rows.map(row=>`${row.phrase} · ${row.learning_language.toUpperCase()}`).join('\n\n')+'\n\n/review');
      else await sendMessage(chatId,(ar?'🧠 حاول تفتكر المعنى ومثال لاستخدام التعبير:\n\n':'🧠 Recall the meaning and think of an example:\n\n')+rows[0].phrase,
        {inline_keyboard:[[{text:ar?'إظهار الشرح':'Show explanation',callback_data:`lesson_show:${rows[0].content_id}`}]]});
    } else if (command === '/start') {
      await withDb(async client => {
        await client.query('BEGIN');
        try {
          await client.query(`INSERT INTO subscribers (chat_id, username, first_name, is_active)
            VALUES ($1, $2, $3, TRUE) ON CONFLICT (chat_id) DO UPDATE
            SET username = EXCLUDED.username, first_name = EXCLUDED.first_name, is_active = TRUE`,
          [chatId, message.from?.username || null, message.from?.first_name || null]);
          await client.query(`INSERT INTO subscriber_preferences (chat_id, input_state, ui_language)
            VALUES ($1, 'setup_ui', $2) ON CONFLICT (chat_id) DO UPDATE
            SET input_state = 'setup_ui', updated_at = now()`, [chatId, lang]);
          await client.query('COMMIT');
        } catch (error) { await client.query('ROLLBACK'); throw error; }
      });
      await setupPrompt(chatId, 'setup_ui', {}, lang);
    } else if (['/learn', '/explain', '/level', '/interval', '/language'].includes(command) && await withDb(async client => {
      const state = await client.query('SELECT input_state FROM subscriber_preferences WHERE chat_id = $1', [chatId]);
      if (!state.rows[0]?.input_state?.startsWith('setup_')) return false;
      // Re-open the wizard without showing an incomplete review.
      const result = await client.query('SELECT p.*, s.level FROM subscriber_preferences p JOIN subscribers s USING (chat_id) WHERE p.chat_id = $1', [chatId]);
      await setupPrompt(chatId, state.rows[0].input_state, result.rows[0], lang);
      return true;
    })) {
      // Finish the current setup before editing individual settings.
    } else if (command === '/language') {
      await sendMessage(chatId, text(lang, 'choose_ui'), uiKeyboard());
    } else if (command === '/learn' || command === '/explain') {
      const kind = command === '/learn' ? 'learn' : 'explain';
      await sendMessage(chatId, text(lang, kind), languageKeyboard(kind));
    } else if (command === '/interval') {
      const result = await withDb(client => client.query(`INSERT INTO subscriber_preferences (chat_id, input_state, next_due_at)
        SELECT chat_id, 'interval', subscribed_at + interval '3 hours' FROM subscribers WHERE chat_id = $1 AND is_active = TRUE
        ON CONFLICT (chat_id) DO UPDATE SET input_state = 'interval' RETURNING chat_id`, [chatId]));
      await sendMessage(chatId, text(lang, result.rowCount ? 'interval' : 'subscribe'), result.rowCount ? intervalKeyboard('interval', lang) : undefined);
    } else if (command === '/level') {
      const result = await withDb(client => client.query('SELECT level FROM subscribers WHERE chat_id = $1 AND is_active = TRUE', [chatId]));
      await sendMessage(chatId, result.rows.length ? text(lang, 'level', { level: result.rows[0].level }) : text(lang, 'subscribe'), result.rows.length ? levelKeyboard('level', lang) : undefined);
    } else if (command === '/stop') {
      await withDb(client => client.query('UPDATE subscribers SET is_active = FALSE WHERE chat_id = $1', [chatId]));
      await sendMessage(chatId, text(lang, 'stopped'));
    } else if (command === '/today') {
      const result = await withDb(client => client.query(`SELECT s.level, p.phrase, p.video_title
        FROM subscribers s
        LEFT JOIN subscriber_preferences settings ON settings.chat_id = s.chat_id
        LEFT JOIN LATERAL (
          SELECT phrase, video_title FROM sent_phrases
          WHERE level = s.level AND learning_language = COALESCE(settings.learning_language, 'en')
          ORDER BY sent_at DESC LIMIT 1
        ) p ON TRUE WHERE s.chat_id = $1 AND s.is_active = TRUE`, [chatId]));
      const row = result.rows[0];
      await sendMessage(chatId, !row ? text(lang, 'subscribe') : row.phrase
        ? text(lang, 'today', { level: row.level, phrase: row.phrase, title: row.video_title || '—' })
        : text(lang, 'empty', { level: row.level }));
    } else if (command === '/help') {
      await sendMessage(chatId, text(lang, 'welcome'));
    } else if (message.text) {
      const result = await withDb(client => client.query(`SELECT p.*, s.level FROM subscriber_preferences p
        JOIN subscribers s USING (chat_id) WHERE p.chat_id = $1 AND s.is_active = TRUE`, [chatId]));
      const settings = result.rows[0];
      if (settings?.input_state?.startsWith('setup_')) {
        await setupPrompt(chatId, settings.input_state, settings, lang);
      } else if (settings?.input_state === 'interval') {
        await sendMessage(chatId, text(lang, 'buttons'), intervalKeyboard('interval', lang));
      } else {
        await sendMessage(chatId, text(lang, 'unknown'));
      }
    }

  } catch (err) {
    console.error('webhook error', err);
    return res.status(500).send('temporary error');
  }
  return res.status(200).send('ok');
}
