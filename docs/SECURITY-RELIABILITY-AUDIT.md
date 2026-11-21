# Security and reliability review

This targeted source review covers delivery, preparation storage, database
connections, webhook/dashboard controls and production npm dependencies. It is
not a penetration test, compliance certification or guarantee of no remaining bugs.

## Confirmed findings addressed

| Priority | Finding | Change |
| --- | --- | --- |
| High | Node database connections explicitly disabled TLS certificate verification. | Shared verified-TLS configuration removes URL SSL overrides, verifies CA/hostname and sets connection/statement timeouts. Validated with the actual handler against the configured database before rollout. |
| High | Python connection contexts committed/rolled back but did not guarantee connection closure. | Short-lived `db.session()` commits/rolls back and closes, while the separate advisory-lock connection retains its session lifetime. |
| Medium | A failed legacy phrase summary could abort later groups after a successful send. | Summary writes are best effort; the durable per-recipient receipt remains authoritative. |
| Medium | A rejected Telegram file ID was reused for later recipients, and the first recipient's schedule was advanced despite definite rejection. | Invalidate the cache, preserve the refused slot for bounded retry, and skip remaining recipients of that cohort instead of sending the known-invalid reference. No replay of ambiguous sends was added. |
| Medium | Eligibility compared settings and overdue status, but not the snapshot's exact slot. | Match the captured due timestamp when present, including the lookahead path. |
| Medium | A growing file could be read unbounded before a post-read size check. | Read at most the configured media limit plus one byte, then reject oversize content. |
| Medium | Reloading a saved lesson could select a different matching movie while retaining the original caption/source. | Refuse a reloaded clip whose identity differs from the saved lesson; no silent source substitution. |
| Low | Local Serverless credentials and environment variants were not explicitly ignored. | Ignore `.tgcloud/` and `.env.*`, preserving `.env.example`. |

## Validation

- Regression tests cover connection closure on success/failure, exact-slot
  preflight, invalid cached IDs and continuation after legacy-summary failure.
- SQL integration tests and the disposable-schema lifecycle exercise the actual
  scheduling/storage paths without sending to real subscribers.
- The authenticated browser workflow checks the real database handler, subscriber
  search, navigation, mobile overflow and unauthenticated access rejection.
- `npm audit --omit=dev` reported zero known production dependency vulnerabilities
  at review time. This does not cover Python dependencies, unknown vulnerabilities
  or development-only dependencies.

## Remaining operational considerations

- PostgreSQL credentials in a connection URL must remain secret. Python/libpq TLS
  policy still follows the deployment DSN; this review does not certify its CA
  verification settings.
- Telegram has no atomic transaction with the database. Ambiguous sends remain
  uncertain and are not automatically replayed; perfect exactly-once delivery is
  not promised.
- Provider quotas and missing verified content can still delay delivery. No audio
  verification, language matching or CEFR setting was bypassed.
- Database migrations still run during webhook database initialization, which can
  increase latency/locking; moving them exclusively to deployment needs a separate
  migration rollout strategy.
- Admin credentials have no application-level lockout/rate limiter, and previously
  disclosed tokens require revocation by their owner. This review cannot confirm
  revocation from repository contents.
- A separate Python dependency vulnerability scan and independent security review
  remain advisable. Copyright permissions for film excerpts remain an operator
  responsibility.

## Operational follow-up

- Preparation now starts up to **30 minutes** before the current slot rather than
  ten. Only the current slot is prepared; due-time preflight still prevents early
  sends. This creates more retry opportunities, not a guarantee of provider supply.
- A read-only aggregate health check fails the daily workflow when eligible users
  are more than 15 minutes overdue, or uncertain/stale in-flight sends remain
  unresolved. No automatic replay or resolution is performed. Production workflow failure opens one GitHub
  incident, deduplicated until a healthy production run closes it. Alerts contain
  no subscriber identifiers, secrets or raw logs. GitHub notification delivery
  depends on repository notification settings. A complete GitHub/external-cron
  outage cannot be detected by a monitor running on the same service.
- Python PostgreSQL transport now enforces `verify-full` with the certifi CA bundle,
  a ten-second connection timeout and a fifteen-second statement timeout. It never
  falls back to weaker TLS. The isolated database integration uses this transport.
- Webhook requests no longer execute schema migrations. The explicit **Database
  migrations** workflow runs for SQL changes on main and supports manual runs.
  Existing setup/worker initialization remains as a compatibility fallback.
  For incompatible future schema changes, deploy additive migrations **before**
  code. Missing schema fails closed; never restore runtime webhook DDL to hide it.
- Admin login attempts with supplied credentials are throttled in PostgreSQL:
  twenty tries per IP per fifteen-minute window, shared across instances. A
  successful login clears its counter. Blocked attempts are rejected before
  password comparison; valid guesses cannot bypass a locked window. Only salted
  address hashes are stored; expired rows are cleaned after one day. Vercel's
  trusted forwarding header is used, never arbitrary X-Forwarded-For. Proxies/NAT
  can share a counter; distributed attacks still require edge/WAF controls.
- A PyPI vulnerability scan of the installed Python environment found no known
  advisories at scan time. This is neither a source-code audit nor protection
  against future or undisclosed vulnerabilities.

These follow-ups supersede the earlier Python TLS, webhook migration, admin
throttling and missing Python dependency scan items. Still outside software-only
closure: provider availability/quotas, external scheduling precision, independent
penetration testing, rights to media and revocation of previously exposed secrets.
No automatic replay of uncertain Telegram sends has been introduced.

## Recurring content starvation: structural correction

The next real scheduled run still failed before `sendVideo`: there was no verified
unseen C1 English lesson. Increasing lookahead or generating another exact phrase
had not removed the underlying dependency on a scarce exact movie quote. A green
idle run, or a single recovered send, was insufficient evidence of steady supply.

English selection now also uses the source-first path: download available speech,
verify its language, and select a level-appropriate contiguous expression from its
actual transcript. Search seeds are hints, not the lesson text. The selected text
must still occur in the transcript, be multiword, and not already be used/reserved.
The approximate model-assigned CEFR level is not an independent certification.

A demand-only reserve targets **three ready unseen lessons per learner**. Each
scheduled invocation attempts at most one refill, after due delivery, using the
existing 80 MiB/24-hour durable media budget and reusable Telegram file cache.
Only active, setup-complete subscribers due within a day cause work. Each lesson
needs its requested-language caption before it counts as ready. Partial captions
resume on the same media. No refill sends, claims a slot, or changes a schedule.
At delivery time the existing oldest-unseen queue can use this stock without
search/transcription/explanation calls. Failed refill remains visible, not silently
reported as healthy. Different groups are prioritized by lowest available stock.
This is a **target**, not a claim that three lessons always exist: provider outages,
quotas or a full media budget can still prevent replenishment.

The live GitHub CLI represents the Actions author as `app/github-actions`, whereas
the initial mock used `github-actions[bot]`. Alert reconciliation now accepts both
exact trusted identities while retaining marker/title checks; human issues remain
untouched. This fixes the observed duplicate incidents.

Session correctness is also required, not just transport encryption: this code
uses `SET search_path` and session-level advisory locks across transactions.
Recognized Neon `ep-…-pooler.…neon.tech` endpoints are now routed to their direct
session counterpart in Python and Node. Custom/non-Neon hosts are unchanged.
Transaction pooling is incompatible with those session assumptions and can cause
intermittent schema/lock behavior; the first expanded integration failed during
preparation, so the session-compatible path is tested before rollout. This does
not retroactively prove pooling caused every earlier missing message.

Saved lessons are restored from their exact stored source page and clip ID, not a
fresh phrase search which might return another scene first. Identity and audio
verification remain mandatory. Missing/changed original media still fails safely.
Content failures now log the safe processing-stage name (`lookup`,
`restore_saved_media`, `select_new_clip`, `check_unseen`) rather than only an opaque
exception class.

The direct-connection rollout also exposed a refused worker lock in the real
workflow. Legacy transaction-pooled session locks may remain on pooled backends,
so direct-session workers use a fresh namespace, **7195**, instead of 7194. No
pooled backend is terminated and no uncertain delivery is replayed. Failure to
acquire the lock now fails visibly rather than returning a misleading idle success.
The database migration workflow includes a two-connection, randomly namespaced
check: session settings survive commits independently, a simultaneous lock is
refused, and disconnecting its owner releases it. This does not touch subscriber
tables or actual worker lock keys.

## Production regression after repository history replacement

The later production failure ran commit `a845c1acb1d4ea923ef450c67375a0873a8b9a76`,
whose history no longer shared an ancestor with the deployed reliability release
`e037c3a767c61bf8811cfb6718cba8a946a45817` (GitHub compare returned no common
ancestor). Its tree had removed the reserve, transcript cache, session transport,
health/alert steps and multiple security/regression tests. The latest failure also
showed unsuccessful C2 content search and provider HTTP 429 responses. The record
does not identify who changed history, and deleting a merged feature branch alone
cannot produce that change to main.

The recovery is based on the current main history, preserves its newer README,
and restores the verified reliability implementation and tests without an
unrelated-history merge. A release capability contract now runs in CI and before
production delivery to reject accidental partial rollback. Its fingerprint is
printed in workflow annotations. It is not tamper-proof: a whole-history rewrite
can remove the check as well.

Attempts to read branch protection and to create a main ruleset blocking force
push/deletion returned HTTP 403 `Resource not accessible by integration`. No
branch protection was enabled by this session. Repository owner action remains
required: Settings → Rules → Rulesets, target `main`, active enforcement, block
force pushes and deletions; require pull requests and the `test` check. Restrict
bypass actors. Until that is done, repository-side prevention of another history
replacement is NOT complete.
