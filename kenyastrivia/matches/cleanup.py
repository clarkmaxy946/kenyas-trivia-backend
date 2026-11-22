from datetime import timedelta

from django.utils import timezone

from cards import store
from generations.models import GenerationJob
from users.models import GuestSession

from .models import Match
from .models import MatchStatus as S

FINISHED_GUEST_KEEP = timedelta(minutes=10)
UNFINISHED_KEEP = timedelta(hours=3)
JOB_KEEP = timedelta(days=30)

UNFINISHED_STATES = [S.SETTING_UP, S.WAITING_FOR_CARDS, S.IN_PROGRESS, S.SETUP_FAILED, S.ABANDONED]


def _delete_matches(queryset):
    ids = list(queryset.values_list("id", flat=True))
    for match_id in ids:
        store.forget_match(match_id)
    queryset.delete()
    return len(ids)


def run_cleanup(now=None):
    """Delete data nobody needs any more. Returns how much of each kind was removed."""
    now = now or timezone.now()
    counts = {}

    counts["stale_matches"] = _delete_matches(
        Match.objects.filter(status__in=UNFINISHED_STATES, updated_at__lt=now - UNFINISHED_KEEP)
    )
    counts["finished_guest_matches"] = _delete_matches(
        Match.objects.filter(
            guest__isnull=False, status=S.FINISHED, finished_at__lt=now - FINISHED_GUEST_KEEP
        )
    )

    expired = GuestSession.objects.filter(expires_at__lt=now)
    counts["expired_guest_sessions"] = expired.count()
    expired.delete()  # their remaining matches go with them

    old_jobs = GenerationJob.objects.filter(created_at__lt=now - JOB_KEEP)
    counts["old_jobs"] = old_jobs.count()
    old_jobs.delete()

    return counts