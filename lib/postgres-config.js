// Enforce CA/hostname verification even when a connection URL requests weak SSL.
export function postgresOptions(connectionString) {
  if (connectionString) {
    const url = new URL(connectionString);
    // Per-bot search_path spans multiple transactions and needs a session.
    if (url.hostname.endsWith('.neon.tech') && url.hostname.split('.')[0].endsWith('-pooler')) {
      url.hostname = url.hostname.replace('-pooler.', '.');
    }
    for (const key of ['sslmode','ssl','sslcert','sslkey','sslrootcert','uselibpqcompat']) url.searchParams.delete(key);
    connectionString = url.toString();
  }
  return {connectionString, ssl:{rejectUnauthorized:true}, connectionTimeoutMillis:10000, statement_timeout:15000};
}
