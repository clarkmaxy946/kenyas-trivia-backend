CARD_SIZE = 10
WORD_POINTS = 10
ALIAS_WORD_POINTS = 5
EARLY_FINISH_BONUS = 50
MAX_ALIASES_PER_CARD = 3


class InvalidSubmission(ValueError):
    """The submitted turn data breaks the rules of the game."""


def score_turn(done, alias_used, early_finish=False):
    """Score one turn.

    done and alias_used are lists of ten booleans, one per card position.
    An alias revealed on a word that was not marked done scores nothing,
    but it still counts towards the three-alias limit.
    """
    if len(done) != CARD_SIZE or len(alias_used) != CARD_SIZE:
        raise InvalidSubmission("A card has exactly ten words.")
    if not all(isinstance(x, bool) for x in list(done) + list(alias_used)):
        raise InvalidSubmission("Each position must be true or false.")
    if sum(alias_used) > MAX_ALIASES_PER_CARD:
        raise InvalidSubmission("At most three aliases can be used on a card.")

    word_points = 0
    for was_done, used_alias in zip(done, alias_used):
        if was_done:
            word_points += ALIAS_WORD_POINTS if used_alias else WORD_POINTS

    bonus = 0
    if early_finish and all(done) and not any(alias_used):
        bonus = EARLY_FINISH_BONUS

    return {"word_points": word_points, "bonus": bonus, "total": word_points + bonus}