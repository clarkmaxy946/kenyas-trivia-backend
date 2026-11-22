from django.db import transaction
from django.utils import timezone
from datetime import timedelta

from cards import store
from cards.service import accept_card

from .model_client import ModelUnavailable, request_cards
from .models import GenerationJob, GenerationLog, JobStatus, LogOutcome

MAX_ATTEMPTS = 3  # per card
STUCK_AFTER = timedelta(minutes=5)


def queue_round(match_id, round_number):
    """Ask for the cards of one round. Safe to call again after a failure."""
    job, created = GenerationJob.objects.get_or_create(match_id=match_id, round_number=round_number)
    if not created and job.status == JobStatus.FAILED:
        job.status = JobStatus.PENDING
        job.started_at = None
        job.finished_at = None
        job.save()
    return job


def claim_next_job():
    """Take the oldest pending job and mark it running. Returns None if there is none."""
    with transaction.atomic():
        job = (
            GenerationJob.objects.select_for_update(skip_locked=True)
            .filter(status=JobStatus.PENDING)
            .order_by("created_at")
            .first()
        )
        if job is not None:
            job.status = JobStatus.RUNNING
            job.started_at = timezone.now()
            job.save()
        return job


def reset_stuck_jobs():
    """Put jobs that were running when a worker died back in the queue."""
    cutoff = timezone.now() - STUCK_AFTER
    return GenerationJob.objects.filter(
        status=JobStatus.RUNNING, started_at__lt=cutoff
    ).update(status=JobStatus.PENDING)


def _log(job, position, attempt, outcome, problems=""):
    if isinstance(problems, list):
        problems = "; ".join(problems)
    GenerationLog.objects.create(
        job=job, position=position, attempt=attempt, outcome=outcome, problems=problems
    )


def run_job(job):
    """Generate the missing cards of a round.

    Each card gets up to MAX_ATTEMPTS tries. A card that fails is asked for again
    on its own, and cards that were already accepted are never regenerated.
    """
    match_id = job.match_id
    pending = [p for p in (1, 2) if store.get_card(match_id, job.round_number, p) is None]
    attempts = {p: 0 for p in pending}
    failed = False

    while pending and not failed:
        for p in pending:
            attempts[p] += 1

        try:
            cards = request_cards(len(pending))
        except ModelUnavailable as exc:
            cards = None
            for p in pending:
                _log(job, p, attempts[p], LogOutcome.MODEL_ERROR, str(exc))

        still_pending = []
        for index, p in enumerate(pending):
            accepted = False
            if cards is not None:
                if index < len(cards):
                    problems = accept_card(match_id, job.round_number, p, cards[index])
                else:
                    problems = ["the model returned too few cards"]
                accepted = not problems
                outcome = LogOutcome.ACCEPTED if accepted else LogOutcome.REJECTED
                _log(job, p, attempts[p], outcome, problems)

            if not accepted:
                if attempts[p] >= MAX_ATTEMPTS:
                    failed = True
                else:
                    still_pending.append(p)
        pending = still_pending

    job.status = JobStatus.FAILED if failed else JobStatus.SUCCEEDED
    job.finished_at = timezone.now()
    job.save()
    return job

def requeue_round(match_id, round_number):
    """Ask for a round's missing cards again. Cards already stored are kept."""
    job, created = GenerationJob.objects.get_or_create(match_id=match_id, round_number=round_number)
    if not created and job.status in (JobStatus.FAILED, JobStatus.SUCCEEDED):
        job.status = JobStatus.PENDING
        job.started_at = None
        job.finished_at = None
        job.save()
    return job