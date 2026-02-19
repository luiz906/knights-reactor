"""
Knights Reactor — Scheduler
Runs the pipeline every 8 hours (matching n8n's "Every 8 Hours" trigger).

Usage:
  python scheduler.py              # Run on schedule (every 8 hours)
  python scheduler.py --now        # Run once immediately
  python scheduler.py --interval 6 # Run every 6 hours instead

Or use cron:
  0 */8 * * * cd /path/to/knights-reactor && python -c "from pipeline import run_pipeline; run_pipeline()"
"""

import sys, time, logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("scheduler")

def main():
    from pipeline import run_pipeline

    # Parse args
    if "--now" in sys.argv:
        log.info("Running pipeline immediately...")
        result = run_pipeline()
        log.info(f"Result: {result['status']}")
        return

    interval_hours = 8
    for i, arg in enumerate(sys.argv):
        if arg == "--interval" and i + 1 < len(sys.argv):
            interval_hours = int(sys.argv[i + 1])

    interval_secs = interval_hours * 3600

    log.info(f"⚔️  Knights Reactor Scheduler")
    log.info(f"   Interval: every {interval_hours} hours")
    log.info(f"   Press Ctrl+C to stop")

    while True:
        log.info(f"\n{'='*50}")
        log.info(f"Starting pipeline run at {datetime.now().strftime('%Y-%m-%d %H:%M')}")

        try:
            result = run_pipeline()
            log.info(f"Pipeline result: {result['status']}")
        except Exception as e:
            log.error(f"Pipeline crashed: {e}")

        next_run = datetime.now().timestamp() + interval_secs
        next_time = datetime.fromtimestamp(next_run).strftime('%I:%M %p')
        log.info(f"Next run at {next_time}")

        time.sleep(interval_secs)


if __name__ == "__main__":
    main()
