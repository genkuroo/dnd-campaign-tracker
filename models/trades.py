"""PC-to-PC trading (items + gold).

A `trade_offer` is a directed, pending hand-off from one PC to another: either an
inventory item or a sum of coins. The recipient must **accept** before anything
moves (the giver can cancel while it's pending). Items/gold are validated and
transferred at accept time rather than escrowed, so an offer the giver can no
longer honour simply fails — see the app's accept route. CLAUDE.md: trades reuse
the creature engine's inventory/purse plumbing; no new ownership concept.
"""
from db import get_connection


def create_item_offer(from_creature_id, to_creature_id, item_id):
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO trade_offers (from_creature_id, to_creature_id, kind, item_id) "
            "VALUES (?, ?, 'item', ?)",
            (from_creature_id, to_creature_id, item_id),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def create_gold_offer(from_creature_id, to_creature_id, gold=0, silver=0, copper=0):
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO trade_offers "
            "(from_creature_id, to_creature_id, kind, gold, silver, copper) "
            "VALUES (?, ?, 'gold', ?, ?, ?)",
            (from_creature_id, to_creature_id,
             max(0, int(gold)), max(0, int(silver)), max(0, int(copper))),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_offer(offer_id):
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM trade_offers WHERE id = ?", (offer_id,)
        ).fetchone()
    finally:
        conn.close()


def set_status(offer_id, status):
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE trade_offers SET status = ? WHERE id = ?", (status, offer_id))
        conn.commit()
    finally:
        conn.close()


# Offers carry the counterpart creature's name + (for item offers) the item name,
# joined for display. Item name uses LEFT JOIN so a since-deleted item resolves to
# NULL (the ON DELETE CASCADE normally removes such offers, but be defensive).

def pending_incoming(creature_id):
    """Pending offers *to* this creature (awaiting accept/decline), newest first."""
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT t.*, c.name AS from_name, i.name AS item_name "
            "FROM trade_offers t "
            "JOIN creatures c ON c.id = t.from_creature_id "
            "LEFT JOIN creature_items i ON i.id = t.item_id "
            "WHERE t.to_creature_id = ? AND t.status = 'pending' "
            "ORDER BY t.id DESC",
            (creature_id,),
        ).fetchall()
    finally:
        conn.close()


def pending_outgoing(creature_id):
    """Pending offers *from* this creature (still cancellable), newest first."""
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT t.*, c.name AS to_name, i.name AS item_name "
            "FROM trade_offers t "
            "JOIN creatures c ON c.id = t.to_creature_id "
            "LEFT JOIN creature_items i ON i.id = t.item_id "
            "WHERE t.from_creature_id = ? AND t.status = 'pending' "
            "ORDER BY t.id DESC",
            (creature_id,),
        ).fetchall()
    finally:
        conn.close()
