from __future__ import annotations
import json
from datetime import datetime, time
from typing import Any, Dict, Iterable, List, Optional, Tuple
from momento.envs.repository.base import BaseRepository

DEFAULT_TIME_FORMAT = "%H:%M"
DEFAULT_DATE_FORMAT = "%Y-%m-%d"


def _parse_time(value: str) -> Optional[time]:
    """Parse time string to time object."""
    value = value.strip()
    if not value:
        return None
    return datetime.strptime(value, DEFAULT_TIME_FORMAT).time()


def _parse_opening_hours(
    raw_hours: str | Dict[str, Any],
) -> Dict[str, List[Tuple[time, time]]]:
    """Parse opening hours JSON to structured format."""
    try:
        hours = json.loads(raw_hours) if isinstance(raw_hours, str) else raw_hours
    except json.JSONDecodeError:
        return {}

    if not hours:
        return {}

    parsed: Dict[str, List[Tuple[time, time]]] = {}
    for day, ranges in hours.items():
        if not ranges or str(ranges).lower() == "closed":
            parsed[day.lower()] = []
            continue
        day_ranges: List[Tuple[time, time]] = []
        for block in str(ranges).split(","):
            block = block.strip()
            if not block or "-" not in block:
                continue
            start_str, end_str = block.split("-", 1)
            start_time = _parse_time(start_str)
            end_time = _parse_time(end_str)
            if start_time and end_time:
                day_ranges.append((start_time, end_time))
        parsed[day.lower()] = day_ranges
    return parsed


def _time_in_ranges(target: time, ranges: Iterable[Tuple[time, time]]) -> bool:
    """Check if target time falls within any of the given ranges."""
    for start_time, end_time in ranges:
        if start_time <= target <= end_time:
            return True
    return False

def _coerce_date_str(value: Any) -> str:
    """Convert date value to string."""
    if isinstance(value, str):
        return value
    if hasattr(value, "strftime"):
        return value.strftime(DEFAULT_DATE_FORMAT)
    return str(value)


def _coerce_time_str(value: Any) -> str:
    """Convert time value to string."""
    if isinstance(value, str):
        return value
    if hasattr(value, "strftime"):
        return value.strftime(DEFAULT_TIME_FORMAT)
    return str(value)


class ReservationRepository(BaseRepository):
    def get_by_id(self, reservation_id: str) -> Optional[Dict[str, Any]]:
        """Get reservation by ID."""
        return self._fetch_one(
            "SELECT * FROM reservations WHERE id = %s", (reservation_id,)
        )

    def get_for_user(
        self, reservation_id: str, user_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get reservation only if it belongs to the specified user."""
        return self._fetch_one(
            "SELECT * FROM reservations WHERE id = %s AND user_id = %s",
            (reservation_id, user_id),
        )

    def list_by_user(
        self, user_id: str, status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List all reservations for a user, optionally filtered by status."""
        if status:
            return self._fetch_all(
                "SELECT * FROM reservations WHERE user_id = %s AND status = %s ORDER BY date DESC, time DESC",
                (user_id, status),
            )
        return self._fetch_all(
            "SELECT * FROM reservations WHERE user_id = %s ORDER BY date DESC, time DESC",
            (user_id,),
        )

    def get_reserved_party_size(
        self,
        restaurant_id: str,
        date_str: str,
        time_str: str,
        duration_minutes: int,
        exclude_reservation_id: Optional[str] = None,
    ) -> int:
        """Get total reserved party size for overlapping reservations.

        A reservation overlaps with the requested window [time_str, time_str + duration_minutes)
        if it starts before the window ends AND ends after the window starts.
        """
        if exclude_reservation_id:
            result = self._fetch_one(
                """
                SELECT COALESCE(SUM(party_size), 0) AS reserved
                FROM reservations
                WHERE restaurant_id = %s
                  AND date = %s
                  AND status = 'confirmed'
                  AND id <> %s
                  AND time < (%s::time + (%s || ' minutes')::interval)
                  AND (time + (duration_minutes || ' minutes')::interval) > %s::time
                """,
                (restaurant_id, date_str, exclude_reservation_id, time_str, duration_minutes, time_str),
            )
        else:
            result = self._fetch_one(
                """
                SELECT COALESCE(SUM(party_size), 0) AS reserved
                FROM reservations
                WHERE restaurant_id = %s
                  AND date = %s
                  AND status = 'confirmed'
                  AND time < (%s::time + (%s || ' minutes')::interval)
                  AND (time + (duration_minutes || ' minutes')::interval) > %s::time
                """,
                (restaurant_id, date_str, time_str, duration_minutes, time_str),
            )
        return int(result.get("reserved", 0)) if result else 0

    def is_restaurant_open(
        self, opening_hours: Optional[Dict[str, Any]], date_str: str, time_str: str
    ) -> Tuple[bool, str]:
        """Check if restaurant is open at the given date/time."""
        if not opening_hours:
            return False, "opening hours not available"

        date = datetime.strptime(date_str, DEFAULT_DATE_FORMAT)
        slot_time = datetime.strptime(time_str, DEFAULT_TIME_FORMAT).time()
        day_name = date.strftime("%A").lower()
        ranges = _parse_opening_hours(opening_hours).get(day_name, [])
        if not ranges:
            return False, "restaurant closed on this day"
        if not _time_in_ranges(slot_time, ranges):
            return False, "outside opening hours"
        return True, ""

    def remaining_capacity(
        self,
        restaurant_id: str,
        capacity: int,
        date_str: str,
        time_str: str,
        duration_minutes: int,
        exclude_reservation_id: Optional[str] = None,
    ) -> int:
        """Calculate remaining capacity for a time window."""
        reserved = self.get_reserved_party_size(
            restaurant_id, date_str, time_str, duration_minutes, exclude_reservation_id
        )
        return max(capacity - reserved, 0)

    def create(
        self,
        restaurant_id: str,
        user_id: str,
        date_str: str,
        time_str: str,
        party_size: int,
        duration_minutes: int,
        special_requests: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Create a new reservation."""
        return self._execute_returning(
            """
            INSERT INTO reservations (
                restaurant_id, user_id, date, time, party_size,
                duration_minutes, special_requests, status
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'confirmed')
            RETURNING *
            """,
            (
                restaurant_id,
                user_id,
                date_str,
                time_str,
                party_size,
                duration_minutes,
                special_requests,
            ),
        )

    def update(
        self,
        reservation_id: str,
        date_str: Optional[str] = None,
        time_str: Optional[str] = None,
        party_size: Optional[int] = None,
        duration_minutes: Optional[int] = None,
        special_requests: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Update an existing reservation."""
        reservation = self.get_by_id(reservation_id)
        if not reservation:
            return None

        updates = []
        params: List[Any] = []

        next_date = _coerce_date_str(date_str or reservation.get("date"))
        next_time = _coerce_time_str(time_str or reservation.get("time"))

        if date_str:
            updates.append("date = %s")
            params.append(next_date)
        if time_str:
            updates.append("time = %s")
            params.append(next_time)
        if party_size is not None:
            updates.append("party_size = %s")
            params.append(party_size)
        if duration_minutes is not None:
            updates.append("duration_minutes = %s")
            params.append(duration_minutes)
        if special_requests is not None:
            updates.append("special_requests = %s")
            params.append(special_requests)
        if status:
            updates.append("status = %s")
            params.append(status)

        if not updates:
            return reservation

        params.append(reservation_id)
        query = (
            "UPDATE reservations SET "
            + ", ".join(updates)
            + " WHERE id = %s RETURNING *"
        )
        return self._execute_returning(query, tuple(params))

    def cancel(self, reservation_id: str) -> Optional[Dict[str, Any]]:
        """Cancel a reservation."""
        return self._execute_returning(
            """
            UPDATE reservations
            SET status = 'cancelled'
            WHERE id = %s
            RETURNING *
            """,
            (reservation_id,),
        )
