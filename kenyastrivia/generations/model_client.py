import random
import time

from django.conf import settings


class ModelUnavailable(Exception):
    """The model server could not be reached or gave no usable answer."""


def request_cards(count):
    """Ask the model for `count` cards, each a list of ten {word, alias, hint} entries.

    This is the stand-in. When the trained model is hosted, only this function
    changes: it will send a request to the model server instead.
    """
    delay = getattr(settings, "STAND_IN_DELAY_SECONDS", 0)
    if delay:
        time.sleep(delay)

    fail_rate = getattr(settings, "STAND_IN_FAIL_RATE", 0.0)
    if random.random() < fail_rate / 2:
        raise ModelUnavailable("The stand-in model is pretending to be down.")

    return [_make_card(fail_rate) for _ in range(count)]


def _make_card(fail_rate):
    numbers = random.sample(range(1, 100000), 10)
    card = [
        {
            "word": f"Stand-in word {n}",
            "alias": f"clue{n}",
            "hint": f"Placeholder hint for stand-in word {n}, made for testing.",
        }
        for n in numbers
    ]
    if random.random() < fail_rate / 2:
        card[random.randrange(10)]["hint"] = ""  # a broken entry, to exercise the retry rule
    return card