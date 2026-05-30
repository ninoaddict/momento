import json
from typing import Any, Dict
from momento.envs.repository import UserRepository
from momento.envs.tools.base import Tool


class GetUserDetails(Tool):
    @staticmethod
    def invoke(
        user_id: str,
    ) -> str:
        user_repo = UserRepository()

        user = user_repo.get_by_id(user_id)
        if not user:
            return "Error: user not found"

        payment_methods = user_repo.get_payment_methods(user_id)
        payment_method_summary = [
            {
                "id": str(pm["id"]),
                "type": pm["type"],
            }
            for pm in payment_methods
        ]

        result = {
            "user_id": user["id"],
            "name": f"{user['first_name']} {user['last_name']}",
            "first_name": user["first_name"],
            "last_name": user["last_name"],
            "email": user["email"],
            "phone": user.get("phone"),
            "gender": user.get("gender"),
            "address": {
                "address1": user.get("address1"),
                "address2": user.get("address2"),
                "city": user.get("city"),
                "state": user.get("state"),
                "country": user.get("country"),
                "zip": user.get("zip"),
            },
            "payment_methods": payment_method_summary,
            "created_at": user.get("created_at"),
        }

        return json.dumps(result, default=str)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_user_details",
                "description": (
                    "Retrieve user profile information by user ID. "
                    "Returns name, email, phone, address, and available payment methods."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "user_id": {
                            "type": "string",
                            "description": "The user ID to look up (e.g., 'olivia_chen_2847').",
                        },
                    },
                    "required": ["user_id"],
                },
            },
        }
