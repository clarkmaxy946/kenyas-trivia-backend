from django.test import SimpleTestCase, override_settings
from django.core.cache import cache

from . import store
from .rules import check_card
from .service import accept_card

HINT = "A short hint that is long enough to pass."


def make_card(prefix):
    return [
        {"word": f"Word {prefix}{i}", "alias": f"clue{prefix}{i}", "hint": HINT}
        for i in range(10)
    ]


class CheckCardTests(SimpleTestCase):
    def test_a_good_card_has_no_problems(self):
        self.assertEqual(check_card(make_card("a")), [])

    def test_wrong_size_is_rejected(self):
        self.assertTrue(check_card(make_card("a")[:9]))

    def test_multi_word_alias_is_rejected(self):
        card = make_card("a")
        card[0]["alias"] = "two words"
        self.assertTrue(check_card(card))

    def test_alias_equal_to_the_word_is_rejected(self):
        card = make_card("a")
        card[0] = {"word": "Mboya", "alias": "mboya", "hint": HINT}
        self.assertTrue(check_card(card))

    def test_alias_equal_to_part_of_the_word_is_rejected(self):
        card = make_card("a")
        card[0] = {"word": "Jomo Kenyatta", "alias": "Kenyatta", "hint": HINT}
        self.assertTrue(check_card(card))

    def test_missing_hint_is_rejected(self):
        card = make_card("a")
        card[0]["hint"] = ""
        self.assertTrue(check_card(card))

    def test_repeat_within_the_card_is_rejected(self):
        card = make_card("a")
        card[1]["word"] = card[0]["word"].upper()
        self.assertTrue(check_card(card))

    def test_word_used_earlier_in_the_match_is_rejected(self):
        card = make_card("a")
        self.assertTrue(check_card(card, used_words={"word a0"}))


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
)
class StoreTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_a_valid_card_is_stored_and_the_round_becomes_ready(self):
        self.assertEqual(accept_card("m1", 1, 1, make_card("a")), [])
        self.assertFalse(store.round_is_ready("m1", 1))
        self.assertEqual(accept_card("m1", 1, 2, make_card("b")), [])
        self.assertTrue(store.round_is_ready("m1", 1))

    def test_an_invalid_card_is_not_stored(self):
        bad = make_card("a")
        bad[0]["hint"] = ""
        self.assertTrue(accept_card("m1", 1, 1, bad))
        self.assertIsNone(store.get_card("m1", 1, 1))

    def test_a_word_cannot_come_back_in_a_later_round(self):
        accept_card("m1", 1, 1, make_card("a"))
        again = make_card("c")
        again[0]["word"] = "word a0"
        self.assertTrue(accept_card("m1", 2, 1, again))

    def test_forget_match_clears_everything(self):
        accept_card("m1", 1, 1, make_card("a"))
        store.forget_match("m1")
        self.assertIsNone(store.get_card("m1", 1, 1))
        self.assertEqual(store.used_words("m1"), set())