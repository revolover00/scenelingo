import { createHmac } from 'node:crypto';
import { isIP } from 'node:net';
import pg from 'pg';
import { postgresOptions } from './postgres-config.js';

export function loginKey(req) {
  // Vercel overwrites this header. Never trust caller-supplied X-Forwarded-For.
  const address = process.env.VERCEL === '1'
    ? req.headers['x-vercel-forwarded-for'] : req.socket?.remoteAddress;
  const ip = typeof address === 'string' && isIP(address.trim()) ? address.trim() : 'unknown';
  return createHmac('sha256', process.env.DASHBOARD_PASSWORD_HASH).update(ip).digest('hex');
}

export async function loginAttempt(req, successful = false) {
  const botId = (process.env.BOT_TOKEN || '').split(':')[0];
  if (!/^\d+$/.test(botId)) throw new Error('Missing bot identity');
  const client = new pg.Client(postgresOptions(process.env.DATABASE_URL));
  try {
    await client.connect();
    await client.query(`SET search_path TO "bot_${botId}"`);
    const key = loginKey(req);
    if (successful) {
      await client.query('DELETE FROM admin_login_limits WHERE key_hash=$1', [key]);
      return true;
    }
    await client.query("DELETE FROM admin_login_limits WHERE expires_at < now()-interval '1 day'");
    const result = await client.query(`INSERT INTO admin_login_limits(key_hash,attempts,expires_at)
      VALUES($1,1,now()+interval '15 minutes') ON CONFLICT(key_hash) DO UPDATE SET
      attempts=CASE WHEN admin_login_limits.expires_at<=now() THEN 1 ELSE admin_login_limits.attempts+1 END,
      expires_at=CASE WHEN admin_login_limits.expires_at<=now() THEN now()+interval '15 minutes' ELSE admin_login_limits.expires_at END
      RETURNING attempts<=20 AS allowed`, [key]);
    return result.rows[0]?.allowed === true;
  } finally { await client.end(); }
}
