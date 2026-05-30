import json
from typing import Any, Dict, Optional
from momento.envs.repository import ReservationRepository, RestaurantRepository
from momento.envs.tools.base import Tool, PolicyViolationError
from momento.utils.utils import is_valid_uuid


class UpdateReservation(Tool):
    @staticmethod
    def invoke(
        reservation_id: str,
        user_id: str,
        date: Optional[str] = None,
        time: Optional[str] = None,
        party_size: Optional[int] = None,
        duration_minutes: Optional[int] = None,
        special_requests: Optional[str] = None,
    ) -> str:
        if not is_valid_uuid(reservation_id):
            return f"Error: invalid reservation_id format '{reservation_id}' - must be a valid UUID"

        if party_size is not None and party_size < 1:
            raise PolicyViolationError("party_size must be at least 1")
        if duration_minutes is not None and duration_minutes < 30:
            raise PolicyViolationError("duration_minutes must be at least 30 minutes")
        if duration_minutes is not None and duration_minutes > 120:
            raise PolicyViolationError("duration_minutes cannot exceed 120 minutes")
        reservation_repo = ReservationRepository()
        restaurant_repo = RestaurantRepository()

        reservation = reservation_repo.get_for_user(reservation_id, user_id)
        if not reservation:
            raise PolicyViolationError("Reservation not found or does not belong to the user")

        if reservation.get("status") != "confirmed":
            raise PolicyViolationError(
                f"Cannot modify a reservation with status '{reservation.get('status')}'. "
                "Only confirmed reservations can be modified."
            )

        if date or time or party_size is not None or duration_minutes is not None:
            restaurant_id = str(reservation["restaurant_id"])
            restaurant = restaurant_repo.get_by_id(restaurant_id)
            if not restaurant:
                return "Error: restaurant not found"

            new_date_val = date or reservation.get("date")
            new_time_val = time or reservation.get("time")
            new_party_size = party_size if party_size is not None else reservation.get("party_size", 0)

            if hasattr(new_date_val, "strftime"):
                new_date_str = new_date_val.strftime("%Y-%m-%d")  # type: ignore
            else:
                new_date_str = str(new_date_val) if new_date_val else ""
            if hasattr(new_time_val, "strftime"):
                new_time_str = new_time_val.strftime("%H:%M")  # type: ignore
            else:
                new_time_str = str(new_time_val) if new_time_val else ""

            if not new_date_str or not new_time_str:
                return "Error: invalid date or time"

            opening_hours = restaurant.get("opening_hours")
            is_open, reason = reservation_repo.is_restaurant_open(
                opening_hours, new_date_str, new_time_str
            )
            if not is_open:
                raise PolicyViolationError(f"Restaurant is not open at the requested time: {reason}")

            new_duration = duration_minutes if duration_minutes is not None else reservation.get("duration_minutes", 90)
            capacity = restaurant.get("capacity", 0)
            remaining = reservation_repo.remaining_capacity(
                restaurant_id, capacity, new_date_str, new_time_str,
                new_duration, exclude_reservation_id=reservation_id
            )
            if new_party_size > remaining:
                raise PolicyViolationError("Insufficient capacity for the requested party size")

        updated = reservation_repo.update(
            reservation_id=reservation_id,
            date_str=date,
            time_str=time,
            party_size=party_size,
            duration_minutes=duration_minutes,
            special_requests=special_requests,
        )

        if not updated:
            return "Error: failed to update reservation"

        return json.dumps(updated, default=str)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "update_reservation",
                "description": (
                    "Update an existing restaurant reservation. "
                    "Only confirmed reservations can be modified. "
                    "Only the user who made the reservation can update it."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reservation_id": {
                            "type": "string",
                            "description": "Reservation ID (UUID format).",
                        },
                        "user_id": {
                            "type": "string",
                            "description": "User ID who owns the reservation.",
                        },
                        "date": {
                            "type": "string",
                            "description": "New reservation date in YYYY-MM-DD format.",
                        },
                        "time": {
                            "type": "string",
                            "description": "New reservation time in HH:MM 24-hour format.",
                        },
                        "party_size": {
                            "type": "integer",
                            "description": "New number of guests.",
                            "minimum": 1,
                        },
                        "duration_minutes": {
                            "type": "integer",
                            "description": "New duration of the reservation in minutes.",
                            "minimum": 30,
                            "maximum": 120,
                        },
                        "special_requests": {
                            "type": "string",
                            "description": "New special requests or notes.",
                        },
                    },
                    "required": ["reservation_id", "user_id"],
                },
            },
        }
