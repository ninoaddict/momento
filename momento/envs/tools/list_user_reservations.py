import json
from typing import Any, Dict, List, Optional
from momento.envs.repository import (
    ReservationRepository,
    RestaurantRepository,
    UserRepository,
)
from momento.envs.tools.base import Tool


class ListUserReservations(Tool):
    @staticmethod
    def invoke(
        user_id: str,
        status: Optional[str] = None,
    ) -> str:
        user_repo = UserRepository()
        reservation_repo = ReservationRepository()
        restaurant_repo = RestaurantRepository()

        if not user_repo.exists(user_id):
            return "Error: user not found"

        reservations = reservation_repo.list_by_user(user_id, status)

        results: List[Dict[str, Any]] = []
        for reservation in reservations:
            restaurant = restaurant_repo.get_by_id(str(reservation["restaurant_id"]))
            results.append(
                {
                    "id": str(reservation["id"]),
                    "restaurant_id": str(reservation["restaurant_id"]),
                    "restaurant_name": restaurant.get("name") if restaurant else None,
                    "date": reservation["date"],
                    "time": reservation["time"],
                    "party_size": reservation["party_size"],
                    "duration_minutes": reservation.get("duration_minutes", 90),
                    "status": reservation["status"],
                    "special_requests": reservation.get("special_requests"),
                    "created_at": reservation.get("created_at"),
                }
            )

        return json.dumps(results, default=str)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "list_user_reservations",
                "description": "List all reservations for a user, optionally filtered by status.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "user_id": {
                            "type": "string",
                            "description": "User ID to list reservations for.",
                        },
                        "status": {
                            "type": "string",
                            "description": "Optional filter by reservation status.",
                            "enum": ["confirmed", "cancelled", "completed", "no_show"],
                        },
                    },
                    "required": ["user_id"],
                },
            },
        }
