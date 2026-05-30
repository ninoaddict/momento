import json
from typing import Any, Dict, List, Optional
from momento.envs.repository import OrderRepository, RestaurantRepository, UserRepository
from momento.envs.tools.base import Tool


class ListUserOrders(Tool):
    @staticmethod
    def invoke(
        user_id: str,
        status: Optional[str] = None,
    ) -> str:
        user_repo = UserRepository()
        order_repo = OrderRepository()
        restaurant_repo = RestaurantRepository()

        if not user_repo.exists(user_id):
            return "Error: user not found"

        valid_statuses = [
            "created", "confirmed", "preparing", "ready",
            "picked_up", "on_the_way", "delivered", "cancelled"
        ]
        if status and status not in valid_statuses:
            return f"Error: invalid status. Valid options: {', '.join(valid_statuses)}"

        orders = order_repo.list_by_user(user_id, status)
        results: List[Dict[str, Any]] = []
        for order in orders:
            restaurant = restaurant_repo.get_by_id(str(order["restaurant_id"]))
            results.append({
                "id": str(order["id"]),
                "restaurant_id": str(order["restaurant_id"]),
                "restaurant_name": restaurant.get("name") if restaurant else None,
                "fulfillment": order["fulfillment"],
                "status": order["status"],
                "total_price": float(order["total_price"]) if order.get("total_price") else None,
                "currency": order.get("currency", "USD"),
                "delivery_provider_name": order.get("delivery_provider_name"),
                "item_count": len(order.get("items", [])),
                "created_at": order.get("created_at"),
            })
        return json.dumps(results, default=str)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "list_user_orders",
                "description": "List all orders for a user, optionally filtered by status.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "user_id": {
                            "type": "string",
                            "description": "User ID to list orders for.",
                        },
                        "status": {
                            "type": "string",
                            "description": "Optional filter by order status.",
                            "enum": [
                                "created", "confirmed", "preparing", "ready",
                                "picked_up", "on_the_way", "delivered", "cancelled"
                            ],
                        },
                    },
                    "required": ["user_id"],
                },
            },
        }
