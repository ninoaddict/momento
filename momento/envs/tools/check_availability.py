import json
from typing import Any, Dict, Optional
from momento.envs.repository import ReservationRepository, RestaurantRepository
from momento.envs.tools.base import PolicyViolationError, Tool
from momento.utils.utils import is_valid_uuid


class CheckRestaurantAvailability(Tool):
    @staticmethod
    def invoke(
        restaurant_id: str,
        date: str,
        time: str,
        party_size: int,
        duration_minutes: int,
        exclude_reservation_id: Optional[str] = None,
    ) -> str:
        if not is_valid_uuid(restaurant_id):
            return f"Error: invalid restaurant_id format '{restaurant_id}' - must be a valid UUID"
        if exclude_reservation_id and not is_valid_uuid(exclude_reservation_id):
            return f"Error: invalid exclude_reservation_id format '{exclude_reservation_id}' - must be a valid UUID"

        if party_size < 1:
            raise PolicyViolationError("party_size must be at least 1")
        if duration_minutes < 30:
            raise PolicyViolationError("duration_minutes must be at least 30 minutes")
        if duration_minutes > 120:
            raise PolicyViolationError("duration_minutes cannot exceed 120 minutes")

        restaurant_repo = RestaurantRepository()
        reservation_repo = ReservationRepository()

        restaurant = restaurant_repo.get_by_id(restaurant_id)
        if not restaurant:
            return "Error: restaurant not found"

        opening_hours = restaurant.get("opening_hours")
        is_open, reason = reservation_repo.is_restaurant_open(opening_hours, date, time)
        if not is_open:
            return json.dumps(
                {
                    "restaurant_id": restaurant_id,
                    "date": date,
                    "time": time,
                    "party_size": party_size,
                    "duration_minutes": duration_minutes,
                    "available": False,
                    "reason": reason,
                }
            )

        capacity = restaurant.get("capacity", 0)
        remaining = reservation_repo.remaining_capacity(
            restaurant_id,
            capacity,
            date,
            time,
            duration_minutes,
            exclude_reservation_id,
        )
        if party_size > remaining:
            return json.dumps(
                {
                    "restaurant_id": restaurant_id,
                    "date": date,
                    "time": time,
                    "party_size": party_size,
                    "duration_minutes": duration_minutes,
                    "available": False,
                    "reason": "insufficient capacity",
                }
            )

        payload = {
            "restaurant_id": restaurant_id,
            "date": date,
            "time": time,
            "party_size": party_size,
            "duration_minutes": duration_minutes,
            "available": True,
            "remaining_capacity": remaining,
        }
        return json.dumps(payload)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "check_restaurant_availability",
                "description": "Check if a restaurant can accept a reservation for a given date/time and party size.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "restaurant_id": {
                            "type": "string",
                            "description": "Restaurant ID (UUID format).",
                        },
                        "date": {
                            "type": "string",
                            "description": "Reservation date in YYYY-MM-DD format.",
                        },
                        "time": {
                            "type": "string",
                            "description": "Reservation time in HH:MM 24-hour format.",
                        },
                        "party_size": {
                            "type": "integer",
                            "description": "Number of guests.",
                            "minimum": 1,
                        },
                        "duration_minutes": {
                            "type": "integer",
                            "description": "Expected duration of the reservation in minutes.",
                            "minimum": 30,
                            "maximum": 120,
                        },
                        "exclude_reservation_id": {
                            "type": "string",
                            "description": (
                                "Optional reservation ID to exclude from availability check. "
                                "Useful when modifying an existing reservation to avoid self-conflict."
                            ),
                        },
                    },
                    "required": [
                        "restaurant_id",
                        "date",
                        "time",
                        "party_size",
                        "duration_minutes",
                    ],
                },
            },
        }
