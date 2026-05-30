from __future__ import annotations

import hashlib
import json
import re
import uuid as _uuid
from typing import Any, Dict, Optional
import os
import psycopg2
from psycopg2.extras import RealDictCursor

def get_connection():
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return psycopg2.connect(database_url, cursor_factory=RealDictCursor)
    return psycopg2.connect(
        host=os.getenv("PGHOST", "localhost"),
        port=int(os.getenv("PGPORT", "5433")),
        user=os.getenv("PGUSER", "restaurant"),
        password=os.getenv("PGPASSWORD", "restaurant"),
        dbname=os.getenv("PGDATABASE", "restaurant"),
        cursor_factory=RealDictCursor,
    )


EXCLUDED_FIELDS = {"id", "created_at", "updated_at"}


def is_valid_uuid(value: str) -> bool:
    """Return True if value is a valid UUID string."""
    try:
        _uuid.UUID(value)
        return True
    except (ValueError, AttributeError):
        return False


def _serialize_row(row: Dict[str, Any], excluded: set) -> str:
    filtered = {k: v for k, v in sorted(row.items()) if k not in excluded}
    return json.dumps(filtered, sort_keys=True, default=str)


def compute_table_hash(
    table_name: str,
    order_by: str = "id",
    where_clause: Optional[str] = None,
    where_params: Optional[tuple] = None,
    excluded_fields: Optional[set] = None,
) -> str:
    excluded = excluded_fields if excluded_fields is not None else EXCLUDED_FIELDS

    query = f"SELECT * FROM {table_name}"
    if where_clause:
        query += f" WHERE {where_clause}"
    query += f" ORDER BY {order_by}"

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(query, where_params)
            rows = cursor.fetchall()
    finally:
        conn.close()

    if not rows:
        return hashlib.md5(b"").hexdigest()

    serialized = "".join(_serialize_row(dict(row), excluded) for row in rows)
    return hashlib.md5(serialized.encode("utf-8")).hexdigest()


def compute_user_orders_hash(user_id: str) -> str:
    return compute_table_hash(
        table_name="orders",
        order_by="restaurant_id, fulfillment, status, total_price, created_at",
        where_clause="user_id = %s",
        where_params=(user_id,),
        excluded_fields={"id", "created_at", "updated_at", "special_instructions", "delivery_address"},
    )


def compute_user_reservations_hash(user_id: str) -> str:
    return compute_table_hash(
        table_name="reservations",
        order_by="restaurant_id, date, time, party_size, status",
        where_clause="user_id = %s",
        where_params=(user_id,),
        excluded_fields={"id", "created_at", "special_requests"},
    )


def compute_user_order_items_hash(user_id: str) -> str:
    query = """
        SELECT oi.order_id, oi.menu_item_id, oi.name, oi.price, oi.quantity
        FROM order_items oi
        JOIN orders o ON oi.order_id = o.id
        WHERE o.user_id = %s
        ORDER BY oi.menu_item_id, oi.name, oi.quantity, o.created_at
    """

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(query, (user_id,))
            rows = cursor.fetchall()
    finally:
        conn.close()

    if not rows:
        return hashlib.md5(b"").hexdigest()

    excluded = {"id", "order_id"}
    serialized = "".join(_serialize_row(dict(row), excluded) for row in rows)
    return hashlib.md5(serialized.encode("utf-8")).hexdigest()


def compute_user_memberships_hash(user_id: str) -> str:
    return compute_table_hash(
        table_name="memberships",
        order_by="tier, status, start_date",
        where_clause="user_id = %s",
        where_params=(user_id,),
        excluded_fields={"id", "created_at", "updated_at"},
    )


def compute_all_user_hashes(user_id: str) -> Dict[str, str]:
    return {
        "orders_hashed": compute_user_orders_hash(user_id),
        "reservations_hashed": compute_user_reservations_hash(user_id),
        "order_items_hashed": compute_user_order_items_hash(user_id),
        "memberships_hashed": compute_user_memberships_hash(user_id),
    }


def compare_hashes(expected: Dict[str, str], actual: Dict[str, str]) -> Dict[str, bool]:
    results = {}
    for key in ["orders_hashed", "reservations_hashed", "order_items_hashed", "memberships_hashed"]:
        expected_val = expected.get(key, "")
        actual_val = actual.get(key, "")
        if not expected_val:
            results[key] = True
        else:
            results[key] = expected_val == actual_val
    return results
  
def strip_thinking(content: str) -> str:
    return re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()