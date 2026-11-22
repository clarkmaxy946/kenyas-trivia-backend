from django.utils import timezone

from kenyastrivia.errors import ApiError

from .models import MatchStatus as S

ALLOWED = {
    S.SETTING_UP: {S.WAITING_FOR_CARDS, S.IN_PROGRESS, S.SETUP_FAILED, S.ABANDONED},
    S.WAITING_FOR_CARDS: {S.IN_PROGRESS, S.SETUP_FAILED, S.ABANDONED},
    S.SETUP_FAILED: {S.SETTING_UP, S.WAITING_FOR_CARDS, S.ABANDONED},
    S.IN_PROGRESS: {S.FINISHED},
    S.FINISHED: set(),
    S.ABANDONED: set(),
}


def can_transition(current, new):
    return new in ALLOWED[current]


def transition(match, new_status):
    if not can_transition(match.status, new_status):
        raise ApiError(
            "wrong_state",
            f"A match that is {match.status} cannot become {new_status}.",
            409,
        )
    match.status = new_status
    if new_status == S.FINISHED:
        match.finished_at = timezone.now()
    match.save()