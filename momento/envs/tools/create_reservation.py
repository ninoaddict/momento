import json
from typing import Any, Dict, Optional
from momento.envs.repository import (
    MembershipRepository,
    ReservationRepository,
    RestaurantRepository,
    UserRepository,
)
from momento.envs.repository.membership_repository import MEMBERSHIP_BENEFITS
from momento.envs.tools.base import PolicyViolationError, Tool
from momento.utils.utils import is_valid_uuid


class CreateReservation(Tool):
    @staticmethod
    def invoke(
        restaurant_id: str,
        user_id: str,
        date: str,
        time: str,
        party_size: int,
        duration_minutes: int,
        special_requests: Optional[str] = None,
    ) -> str:
        if not is_valid_uuid(restaurant_id):
            return f"Error: invalid restaurant_id format '{restaurant_id}' - must be a valid UUID"

        if party_size < 1:
            raise PolicyViolationError("party_size must be at least 1")
        if duration_minutes < 30:
            raise PolicyViolationError("duration_minutes must be at least 30 minutes")
        if duration_minutes > 120:
            raise PolicyViolationError("duration_minutes cannot exceed 120 minutes")
      
        user_repo = UserRepository()
        restaurant_repo = RestaurantRepository()
        reservation_repo = ReservationRepository()
        membership_repo = MembershipRepository()

        if not user_repo.exists(user_id):
            return "Error: user not found"

        restaurant = restaurant_repo.get_by_id(restaurant_id)
        if not restaurant:
            return "Error: restaurant not found"

        opening_hours = restaurant.get("opening_hours")
        is_open, reason = reservation_repo.is_restaurant_open(opening_hours, date, time)
        if not is_open:
            raise PolicyViolationError(f"Restaurant is not open at the requested time: {reason}")

        effective_tier = membership_repo.get_effective_tier(user_id)
        benefits = MEMBERSHIP_BENEFITS.get(effective_tier, MEMBERSHIP_BENEFITS["basic"])
        has_priority = benefits.get("priority_reservation", False)

        capacity = restaurant.get("capacity", 0)
        remaining = reservation_repo.remaining_capacity(
            restaurant_id, capacity, date, time, duration_minutes
        )
        if party_size > remaining:
            raise PolicyViolationError(f"Not enough capacity for the requested time")

        if has_priority:
            perk_note = f"{effective_tier} membership: priority reservation"
            if special_requests:
                special_requests = f"{special_requests} | {perk_note}"
            else:
                special_requests = perk_note

        reservation = reservation_repo.create(
            restaurant_id=restaurant_id,
            user_id=user_id,
            date_str=date,
            time_str=time,
            party_size=party_size,
            duration_minutes=duration_minutes,
            special_requests=special_requests,
        )

        if not reservation:
            return "Error: failed to create reservation"

        return json.dumps(reservation, default=str)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "create_reservation",
                "description": (
                    "Create a restaurant reservation for a user. "
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "restaurant_id": {
                            "type": "string",
                            "description": "Restaurant ID (UUID format).",
                        },
                        "user_id": {
                            "type": "string",
                            "description": "User ID making the reservation.",
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
                        "special_requests": {
                            "type": "string",
                            "description": "Optional special requests or notes for the reservation.",
                        },
                    },
                    "required": [
                        "restaurant_id",
                        "user_id",
                        "date",
                        "time",
                        "party_size",
                        "duration_minutes",
                    ],
                },
            },
        }
