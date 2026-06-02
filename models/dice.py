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


# A d20 check optionally carrying a flat modifier: 'd20', '1d20', 'd20+3', 'd20-1'.
_D20_CHECK_RE = re.compile(r"^(\d*)d20([+-]\d+)?$")


def parse_and_roll(text):
    """Roll a typed expression, dispatching on an optional adv/dis suffix.

    'd20 adv', 'd20+3 disadvantage' -> a d20 check with advantage/disadvantage.
    Anything else -> a plain expression ('2d6+3'). One entry point so every roll
    (quick buttons, free text, sheet checks) goes through a single path.
    """
    s = (text or "").strip().lower()
    if not s:
        raise DiceError("Enter a dice expression, like 2d6+3.")

    m = re.match(r"^(.*?)\s*(adv|advantage|dis|disadvantage)$", s)
    if m:
        lead = m.group(1).replace(" ", "")
        mode = "advantage" if m.group(2).startswith("adv") else "disadvantage"
        check = _D20_CHECK_RE.match(lead)
        if not check or (check.group(1) not in ("", "1")):
            raise DiceError("Advantage/disadvantage only applies to a single d20 "
                            "(e.g. 'd20 adv' or 'd20+3 dis').")
        modifier = int(check.group(2)) if check.group(2) else 0
        return roll_check(modifier, mode)

    return roll_expression(s)


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
