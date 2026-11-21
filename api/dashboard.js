import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { authorized, snapshot } from '../lib/dashboard.js';
import { loginAttempt } from '../lib/admin-rate-limit.js';

export default async function handler(req, res) {
  res.setHeader('Cache-Control', 'private, no-store');
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('X-Frame-Options', 'DENY');
  res.setHeader('Referrer-Policy', 'no-referrer');
  if (req.method !== 'GET') { res.setHeader('Allow', 'GET'); return res.status(405).send('Method not allowed'); }
  if (!process.env.DASHBOARD_PASSWORD_HASH) return res.status(503).send('Dashboard access is not configured');
  // Empty challenges cannot guess a password; rate-limit every supplied credential
  // before checking it, so a blocked client cannot keep guessing for a 200 oracle.
  if (req.headers.authorization) {
    try {
      if (!await loginAttempt(req)) {
        res.setHeader('Retry-After', '900');
        return res.status(429).send('Too many sign-in attempts. Try again later.');
      }
    } catch { return res.status(503).send('Sign-in temporarily unavailable'); }
  }
  if (!authorized(req.headers.authorization, process.env.DASHBOARD_PASSWORD_HASH)) {
    res.setHeader('WWW-Authenticate', 'Basic realm="SceneLingo admin", charset="UTF-8"');
    return res.status(401).send('Private dashboard. Sign in as admin.');
  }
  try { await loginAttempt(req, true); }
  catch { return res.status(503).send('Sign-in temporarily unavailable'); }
  if (req.query?.data === '1') {
    try { return res.status(200).json(await snapshot({page:req.query?.page,search:req.query?.search})); }
    catch { return res.status(503).json({ error: 'تعذر تحميل البيانات. حاول تاني بعد شوية.' }); }
  }
  const html = readFileSync(new URL('../dashboard.html', import.meta.url), 'utf8');
  const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
  const hash = createHash('sha256').update(script).digest('base64');
  res.setHeader('Content-Security-Policy', `default-src 'none'; script-src 'sha256-${hash}'; style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'`);
  res.setHeader('Content-Type', 'text/html; charset=utf-8');
  return res.status(200).send(html);
}
