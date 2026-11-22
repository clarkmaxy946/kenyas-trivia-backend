import uuid
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings

from cards import store

from .jobs import claim_next_job, queue_round, run_job
from .model_client import ModelUnavailable
from .models import GenerationLog, JobStatus

HINT = "A short hint that is long enough to pass."


def good_card(prefix):
    return [{"word": f"Word {prefix}{i}", "alias": f"clue{prefix}{i}", "hint": HINT} for i in range(10)]


def bad_card(prefix):
    card = good_card(prefix)
    card[0]["hint"] = ""
    return card


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
)
class RunJobTests(TestCase):
    def setUp(self):
        cache.clear()
        self.match_id = uuid.uuid4()

    def run_with(self, results):
        queue_round(self.match_id, 1)
        job = claim_next_job()
        with patch("generations.jobs.request_cards", side_effect=results) as fake:
            run_job(job)
        job.refresh_from_db()
        return job, fake

    def test_a_good_pair_succeeds_and_the_round_is_ready(self):
        job, fake = self.run_with([[good_card("a"), good_card("b")]])
        self.assertEqual(job.status, JobStatus.SUCCEEDED)
        self.assertTrue(store.round_is_ready(self.match_id, 1))
        self.assertEqual(fake.call_count, 1)

    def test_a_bad_card_is_asked_for_again_on_its_own(self):
        job, fake = self.run_with([[good_card("a"), bad_card("b")], [good_card("c")]])
        self.assertEqual(job.status, JobStatus.SUCCEEDED)
        self.assertEqual(fake.call_count, 2)
        self.assertEqual(fake.call_args_list[1].args, (1,))  # only one card re-requested

    def test_a_model_that_is_always_down_fails_after_three_tries(self):
        job, fake = self.run_with([ModelUnavailable("down")] * 3)
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertEqual(fake.call_count, 3)
        self.assertEqual(GenerationLog.objects.filter(job=job).count(), 6)

    def test_a_card_that_keeps_failing_fails_the_job_but_keeps_the_good_card(self):
        job, _ = self.run_with([[good_card("a"), bad_card("b")], [bad_card("c")], [bad_card("d")]])
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertIsNotNone(store.get_card(self.match_id, 1, 1))
        self.assertIsNone(store.get_card(self.match_id, 1, 2))

    def test_trying_again_only_regenerates_what_is_missing(self):
        self.run_with([[good_card("a"), bad_card("b")], [bad_card("c")], [bad_card("d")]])
        queue_round(self.match_id, 1)  # "Try again"
        job = claim_next_job()
        with patch("generations.jobs.request_cards", side_effect=[[good_card("e")]]) as fake:
            run_job(job)
        job.refresh_from_db()
        self.assertEqual(job.status, JobStatus.SUCCEEDED)
        self.assertEqual(fake.call_args_list[0].args, (1,))
        self.assertTrue(store.round_is_ready(self.match_id, 1))