from datetime import timedelta

TURN_SECONDS = 55
GRACE = timedelta(seconds=10)
RETRY_WINDOW = timedelta(minutes=2)
SETUP_TIMEOUT = timedelta(minutes=1)


def submission_allowed(started_at, now, attempt):
    """First attempt: 55 s plus grace. Retries (attempt 2, 3, ...): up to 2 minutes."""
    elapsed = now - started_at
    if attempt <= 1:
        return elapsed <= timedelta(seconds=TURN_SECONDS) + GRACE
    return elapsed <= RETRY_WINDOW


def turn_is_overdue(started_at, now):
    """A turn still open after the retry window is treated as abandoned."""
    return now - started_at > RETRY_WINDOW


def setup_is_expired(last_activity, now):
    return now - last_activity > SETUP_TIMEOUT