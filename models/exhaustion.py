"""Exhaustion — the 5e six-level fatigue track, as a **loose display only**.

Each level stacks a worse penalty (cumulative), and at level 6 a character would
die. By design this app **only displays** the level and what each step means — it
never auto-applies the penalties (no halved speed/HP) and never kills a character
at level 6. It's a reminder/tracker for the table, not an enforced rule.
"""
from db import get_connection

MAX_EXHAUSTION = 6

# Effect at each level (index = level). Cumulative: a level-3 creature also has the
# level 1–2 effects. (The 5e 2014 track.)
EXHAUSTION_EFFECTS = [
    "",                                                  # 0 — none
    "Disadvantage on ability checks",                    # 1
    "Speed halved",                                      # 2
    "Disadvantage on attack rolls and saving throws",    # 3
    "Hit point maximum halved",                          # 4
    "Speed reduced to 0",                                # 5
    "Death",                                             # 6
]


def clamp(level):
    return max(0, min(MAX_EXHAUSTION, int(level or 0)))


def exhaustion_effects(level):
    """[(level, effect)] for every step active at `level` (1..level), cumulative.
    Empty at level 0."""
    return [(i, EXHAUSTION_EFFECTS[i]) for i in range(1, clamp(level) + 1)]


def set_exhaustion(creature_id, level):
    """Set a creature's exhaustion level, clamped to 0..6."""
    conn = get_connection()
    try:
        conn.execute("UPDATE creatures SET exhaustion = ? WHERE id = ?",
                     (clamp(level), creature_id))
        conn.commit()
    finally:
        conn.close()
