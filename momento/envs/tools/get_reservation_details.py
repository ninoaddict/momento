import json
from typing import Any, Dict
from momento.envs.repository import ReservationRepository, RestaurantRepository
from momento.envs.tools.base import Tool
from momento.utils.utils import is_valid_uuid


class GetReservationDetails(Tool):
    @staticmethod
    def invoke(
        reservation_id: str,
        user_id: str,
    ) -> str:
        if not is_valid_uuid(reservation_id):
            return f"Error: invalid reservation_id format '{reservation_id}' - must be a valid UUID"

        reservation_repo = ReservationRepository()
        restaurant_repo = RestaurantRepository()

        reservation = reservation_repo.get_for_user(reservation_id, user_id)
        if not reservation:
            return "Error: reservation not found or does not belong to the user"

        restaurant = restaurant_repo.get_by_id(str(reservation["restaurant_id"]))
        result = {
            "id": str(reservation["id"]),
            "restaurant_id": str(reservation["restaurant_id"]),
            "restaurant_name": restaurant.get("name") if restaurant else None,
            "restaurant_address": restaurant.get("address") if restaurant else None,
            "user_id": reservation["user_id"],
            "date": reservation["date"],
            "time": reservation["time"],
            "party_size": reservation["party_size"],
            "duration_minutes": reservation.get("duration_minutes", 90),
            "special_requests": reservation.get("special_requests"),
            "status": reservation["status"],
            "created_at": reservation.get("created_at"),
        }
        return json.dumps(result, default=str)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_reservation_details",
                "description": "Get details of a specific reservation. Only the user who made the reservation can view it.",
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
                    },
                    "required": ["reservation_id", "user_id"],
                },
            },
        }
