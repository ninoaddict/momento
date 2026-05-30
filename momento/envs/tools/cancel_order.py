import json
from typing import Any, Dict
from momento.envs.repository import OrderRepository
from momento.envs.tools.base import Tool, PolicyViolationError
from momento.utils.utils import is_valid_uuid


class CancelOrder(Tool):
    @staticmethod
    def invoke(
        order_id: str,
        user_id: str,
    ) -> str:
        if not is_valid_uuid(order_id):
            return f"Error: invalid order_id format '{order_id}' - must be a valid UUID"

        order_repo = OrderRepository()

        order = order_repo.get_for_user(order_id, user_id)
        if not order:
            raise PolicyViolationError(
                "Order not found or does not belong to the user."
            )

        if not order_repo.is_cancellable(order):
            raise PolicyViolationError(
                f"Cannot cancel an order with status '{order.get('status')}'. "
                "Only orders with status 'created' or 'confirmed' can be cancelled."
            )

        cancelled = order_repo.cancel(order_id)
        if not cancelled:
            return "Error: failed to cancel order"

        cancelled_order = order_repo.get_by_id(order_id)
        return json.dumps(cancelled_order, default=str)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "cancel_order",
                "description": "Cancel a food order. Only orders with status 'created' or 'confirmed' can be cancelled.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "order_id": {
                            "type": "string",
                            "description": "Order ID (UUID format).",
                        },
                        "user_id": {
                            "type": "string",
                            "description": "User ID who owns the order.",
                        },
                    },
                    "required": ["order_id", "user_id"],
                },
            },
        }
