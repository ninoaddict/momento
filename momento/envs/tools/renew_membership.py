import json
from typing import Any, Dict
from momento.envs.repository import MembershipRepository, UserRepository
from momento.envs.tools.base import Tool, PolicyViolationError


class RenewMembership(Tool):
    @staticmethod
    def invoke(
        user_id: str,
        new_end_date: str,
    ) -> str:
        user_repo = UserRepository()
        membership_repo = MembershipRepository()

        if not user_repo.exists(user_id):
            return "Error: user not found"

        membership = membership_repo.get_active(user_id)
        if not membership:
            raise PolicyViolationError(
                "No active membership found for this user. Only active memberships can be renewed."
            )

        renewed = membership_repo.renew_active(user_id, new_end_date)
        if not renewed:
            return "Error: failed to renew membership"

        return json.dumps(renewed, default=str)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "renew_membership",
                "description": (
                    "Renew the user's active membership by extending its end date. "
                    "Only active memberships can be renewed. "
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "user_id": {
                            "type": "string",
                            "description": "User ID whose active membership should be renewed.",
                        },
                        "new_end_date": {
                            "type": "string",
                            "description": "New membership end date in YYYY-MM-DD format.",
                        },
                    },
                    "required": ["user_id", "new_end_date"],
                },
            },
        }
