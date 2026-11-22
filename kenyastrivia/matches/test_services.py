from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from cards import store
from generations.models import GenerationJob, JobStatus
from kenyastrivia.errors import ApiError
from users.authentication import GuestPrincipal
from users.models import GuestSession, User

from . import services
from .models import Match, Turn

HINT = "A short hint that is long enough to pass."


def make_card(prefix):
    return [{"word": f"Word {prefix}{i}", "alias": f"clue{prefix}{i}", "hint": HINT} for i in range(10)]


def give_cards(match_id, round_number):
    store.put_card(match_id, round_number, 1, make_card(f"r{round_number}a"))
    store.put_card(match_id, round_number, 2, make_card(f"r{round_number}b"))


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
)
class ServiceTests(TestCase):
    def setUp(self):
        cache.clear()
        self.player = GuestPrincipal(GuestSession.objects.create())

    # ----- helpers -----

    def new_match(self, rounds=(1,), names=("Simba", "Chui")):
        match_id = services.create_match(self.player)["id"]
        for round_number in rounds:
            give_cards(match_id, round_number)
        services.submit_team_names(self.player, match_id, list(names))
        return match_id

    def results(self, done_count):
        return [{"done": i < done_count, "alias_used": False} for i in range(10)]

    def submit(self, match_id, turn_id, done_count, early=False, attempt=1):
        return services.submit_turn(
            self.player, match_id, turn_id,
            {"results": self.results(done_count), "attempt": attempt, "early_finish": early},
        )

    def play(self, match_id, done_count, early=False):
        started = services.start_turn(self.player, match_id)
        return self.submit(match_id, started["turn"]["id"], done_count, early)

    # ----- setup -----

    def test_create_match_queues_round_one(self):
        payload = services.create_match(self.player)
        self.assertEqual(payload["status"], "setting_up")
        job = GenerationJob.objects.get(match_id=payload["id"], round_number=1)
        self.assertEqual(job.status, JobStatus.PENDING)

    def test_names_before_the_cards_are_ready_wait_in_order(self):
        match_id = services.create_match(self.player)["id"]
        payload = services.submit_team_names(self.player, match_id, ["Simba", "Chui"])
        self.assertEqual(payload["status"], "waiting_for_cards")
        self.assertEqual([t["name"] for t in payload["teams"]], ["Simba", "Chui"])

    def test_names_when_the_cards_are_ready_start_the_match(self):
        match_id = self.new_match()
        self.assertEqual(services.get_status(self.player, match_id)["status"], "in_progress")

    def test_a_waiting_match_starts_when_the_cards_arrive(self):
        match_id = services.create_match(self.player)["id"]
        services.submit_team_names(self.player, match_id, ["Simba", "Chui"])
        give_cards(match_id, 1)
        self.assertEqual(services.get_status(self.player, match_id)["status"], "in_progress")

    def test_bad_team_names_are_refused(self):
        match_id = services.create_match(self.player)["id"]
        with self.assertRaises(ApiError) as same:
            services.submit_team_names(self.player, match_id, ["Simba", "simba"])
        self.assertEqual(same.exception.error_code, "team_names_same")
        with self.assertRaises(ApiError) as blank:
            services.submit_team_names(self.player, match_id, ["Simba", "  "])
        self.assertEqual(blank.exception.error_code, "team_name_missing")

    def test_failed_generation_means_setup_failed(self):
        match_id = services.create_match(self.player)["id"]
        GenerationJob.objects.filter(match_id=match_id, round_number=1).update(status=JobStatus.FAILED)
        self.assertEqual(services.get_status(self.player, match_id)["status"], "setup_failed")
        with self.assertRaises(ApiError) as caught:
            services.submit_team_names(self.player, match_id, ["Simba", "Chui"])
        self.assertEqual(caught.exception.error_code, "setup_failed")

    def test_retry_after_a_failure_keeps_the_names(self):
        match_id = services.create_match(self.player)["id"]
        services.submit_team_names(self.player, match_id, ["Simba", "Chui"])
        GenerationJob.objects.filter(match_id=match_id, round_number=1).update(status=JobStatus.FAILED)
        self.assertEqual(services.get_status(self.player, match_id)["status"], "setup_failed")

        payload = services.retry(self.player, match_id)
        self.assertEqual(payload["status"], "waiting_for_cards")
        self.assertEqual(len(payload["teams"]), 2)
        self.assertEqual(GenerationJob.objects.get(match_id=match_id, round_number=1).status, JobStatus.PENDING)

    def test_other_players_cannot_see_a_match(self):
        match_id = services.create_match(self.player)["id"]
        stranger = GuestPrincipal(GuestSession.objects.create())
        with self.assertRaises(ApiError) as caught:
            services.get_status(stranger, match_id)
        self.assertEqual(caught.exception.error_code, "match_not_found")

    def test_an_abandoned_setup_expires(self):
        match_id = services.create_match(self.player)["id"]
        Match.objects.filter(pk=match_id).update(updated_at=timezone.now() - timedelta(minutes=2))
        self.assertEqual(services.get_status(self.player, match_id)["status"], "abandoned")
        with self.assertRaises(ApiError) as caught:
            services.retry(self.player, match_id)
        self.assertEqual(caught.exception.error_code, "setup_expired")

    # ----- playing -----

    def test_a_full_match_has_a_winner(self):
        match_id = self.new_match(rounds=(1, 2))
        first = self.play(match_id, 10, early=True)
        self.assertEqual(first["turn"]["points"], 150)
        self.play(match_id, 6)
        self.play(match_id, 7)
        last = self.play(match_id, 5)
        match = last["match"]
        self.assertEqual(match["status"], "finished")
        self.assertEqual([t["score"] for t in match["teams"]], [220, 110])
        self.assertEqual(match["result"], {"is_draw": False, "winner_position": 1})

    def test_level_after_two_rounds_goes_to_a_tiebreaker_then_a_draw(self):
        match_id = self.new_match(rounds=(1, 2, 3))
        for _ in range(3):
            self.play(match_id, 5)
        after_round_two = self.play(match_id, 5)["match"]
        self.assertEqual(after_round_two["status"], "in_progress")
        self.assertEqual(after_round_two["next"]["round_number"], 3)
        self.play(match_id, 5)
        final = self.play(match_id, 5)["match"]
        self.assertEqual(final["status"], "finished")
        self.assertEqual(final["result"], {"is_draw": True, "winner_position": None})

    def test_tiebreaker_cards_that_fail_end_in_a_draw(self):
        match_id = self.new_match(rounds=(1, 2))
        for _ in range(3):
            self.play(match_id, 5)
        started = services.start_turn(self.player, match_id)
        GenerationJob.objects.filter(match_id=match_id, round_number=3).update(status=JobStatus.FAILED)
        payload = self.submit(match_id, started["turn"]["id"], 5)
        self.assertEqual(payload["match"]["status"], "finished")
        self.assertTrue(payload["match"]["result"]["is_draw"])

    def test_starting_a_second_turn_is_refused(self):
        match_id = self.new_match()
        services.start_turn(self.player, match_id)
        with self.assertRaises(ApiError) as caught:
            services.start_turn(self.player, match_id)
        self.assertEqual(caught.exception.error_code, "turn_already_open")

    def test_submitting_twice_scores_once(self):
        match_id = self.new_match()
        started = services.start_turn(self.player, match_id)
        first = self.submit(match_id, started["turn"]["id"], 6)
        second = self.submit(match_id, started["turn"]["id"], 6, attempt=2)
        self.assertEqual(first["turn"]["points"], 60)
        self.assertEqual(second["turn"]["points"], 60)
        self.assertEqual(second["match"]["teams"][0]["score"], 60)

    def test_late_first_attempt_abandons_the_turn(self):
        match_id = self.new_match()
        started = services.start_turn(self.player, match_id)
        turn_id = started["turn"]["id"]
        Turn.objects.filter(pk=turn_id).update(started_at=timezone.now() - timedelta(seconds=70))
        with self.assertRaises(ApiError) as caught:
            self.submit(match_id, turn_id, 6, attempt=1)
        self.assertEqual(caught.exception.error_code, "turn_time_expired")
        self.assertEqual(Turn.objects.get(pk=turn_id).status, "abandoned")

    def test_retry_within_two_minutes_is_accepted(self):
        match_id = self.new_match()
        started = services.start_turn(self.player, match_id)
        turn_id = started["turn"]["id"]
        Turn.objects.filter(pk=turn_id).update(started_at=timezone.now() - timedelta(seconds=70))
        payload = self.submit(match_id, turn_id, 6, attempt=2)
        self.assertEqual(payload["turn"]["status"], "submitted")
        self.assertEqual(payload["turn"]["points"], 60)

    def test_overdue_turn_is_abandoned_on_the_next_status_check(self):
        match_id = self.new_match()
        started = services.start_turn(self.player, match_id)
        turn_id = started["turn"]["id"]
        Turn.objects.filter(pk=turn_id).update(started_at=timezone.now() - timedelta(minutes=3))
        status = services.get_status(self.player, match_id)
        self.assertIsNone(status["open_turn"])
        self.assertEqual(status["next"]["team_position"], 2)
        self.assertEqual(Turn.objects.get(pk=turn_id).status, "abandoned")

    def test_finished_account_matches_appear_in_history(self):
        self.player = User.objects.create_user(
            username="clark_k", email="clark@example.com", password="S3cure-pass-123"
        )
        match_id = self.new_match(rounds=(1, 2))
        for done in (10, 6, 7, 5):
            self.play(match_id, done, early=(done == 10))
        result = services.history(self.player)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["results"][0]["winner_position"], 1)