from django.core.cache import cache

from .rules import normalize

CARD_TTL = 3 * 60 * 60  # 3 hours


def _card_key(match_id, round_number, position):
    return f"card:{match_id}:{round_number}:{position}"


def _words_key(match_id):
    return f"words:{match_id}"


def put_card(match_id, round_number, position, card):
    cache.set(_card_key(match_id, round_number, position), card, CARD_TTL)


def get_card(match_id, round_number, position):
    return cache.get(_card_key(match_id, round_number, position))


def round_is_ready(match_id, round_number):
    return all(get_card(match_id, round_number, p) is not None for p in (1, 2))


def used_words(match_id):
    return set(cache.get(_words_key(match_id), []))


def remember_words(match_id, card):
    words = used_words(match_id) | {normalize(entry["word"]) for entry in card}
    cache.set(_words_key(match_id), sorted(words), CARD_TTL)


def forget_match(match_id):
    keys = [_words_key(match_id)]
    keys += [_card_key(match_id, r, p) for r in (1, 2, 3) for p in (1, 2)]
    cache.delete_many(keys)