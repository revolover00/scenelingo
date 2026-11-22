"""Read aggregate scheduler load without exposing subscriber identities."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import db
with db.connect() as conn, conn.cursor() as cur:
    cur.execute('SELECT count(*), count(DISTINCT level) FROM subscribers WHERE is_active = TRUE')
    total, groups = cur.fetchone()
    print(f'::notice title=Scheduler capacity::Active subscribers={total}; active level groups={groups}', flush=True)
