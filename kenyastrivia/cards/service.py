from . import store
from .rules import check_card


def accept_card(match_id, round_number, position, card):
    """Check a generated card. If it is valid, store it. Returns the list of problems."""
    problems = check_card(card, store.used_words(match_id))
    if problems:
        return problems
    store.put_card(match_id, round_number, position, card)
    store.remember_words(match_id, card)
    return []