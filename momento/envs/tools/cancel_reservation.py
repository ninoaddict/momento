import json
from typing import Any, Dict
from momento.envs.repository import ReservationRepository
from momento.envs.tools.base import Tool, PolicyViolationError
from momento.utils.utils import is_valid_uuid


class CancelReservation(Tool):
    @staticmethod
    def invoke(
        reservation_id: str,
        user_id: str,
    ) -> str:
        if not is_valid_uuid(reservation_id):
            return f"Error: invalid reservation_id format '{reservation_id}' - must be a valid UUID"

        reservation_repo = ReservationRepository()

        reservation = reservation_repo.get_for_user(reservation_id, user_id)
        if not reservation:
            raise PolicyViolationError(
                "Reservation not found or does not belong to the user."
            )

        if reservation.get("status") == "cancelled":
            raise PolicyViolationError(
                "Reservation is already cancelled."
            )

        if reservation.get("status") in ["completed", "no_show"]:
            raise PolicyViolationError(
                f"Cannot cancel a reservation with status '{reservation.get('status')}'."
            )

        cancelled = reservation_repo.cancel(reservation_id)
        if not cancelled:
            return "Error: failed to cancel reservation"

        return json.dumps(cancelled, default=str)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "cancel_reservation",
                "description": (
                    "Cancel an existing restaurant reservation. "
                    "Only the user who made the reservation can cancel it."
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
                    },
                    "required": ["reservation_id", "user_id"],
                },
            },
        }
