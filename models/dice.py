"""The dice engine — parse and roll D&D dice expressions.

Pure functions, no DB. Supports the standard polyhedral set plus arbitrary
expressions like `2d6+3`, `1d20 + 1d4 - 1`, and d20 checks with
advantage/disadvantage. Persistence (the roll log) lives in models/roll_log.py.
"""
import random
import re

MAX_DICE = 100      # guard against `9999d6` style abuse
MAX_SIDES = 1000

# A signed term is either NdM (dice) or a flat number.
_TERM_RE = re.compile(r"([+-]?)(?:(\d*)d(\d+)|(\d+))")


class DiceError(ValueError):
    """Raised for an unparseable or out-of-bounds dice expression."""


def roll_expression(expr):
    """Roll a dice expression, returning {expression, total, detail}.

    `detail` is a human-readable breakdown, e.g. '2d6 (4+3) + 3'.
    """
    s = (expr or "").lower().replace(" ", "")
    if not s:
        raise DiceError("Enter a dice expression, like 2d6+3.")
    if not re.fullmatch(r"[0-9d+\-]+", s):
        raise DiceError(f"'{expr}' isn't a valid dice expression.")

    pos = 0
    total = 0
    pieces = []
    for i, m in enumerate(_TERM_RE.finditer(s)):
        if m.start() != pos:                       # a gap means junk we didn't parse
            raise DiceError(f"'{expr}' isn't a valid dice expression.")
        pos = m.end()
        sign_str, count_str, sides_str, flat_str = m.groups()
        sign = -1 if sign_str == "-" else 1
        op = "-" if sign < 0 else "+"

        if flat_str is not None:                   # flat modifier
            value = int(flat_str)
            total += sign * value
            pieces.append((op, str(value)) if i else (op if sign < 0 else "", str(value)))
        else:                                      # NdM dice term
            count = int(count_str) if count_str else 1
            sides = int(sides_str)
            if not (1 <= count <= MAX_DICE):
                raise DiceError(f"Number of dice must be 1–{MAX_DICE}.")
            if not (1 <= sides <= MAX_SIDES):
                raise DiceError(f"Die must have 1–{MAX_SIDES} sides.")
            rolls = [random.randint(1, sides) for _ in range(count)]
            total += sign * sum(rolls)
            label = f"{count}d{sides} ({'+'.join(map(str, rolls))})"
            pieces.append((op, label) if i else (op if sign < 0 else "", label))

    if pos != len(s):
        raise DiceError(f"'{expr}' isn't a valid dice expression.")

    detail = "".join(
        f" {op} {text}" if op else text for op, text in pieces
    ).strip()
    return {"expression": s, "total": total, "detail": detail}


def roll_check(modifier=0, mode="normal"):
    """Roll a d20 check/saving throw: d20 + modifier.

    `mode` is 'normal', 'advantage' (roll two, keep highest) or 'disadvantage'
    (keep lowest). Returns the same {expression, total, detail} shape.
    """
    modifier = int(modifier)
    if mode == "advantage":
        a, b = random.randint(1, 20), random.randint(1, 20)
        kept = max(a, b)
        roll_text = f"d20 adv ({a},{b}→{kept})"
        expr_tag = "d20 (advantage)"
    elif mode == "disadvantage":
        a, b = random.randint(1, 20), random.randint(1, 20)
        kept = min(a, b)
        roll_text = f"d20 dis ({a},{b}→{kept})"
        expr_tag = "d20 (disadvantage)"
    else:
        kept = random.randint(1, 20)
        roll_text = f"d20 ({kept})"
        expr_tag = "d20"

    detail = roll_text
    if modifier:
        detail += f" {'+' if modifier > 0 else '-'} {abs(modifier)}"
    total = kept + modifier
    return {"expression": expr_tag, "total": total, "detail": detail}
