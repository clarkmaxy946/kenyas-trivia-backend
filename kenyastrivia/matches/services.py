from datetime import timedelta

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from cards import store
from generations.jobs import queue_round, requeue_round
from generations.models import GenerationJob, JobStatus
from kenyastrivia.errors import ApiError

from .flow import next_step
from .models import ROUND_1, ROUND_2, TIEBREAKER, Match, Team, Turn
from .models import MatchStatus as S
from .models import TurnStatus as T
from .scoring import InvalidSubmission, score_turn
from .states import transition
from .timing import TURN_SECONDS, setup_is_expired, submission_allowed, turn_is_overdue

SETUP_STATES = {S.SETTING_UP, S.WAITING_FOR_CARDS, S.SETUP_FAILED}
ACTIVE_STATES = SETUP_STATES | {S.IN_PROGRESS}
ACTIVE_VALUES = {s.value for s in ACTIVE_STATES}
RESUME_WINDOW = timedelta(hours=3)
HISTORY_PAGE_SIZE = 20


# ---------- who owns the match ----------

def _is_guest(user):
    return getattr(user, "is_guest", False)


def _owner_kwargs(user):
    return {"guest_id": user.id} if _is_guest(user) else {"user": user}


def _owner_q(user):
    return Q(guest_id=user.id) if _is_guest(user) else Q(user=user)


def _locked_match(user, match_id):
    """Fetch one of the caller's matches and lock it. Call inside transaction.atomic()."""
    try:
        return Match.objects.select_for_update().get(_owner_q(user), pk=match_id)
    except (Match.DoesNotExist, ValueError, DjangoValidationError):
        raise ApiError("match_not_found", "Match not found.", 404)


# ---------- small helpers ----------

def _teams(match):
    return {team.position: team for team in match.teams.all()}


def _scores(match):
    totals = {1: 0, 2: 0}
    for turn in match.turns.filter(status=T.SUBMITTED).select_related("team"):
        totals[turn.team.position] += turn.points
    return totals


def _closed(match):
    turns = match.turns.exclude(status=T.IN_PROGRESS).select_related("team")
    return {(turn.round_number, turn.team.position) for turn in turns}

def _tiebreaker_points(match):
    points = {1: 0, 2: 0}
    turns = match.turns.filter(status=T.SUBMITTED, round_number=TIEBREAKER).select_related("team")
    for turn in turns:
        points[turn.team.position] += turn.points
    return points


def _next_step(match):
    return next_step(_closed(match), _scores(match), _tiebreaker_points(match))


def _generation_failed(match, round_number):
    return GenerationJob.objects.filter(
        match_id=match.id, round_number=round_number, status=JobStatus.FAILED
    ).exists()


def _finish(match, winner_position):
    if winner_position is None:
        match.is_draw = True
    else:
        match.winner = _teams(match)[winner_position]
    transition(match, S.FINISHED)
    store.forget_match(match.id)


def _abandon_overdue(match, now):
    for turn in match.turns.filter(status=T.IN_PROGRESS):
        if turn_is_overdue(turn.started_at, now):
            turn.status = T.ABANDONED
            turn.submitted_at = now
            turn.save()


def _resolve_progress(match):
    """After turns close: finish the match if the game is over (or the tiebreaker cannot be made)."""
    if match.status != S.IN_PROGRESS:
        return
    if match.turns.filter(status=T.IN_PROGRESS).exists():
        return
    step = _next_step(match)
    if step.kind == "finished":
        _finish(match, step.winner_position)
    elif (
        step.round_number == TIEBREAKER
        and store.get_card(match.id, TIEBREAKER, step.position) is None
        and _generation_failed(match, TIEBREAKER)
    ):
        _finish(match, None)  # tiebreaker cards failed after the retries: a draw


def _refresh(match):
    """The lazy checks, run at the start of every call. Nothing runs on a timer."""
    now = timezone.now()

    if match.status in SETUP_STATES and setup_is_expired(match.updated_at, now):
        transition(match, S.ABANDONED)
        store.forget_match(match.id)
        return

    if match.status == S.IN_PROGRESS:
        _abandon_overdue(match, now)

    if match.status in (S.SETTING_UP, S.WAITING_FOR_CARDS):
        if _generation_failed(match, ROUND_1):
            transition(match, S.SETUP_FAILED)
        elif match.status == S.WAITING_FOR_CARDS and store.round_is_ready(match.id, ROUND_1):
            transition(match, S.IN_PROGRESS)

    _resolve_progress(match)


def _status_payload(match):
    teams = _teams(match)
    scores = _scores(match)
    payload = {
        "id": str(match.id),
        "status": match.status,
        "teams": [{"position": p, "name": t.name, "score": scores[p]} for p, t in sorted(teams.items())],
        "open_turn": None,
        "next": None,
        "cards_ready": False,
        "result": None,
    }

    open_turn = match.turns.filter(status=T.IN_PROGRESS).select_related("team").first()
    if open_turn:
        payload["open_turn"] = {
            "id": str(open_turn.id),
            "round_number": open_turn.round_number,
            "team_position": open_turn.team.position,
            "started_at": open_turn.started_at,
        }

    if match.status in SETUP_STATES:
        payload["cards_ready"] = store.round_is_ready(match.id, ROUND_1)
    elif match.status == S.IN_PROGRESS and teams:
        step = _next_step(match)
        if step.kind == "turn":
            payload["next"] = {
                "team_position": step.position,
                "team_name": teams[step.position].name,
                "round_number": step.round_number,
            }
            payload["cards_ready"] = store.get_card(match.id, step.round_number, step.position) is not None
    elif match.status == S.FINISHED:
        payload["result"] = {
            "is_draw": match.is_draw,
            "winner_position": match.winner.position if match.winner_id else None,
        }
    return payload


def _turn_payload(turn, match):
    return {
        "turn": {
            "id": str(turn.id),
            "status": turn.status,
            "round_number": turn.round_number,
            "team_position": turn.team.position,
            "points": turn.points,
            "word_points": turn.word_points,
            "bonus_points": turn.bonus_points,
            "bonus_earned": turn.bonus_points > 0,
        },
        "match": _status_payload(match),
    }


# ---------- the operations behind the endpoints ----------

def create_match(user):
    match = Match.objects.create(**_owner_kwargs(user))
    queue_round(match.id, ROUND_1)
    return _status_payload(match)


def get_status(user, match_id):
    with transaction.atomic():
        match = _locked_match(user, match_id)
        _refresh(match)
        if match.status in ACTIVE_STATES:
            match.save(update_fields=["updated_at"])  # a poll counts as activity
        return _status_payload(match)


def _clean_names(names):
    if not isinstance(names, list) or len(names) != 2:
        raise ApiError("team_name_missing", "Enter a name for both teams.", 400)
    cleaned = [n.strip() if isinstance(n, str) else "" for n in names]
    if not all(cleaned):
        raise ApiError("team_name_missing", "Enter a name for both teams.", 400)
    if cleaned[0].casefold() == cleaned[1].casefold():
        raise ApiError("team_names_same", "The two teams need different names.", 400)
    return cleaned


def submit_team_names(user, match_id, names):
    cleaned = _clean_names(names)  # the name entered first plays first
    with transaction.atomic():
        match = _locked_match(user, match_id)
        _refresh(match)
        if match.status == S.ABANDONED:
            raise ApiError("setup_expired", "This match timed out. Start a new one.", 410)
        if match.teams.exists() or match.status not in (S.SETTING_UP, S.SETUP_FAILED):
            raise ApiError("wrong_state", "Team names cannot be entered now.", 409)
        if match.status == S.SETUP_FAILED:
            raise ApiError("setup_failed", "The cards could not be made. Try again.", 409)

        for position, name in enumerate(cleaned, start=1):
            Team.objects.create(match=match, position=position, name=name)

        if store.round_is_ready(match.id, ROUND_1):
            transition(match, S.IN_PROGRESS)
        else:
            transition(match, S.WAITING_FOR_CARDS)
        return _status_payload(match)


def retry(user, match_id):
    with transaction.atomic():
        match = _locked_match(user, match_id)
        _refresh(match)

        if match.status == S.ABANDONED:
            raise ApiError("setup_expired", "This match timed out. Start a new one.", 410)

        if match.status == S.SETUP_FAILED:
            requeue_round(match.id, ROUND_1)
            transition(match, S.WAITING_FOR_CARDS if match.teams.exists() else S.SETTING_UP)
            return _status_payload(match)

        if match.status == S.IN_PROGRESS and not match.turns.filter(status=T.IN_PROGRESS).exists():
            step = _next_step(match)
            if step.kind == "turn" and store.get_card(match.id, step.round_number, step.position) is None:
                requeue_round(match.id, step.round_number)
                return _status_payload(match)

        raise ApiError("match_not_failed", "Nothing needs retrying.", 409)


def _cards_error(match, round_number):
    job = GenerationJob.objects.filter(match_id=match.id, round_number=round_number).first()
    if job and job.status in (JobStatus.PENDING, JobStatus.RUNNING):
        return ApiError("cards_not_ready", "The cards are still being made.", 409)
    return ApiError("card_unavailable", "The cards are no longer available. Try again.", 410)


def start_turn(user, match_id):
    with transaction.atomic():
        match = _locked_match(user, match_id)
        _refresh(match)

        if match.status != S.IN_PROGRESS:
            if match.status == S.WAITING_FOR_CARDS:
                raise ApiError("cards_not_ready", "The cards are still being made.", 409)
            if match.status == S.SETUP_FAILED:
                raise ApiError("setup_failed", "The cards could not be made. Try again.", 409)
            if match.status == S.SETTING_UP:
                raise ApiError("wrong_state", "Enter the team names first.", 409)
            raise ApiError("match_not_playable", "This match is over.", 409)

        if match.turns.filter(status=T.IN_PROGRESS).exists():
            raise ApiError("turn_already_open", "A turn is already running.", 409)

        step = _next_step(match)
        if step.kind != "turn":
            raise ApiError("match_not_playable", "This match is over.", 409)

        card = store.get_card(match.id, step.round_number, step.position)
        if card is None:
            raise _cards_error(match, step.round_number)

        # Cards are made a round ahead: round 2 once round 1 starts, the tiebreaker once round 2 starts.
        if step.position == 1 and step.round_number in (ROUND_1, ROUND_2):
            queue_round(match.id, step.round_number + 1)

        team = _teams(match)[step.position]
        try:
            turn = Turn.objects.create(
                match=match, team=team, round_number=step.round_number, started_at=timezone.now()
            )
        except IntegrityError:
            raise ApiError("turn_already_open", "A turn is already running.", 409)

        return {
            "turn": {
                "id": str(turn.id),
                "round_number": turn.round_number,
                "team_position": team.position,
                "team_name": team.name,
                "seconds": TURN_SECONDS,
                "started_at": turn.started_at,
            },
            "card": card,
        }


def _parse_submission(data):
    bad = lambda text: ApiError("invalid_submission", text, 400)
    if not isinstance(data, dict):
        raise bad("Send a JSON object.")
    results = data.get("results")
    if not isinstance(results, list) or not all(isinstance(r, dict) for r in results):
        raise bad("results must be a list with one entry for each of the ten words.")
    attempt = data.get("attempt", 1)
    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
        raise bad("attempt must be a whole number, 1 or more.")
    early_finish = data.get("early_finish", False)
    if not isinstance(early_finish, bool):
        raise bad("early_finish must be true or false.")

    done = [r.get("done") for r in results]
    alias_used = [r.get("alias_used") for r in results]
    try:
        outcome = score_turn(done, alias_used, early_finish)
    except InvalidSubmission as exc:
        raise bad(str(exc))
    return done, alias_used, attempt, outcome


def submit_turn(user, match_id, turn_id, data):
    done, alias_used, attempt, outcome = _parse_submission(data)
    late = False

    with transaction.atomic():
        match = _locked_match(user, match_id)
        try:
            turn = match.turns.select_related("team").get(pk=turn_id)
        except (Turn.DoesNotExist, ValueError, DjangoValidationError):
            raise ApiError("turn_not_found", "Turn not found.", 404)

        if turn.status == T.SUBMITTED:
            return _turn_payload(turn, match)  # a repeat of a submission: return the stored result
        if turn.status == T.ABANDONED:
            raise ApiError("turn_time_expired", "That turn ran out of time and scored 0.", 409)

        now = timezone.now()
        if not submission_allowed(turn.started_at, now, attempt):
            turn.status = T.ABANDONED
            turn.submitted_at = now
            turn.save()
            _resolve_progress(match)
            late = True
        else:
            turn.results = [{"done": d, "alias_used": a} for d, a in zip(done, alias_used)]
            turn.word_points = outcome["word_points"]
            turn.bonus_points = outcome["bonus"]
            turn.status = T.SUBMITTED
            turn.submitted_at = now
            turn.save()
            _resolve_progress(match)
            match.save(update_fields=["updated_at"])
            payload = _turn_payload(turn, match)

    if late:
        raise ApiError("turn_time_expired", "That turn ran out of time and scored 0.", 409)
    return payload


def resume(user):
    cutoff = timezone.now() - RESUME_WINDOW
    ids = list(
        Match.objects.filter(_owner_q(user), status__in=ACTIVE_STATES, updated_at__gte=cutoff)
        .order_by("-updated_at")
        .values_list("id", flat=True)[:5]
    )
    for match_id in ids:
        payload = get_status(user, match_id)
        if payload["status"] in ACTIVE_VALUES:
            return payload
    raise ApiError("no_match_to_resume", "There is no unfinished match to continue.", 404)


def history(user, page=1):
    queryset = Match.objects.filter(user=user, status=S.FINISHED).order_by("-finished_at")
    total = queryset.count()
    start = (page - 1) * HISTORY_PAGE_SIZE
    results = []
    for match in queryset[start:start + HISTORY_PAGE_SIZE]:
        scores = _scores(match)
        results.append({
            "id": str(match.id),
            "finished_at": match.finished_at,
            "teams": [{"position": t.position, "name": t.name, "score": scores[t.position]} for t in match.teams.all()],
            "is_draw": match.is_draw,
            "winner_position": match.winner.position if match.winner_id else None,
        })
    return {"count": total, "page": page, "page_size": HISTORY_PAGE_SIZE, "results": results}