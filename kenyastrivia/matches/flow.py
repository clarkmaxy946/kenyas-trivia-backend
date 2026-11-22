from dataclasses import dataclass
from typing import Optional

from .models import ROUND_1, ROUND_2, TIEBREAKER


@dataclass(frozen=True)
class Step:
    kind: str                                # "turn" or "finished"
    position: Optional[int] = None           # which team plays (1 or 2)
    round_number: Optional[int] = None
    winner_position: Optional[int] = None    # None on a finished step means a draw


def next_step(closed, totals, tiebreaker_points=None):
    """Work out what comes next.

    closed: set of (round_number, team_position) for turns already closed.
    totals: {1: points, 2: points}, counting every closed turn so far.
    tiebreaker_points: the part of totals that came from the tiebreaker round.
    """
    tiebreaker_points = tiebreaker_points or {1: 0, 2: 0}

    for rnd in (ROUND_1, ROUND_2):
        for pos in (1, 2):
            if (rnd, pos) not in closed:
                return Step("turn", position=pos, round_number=rnd)

    # Were the teams level after the two rounds? The tiebreaker's own points do not count here.
    after_two = {pos: totals[pos] - tiebreaker_points[pos] for pos in (1, 2)}
    if after_two[1] != after_two[2]:
        return Step("finished", winner_position=1 if after_two[1] > after_two[2] else 2)

    # Level: both teams take a tiebreaker turn before anything is decided.
    for pos in (1, 2):
        if (TIEBREAKER, pos) not in closed:
            return Step("turn", position=pos, round_number=TIEBREAKER)

    if totals[1] != totals[2]:
        return Step("finished", winner_position=1 if totals[1] > totals[2] else 2)
    return Step("finished", winner_position=None)  # still level: a draw