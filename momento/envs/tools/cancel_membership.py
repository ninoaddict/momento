import json
from typing import Any, Dict
from momento.envs.repository import MembershipRepository, UserRepository
from momento.envs.tools.base import PolicyViolationError, Tool


class CancelMembership(Tool):
    @staticmethod
    def invoke(
        user_id: str,
    ) -> str:
        user_repo = UserRepository()
        membership_repo = MembershipRepository()

        if not user_repo.exists(user_id):
            return "Error: user not found"

        membership = membership_repo.get_active(user_id)
        if not membership:
            raise PolicyViolationError("No active membership found for this user. Nothing to cancel.")

        cancelled = membership_repo.cancel_active(user_id)
        if not cancelled:
            return "Error: failed to cancel membership"

        return json.dumps(cancelled, default=str)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "cancel_membership",
                "description": (
                    "Cancel the user's active membership. The user reverts to the implicit BASIC tier. "
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "user_id": {
                            "type": "string",
                            "description": "User ID whose active membership should be cancelled.",
                        },
                    },
                    "required": ["user_id"],
                },
            },
        }
