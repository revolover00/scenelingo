"""Replenish verified lessons between deliveries; never send Telegram messages."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import content_reserve
import daily_job
import db
import delivery_store
import preparation


def main():
    db.init_db()
    with delivery_store.worker_lock() as acquired:
        if not acquired:
            raise RuntimeError('Reserve worker could not acquire shared lock')
        preparation.cleanup()
        built, failed = content_reserve.refill(db.due_subscribers(1440),
            daily_job.select_localized_clip, daily_job.localized_caption)
        if failed:
            raise RuntimeError('Verified lesson reserve refill failed')


if __name__ == '__main__':
    main()
