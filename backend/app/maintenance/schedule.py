"""Keep these constants aligned with maintenance.yml's UTC schedule."""

from datetime import timedelta

SCHEDULE_INTERVAL_HOURS = 6
CLEANUP_OVERDUE_AFTER = timedelta(hours=SCHEDULE_INTERVAL_HOURS + 1)
