from datetime import datetime, timedelta, timezone as dt_timezone
from types import SimpleNamespace

from django.test import SimpleTestCase

from kenyastrivia.errors import ApiError

from .flow import next_step
from .scoring import InvalidSubmission, score_turn
from .states import transition
from .timing import submission_allowed, turn_is_overdue

ALL = [True] * 10
NONE = [False] * 10


class ScoreTurnTests(SimpleTestCase):
    def test_perfect_early_finish_is_150(self):
        self.assertEqual(score_turn(ALL, NONE, early_finish=True)["total"], 150)

    def test_all_done_but_not_early_has_no_bonus(self):
        self.assertEqual(score_turn(ALL, NONE, early_finish=False)["total"], 100)

    def test_one_alias_halves_that_word_and_removes_the_bonus(self):
        alias = [True] + [False] * 9
        self.assertEqual(score_turn(ALL, alias, early_finish=True)["total"], 95)

    def test_alias_on_an_unmarked_word_scores_zero(self):
        done = [True] * 3 + [False] * 7
        alias = [False] * 3 + [True] + [False] * 6
        self.assertEqual(score_turn(done, alias)["total"], 30)

    def test_nothing_done_scores_zero(self):
        self.assertEqual(score_turn(NONE, NONE)["total"], 0)

    def test_four_aliases_is_rejected(self):
        with self.assertRaises(InvalidSubmission):
            score_turn(ALL, [True] * 4 + [False] * 6)

    def test_wrong_length_is_rejected(self):
        with self.assertRaises(InvalidSubmission):
            score_turn([True] * 9, [False] * 9)


class FlowTests(SimpleTestCase):
    def test_game_starts_with_team_one_in_round_one(self):
        step = next_step(set(), {1: 0, 2: 0})
        self.assertEqual((step.kind, step.position, step.round_number), ("turn", 1, 1))

    def test_teams_alternate_and_round_two_starts_with_team_one(self):
        step = next_step({(1, 1)}, {1: 50, 2: 0})
        self.assertEqual((step.position, step.round_number), (2, 1))
        step = next_step({(1, 1), (1, 2)}, {1: 50, 2: 40})
        self.assertEqual((step.position, step.round_number), (1, 2))

    def test_higher_total_wins_after_two_rounds(self):
        closed = {(1, 1), (1, 2), (2, 1), (2, 2)}
        step = next_step(closed, {1: 80, 2: 120})
        self.assertEqual((step.kind, step.winner_position), ("finished", 2))

    def test_level_after_two_rounds_goes_to_the_tiebreaker(self):
        closed = {(1, 1), (1, 2), (2, 1), (2, 2)}
        step = next_step(closed, {1: 100, 2: 100})
        self.assertEqual((step.kind, step.position, step.round_number), ("turn", 1, 3))

    def test_tiebreaker_can_decide_the_match(self):
        closed = {(1, 1), (1, 2), (2, 1), (2, 2), (3, 1), (3, 2)}
        # Level on 100 after two rounds; the tiebreaker gave 30 and 10.
        step = next_step(closed, {1: 130, 2: 110}, {1: 30, 2: 10})
        self.assertEqual((step.kind, step.winner_position), ("finished", 1))

    def test_half_played_tiebreaker_waits_for_the_other_team(self):
        closed = {(1, 1), (1, 2), (2, 1), (2, 2), (3, 1)}
        step = next_step(closed, {1: 150, 2: 100}, {1: 50, 2: 0})
        self.assertEqual((step.kind, step.position, step.round_number), ("turn", 2, 3))

    def test_still_level_after_the_tiebreaker_is_a_draw(self):
        closed = {(1, 1), (1, 2), (2, 1), (2, 2), (3, 1), (3, 2)}
        step = next_step(closed, {1: 120, 2: 120}, {1: 20, 2: 20})
        self.assertEqual((step.kind, step.winner_position), ("finished", None))


class TimingTests(SimpleTestCase):
    start = datetime(2026, 10, 10, 12, 0, 0, tzinfo=dt_timezone.utc)

    def at(self, seconds):
        return self.start + timedelta(seconds=seconds)

    def test_first_attempt_gets_55_seconds_plus_grace(self):
        self.assertTrue(submission_allowed(self.start, self.at(64), attempt=1))
        self.assertFalse(submission_allowed(self.start, self.at(66), attempt=1))

    def test_retries_get_two_minutes(self):
        self.assertTrue(submission_allowed(self.start, self.at(100), attempt=2))
        self.assertFalse(submission_allowed(self.start, self.at(125), attempt=2))

    def test_overdue_after_two_minutes(self):
        self.assertFalse(turn_is_overdue(self.start, self.at(119)))
        self.assertTrue(turn_is_overdue(self.start, self.at(121)))


class StateTests(SimpleTestCase):
    def make(self, status):
        return SimpleNamespace(status=status, finished_at=None, save=lambda: None)

    def test_allowed_move(self):
        match = self.make("setting_up")
        transition(match, "in_progress")
        self.assertEqual(match.status, "in_progress")

    def test_finishing_sets_the_finish_time(self):
        match = self.make("in_progress")
        transition(match, "finished")
        self.assertIsNotNone(match.finished_at)

    def test_illegal_move_is_refused(self):
        match = self.make("finished")
        with self.assertRaises(ApiError) as caught:
            transition(match, "in_progress")
        self.assertEqual(caught.exception.error_code, "wrong_state")