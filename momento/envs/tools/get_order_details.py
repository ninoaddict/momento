import json
from typing import Any, Dict
from momento.envs.repository import OrderRepository, RestaurantRepository
from momento.envs.tools.base import Tool
from momento.utils.utils import is_valid_uuid


class GetOrderDetails(Tool):
    @staticmethod
    def invoke(
        order_id: str,
        user_id: str,
    ) -> str:
        if not is_valid_uuid(order_id):
            return f"Error: invalid order_id format '{order_id}' - must be a valid UUID"

        order_repo = OrderRepository()
        restaurant_repo = RestaurantRepository()

        order = order_repo.get_for_user(order_id, user_id)
        if not order:
            return "Error: order not found or does not belong to the user"

        restaurant = restaurant_repo.get_by_id(str(order["restaurant_id"]))

        result = {
            "id": str(order["id"]),
            "user_id": order["user_id"],
            "restaurant_id": str(order["restaurant_id"]),
            "restaurant_name": restaurant.get("name") if restaurant else None,
            "fulfillment": order["fulfillment"],
            "status": order["status"],
            "total_price": float(order["total_price"]) if order.get("total_price") else None,
            "currency": order.get("currency", "USD"),
            "delivery_provider_name": order.get("delivery_provider_name"),
            "delivery_address": order.get("delivery_address"),
            "special_instructions": order.get("special_instructions"),
            "items": [
                {
                    "id": str(item["id"]),
                    "menu_item_id": str(item["menu_item_id"]) if item.get("menu_item_id") else None,
                    "name": item["name"],
                    "price": float(item["price"]) if item.get("price") else None,
                    "quantity": item["quantity"],
                    "notes": item.get("notes"),
                }
                for item in order.get("items", [])
            ],
            "created_at": order.get("created_at"),
            "updated_at": order.get("updated_at"),
        }

        return json.dumps(result, default=str)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_order_details",
                "description": "Get details of a specific order including all items. Only the user who placed the order can view it.",
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
