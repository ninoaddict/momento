from __future__ import annotations
import os
from datetime import date as _date
from typing import Any, Dict, List, Optional, Tuple
import psycopg2
from psycopg2.extras import RealDictCursor


_scenario_date: Optional[str] = None
def set_scenario_date(current_date: Optional[str]) -> None:
    global _scenario_date
    _scenario_date = current_date


def get_scenario_date() -> str:
    return _scenario_date if _scenario_date else _date.today().isoformat()


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


def get_recall_connection():
    return psycopg2.connect(
        host=os.getenv("PGHOST", "localhost"),
        port=int(os.getenv("PGPORT", "5433")),
        user=os.getenv("PG_RECALL_USER", "recall_reader"),
        password=os.getenv("PG_RECALL_PASSWORD", "recall_reader"),
        dbname=os.getenv("PGDATABASE", "restaurant"),
        cursor_factory=RealDictCursor,
    )


class BaseRepository:
    def _fetch_all(
        self, query: str, params: Tuple[Any, ...] = ()
    ) -> List[Dict[str, Any]]:
        """Execute a query and return all results as list of dictionaries."""
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                return [dict(row) for row in cursor.fetchall()]

    def _fetch_one(
        self, query: str, params: Tuple[Any, ...] = ()
    ) -> Optional[Dict[str, Any]]:
        """Execute a query and return a single result as dictionary."""
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                row = cursor.fetchone()
                return dict(row) if row else None

    def _execute(self, query: str, params: Tuple[Any, ...] = ()) -> None:
        """Execute a query without returning results."""
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
            conn.commit()

    def _execute_returning(
        self, query: str, params: Tuple[Any, ...] = ()
    ) -> Optional[Dict[str, Any]]:
        """Execute a query and return the affected row."""
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                row = cursor.fetchone()
                conn.commit()
                return dict(row) if row else None
