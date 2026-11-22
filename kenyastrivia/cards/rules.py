import re

CARD_SIZE = 10
MIN_HINT_LENGTH = 15
MAX_HINT_LENGTH = 250
MAX_WORD_LENGTH = 60
MAX_ALIAS_LENGTH = 30


def normalize(text):
    """Lower-case and tidy spaces, so 'Tom  Mboya' and 'tom mboya' count as the same."""
    return re.sub(r"\s+", " ", text.strip().casefold())


def check_card(card, used_words=frozenset()):
    """Return a list of problems. An empty list means the card is valid.

    card: a list of ten {"word", "alias", "hint"} entries.
    used_words: normalised words already accepted earlier in the same match.
    """
    if not isinstance(card, list) or len(card) != CARD_SIZE:
        return [f"a card must have exactly {CARD_SIZE} entries"]

    problems = []
    seen = set()
    for number, entry in enumerate(card, start=1):
        values = [entry.get(k) if isinstance(entry, dict) else None for k in ("word", "alias", "hint")]
        word, alias, hint = values
        if not all(isinstance(v, str) and v.strip() for v in values):
            problems.append(f"entry {number}: word, alias and hint must all be filled in")
            continue

        norm_word = normalize(word)
        norm_alias = normalize(alias)

        if len(word.strip()) > MAX_WORD_LENGTH:
            problems.append(f"entry {number}: word is too long")
        if " " in norm_alias:
            problems.append(f"entry {number}: alias must be a single word")
        elif len(norm_alias) > MAX_ALIAS_LENGTH:
            problems.append(f"entry {number}: alias is too long")
        elif norm_alias == norm_word or norm_alias in norm_word.split(" "):
            problems.append(f"entry {number}: alias gives the word away")
        if not MIN_HINT_LENGTH <= len(hint.strip()) <= MAX_HINT_LENGTH:
            problems.append(f"entry {number}: hint length is not sensible")

        if norm_word in seen:
            problems.append(f"entry {number}: word repeats earlier in this card")
        elif norm_word in used_words:
            problems.append(f"entry {number}: word was already used in this match")
        seen.add(norm_word)

    return problems