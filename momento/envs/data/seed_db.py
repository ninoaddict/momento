from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable
import random
import psycopg2
from psycopg2.extras import execute_values
from momento.envs.services.embedding import build_session_text, embed_texts
from momento.types import ScenarioSeedData, SessionSeed
from momento.utils import get_connection

random.seed(42)


DATA_DIR = Path(__file__).resolve().parent
RESTAURANTS_PATH = DATA_DIR / "restaurants.json"
MENUS_PATH = DATA_DIR / "restaurant_menus.json"
USER_PATH = DATA_DIR / "users.json"

DB_DIR = Path(__file__).resolve().parent.parent.parent / "db"
SCHEMA_PATH = DB_DIR / "schema.sql"
SEEDS_DIR = DB_DIR / "seeds"


TRANSACTIONAL_TABLES = ("order_items", "orders", "reservations", "memberships")


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _coerce_opening_hours(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {}
    return value


def reset_database(tables: Iterable[str] | None = None):
    target = tuple(tables) if tables is not None else TRANSACTIONAL_TABLES
    with get_connection() as conn:
        with conn.cursor() as cursor:
            for table in target:
                cursor.execute(f"DELETE FROM {table}")
        conn.commit()


def apply_sql_script(path: Path):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            with path.open("r", encoding="utf-8") as handle:
                sql = handle.read()
                cursor.execute(sql)
        conn.commit()


def apply_sql_directory(directory: Path) -> None:
    if not directory.exists():
        return
    files = sorted(
        directory.glob("*.sql"),
        key=lambda p: p.name,
    )
    for f in files:
        apply_sql_script(f)


def clear_sessions() -> None:
    """Wipe ALL sessions and session_messages."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM session_messages")
            cursor.execute("DELETE FROM sessions")
        conn.commit()


def seed_sessions(sessions: list[SessionSeed]) -> None:
    """Replace all sessions with the provided list (with fresh embeddings)."""
    clear_sessions()
    if not sessions:
        return

    texts = [build_session_text(s.summary, s.extracted_facts) for s in sessions]
    embeddings = embed_texts(texts)

    session_rows = [
        (
            s.id,
            s.user_id,
            s.started_at,
            s.ended_at,
            s.summary,
            json.dumps(s.extracted_facts or {}),
            "[" + ",".join(f"{x:.8f}" for x in emb) + "]",
        )
        for s, emb in zip(sessions, embeddings)
    ]

    message_rows = [
        (
            s.id,
            msg.role,
            json.dumps(msg.content),
            msg.seq,
        )
        for s in sessions
        for msg in s.messages
    ]

    with get_connection() as conn:
        with conn.cursor() as cursor:
            execute_values(
                cursor,
                """
                INSERT INTO sessions (id, user_id, started_at, ended_at, summary, extracted_facts, embedding)
                VALUES %s
                """,
                session_rows,
            )
            if message_rows:
                execute_values(
                    cursor,
                    """
                    INSERT INTO session_messages (session_id, role, content, seq)
                    VALUES %s
                    """,
                    message_rows,
                )
        conn.commit()


_ORDER_COLS = (
    "id", "user_id", "restaurant_id", "fulfillment", "status",
    "total_price", "currency", "delivery_provider_name",
    "delivery_address", "special_instructions",
    "created_at", "updated_at",
)
_ORDER_ITEM_COLS = (
    "id", "order_id", "menu_item_id", "name", "price", "quantity", "notes",
)
_RESERVATION_COLS = (
    "id", "user_id", "restaurant_id", "date", "time",
    "party_size", "special_requests", "duration_minutes", "status", "created_at",
)
_MEMBERSHIP_COLS = (
    "id", "user_id", "tier", "status",
    "start_date", "end_date", "created_at", "updated_at",
)


def _rows_for(rows: list[dict], cols: tuple[str, ...]) -> list[tuple]:
    return [tuple(r.get(c) for c in cols) for r in rows]


def _insert_rows(cursor, table: str, cols: tuple[str, ...], rows: list[dict]) -> None:
    if not rows:
        return
    col_sql = ", ".join(cols)
    execute_values(
        cursor,
        f"INSERT INTO {table} ({col_sql}) VALUES %s",
        _rows_for(rows, cols),
    )


def apply_scenario_seed_data(seed_data: ScenarioSeedData) -> None:
    """Apply per-trial scenario seed rows. Memberships replace per-user to allow tier overrides."""
    if seed_data.is_empty():
        return

    with get_connection() as conn:
        with conn.cursor() as cursor:
            # Replace memberships for users mentioned in scenario seed (overrides basic-tier defaults).
            user_ids = {m.get("user_id") for m in seed_data.memberships if m.get("user_id")}
            if user_ids:
                cursor.execute(
                    "DELETE FROM memberships WHERE user_id = ANY(%s)",
                    (list(user_ids),),
                )

            _insert_rows(cursor, "memberships", _MEMBERSHIP_COLS, seed_data.memberships)
            _insert_rows(cursor, "reservations", _RESERVATION_COLS, seed_data.reservations)
            _insert_rows(cursor, "orders", _ORDER_COLS, seed_data.orders)
            _insert_rows(cursor, "order_items", _ORDER_ITEM_COLS, seed_data.order_items)
        conn.commit()


# Global setup (once per environment lifecycle)
def seed_database(schema_path: Path = SCHEMA_PATH):
    """Apply schema and seed catalog tables (restaurants, menus, users, payment methods).
    """
    restaurants = _load_json(RESTAURANTS_PATH)
    menus = _load_json(MENUS_PATH)
    users = _load_json(USER_PATH)

    apply_sql_script(schema_path)

    with get_connection() as conn:
        with conn.cursor() as cursor:
            user_rows = []
            payment_method_rows = []
            for user_key in users:
                user = users.get(user_key)
                user_rows.append(
                    (
                        user_key,
                        user.get("name").get("first_name"),
                        user.get("name").get("last_name"),
                        user.get("email"),
                        user.get("gender"),
                        user.get("address").get("address1"),
                        user.get("address").get("address2"),
                        user.get("address").get("city"),
                        user.get("address").get("state"),
                        user.get("address").get("country"),
                        user.get("address").get("zip"),
                        user.get("address").get("phone"),
                    )
                )
            for user_key in users:
                user = users.get(user_key)
                for pm in user.get("payment_methods", []):
                    payment_method_rows.append(
                        (
                            pm.get("id"),
                            user_key,
                            pm.get("type"),
                            json.dumps(pm.get("details", {})),
                        )
                    )

            execute_values(
                cursor,
                """
                INSERT INTO users (
                    id, first_name, last_name, email, gender, address1, address2,
                    city, state, country, zip, phone
                ) VALUES %s
                ON CONFLICT (id) DO NOTHING
                """,
                user_rows,
            )

            if payment_method_rows:
                execute_values(
                    cursor,
                    """
                    INSERT INTO payment_methods (
                        id, user_id, type, details
                    ) VALUES %s
                    ON CONFLICT (id) DO NOTHING
                    """,
                    payment_method_rows,
                )

            restaurant_rows = []
            for item in restaurants:
                restaurant_rows.append(
                    (
                        item.get("id"),
                        item.get("name"),
                        item.get("description"),
                        item.get("address"),
                        item.get("city"),
                        item.get("country"),
                        item.get("lat"),
                        item.get("lon"),
                        [c.lower() for c in item.get("cuisines", [])],
                        item.get("price_range_lower"),
                        item.get("price_range_upper"),
                        json.dumps(_coerce_opening_hours(item.get("opening_hours"))),
                        item.get("capacity", random.randint(20, 100)),
                        item.get("amenities", []),
                        item.get("image_url", []),
                    )
                )

            execute_values(
                cursor,
                """
                INSERT INTO restaurants (
                    id, name, description, address, city, country, lat, lon, cuisines,
                    price_range_lower, price_range_upper, opening_hours, capacity, amenities, image_url
                ) VALUES %s
                ON CONFLICT (id) DO NOTHING
                """,
                restaurant_rows,
            )

            menu_rows = []
            for item in menus:
                menu_rows.append(
                    (
                        item.get("id"),
                        item.get("restaurant_id"),
                        item.get("name"),
                        item.get("description"),
                        item.get("categories", []),
                        [c.lower() for c in item.get("cuisines", [])],
                        item.get("price", random.uniform(1.0, 50.0)),
                        item.get("image_url", []),
                    )
                )

            execute_values(
                cursor,
                """
                INSERT INTO menu_items (
                    id, restaurant_id, name, description, categories,
                    cuisines, price, image_url
                ) VALUES %s
                ON CONFLICT (id) DO NOTHING
                """,
                menu_rows,
            )
        conn.commit()
    print("Database seeded successfully.")


if __name__ == "__main__":
    seed_database()
