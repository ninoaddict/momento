import json
from typing import Any, Dict

from momento.envs.repository import MenuItemRepository, RestaurantRepository
from momento.envs.tools.base import Tool
from momento.utils.utils import is_valid_uuid


class GetMenuItemDetails(Tool):
    @staticmethod
    def invoke(
        menu_item_id: str,
    ) -> str:
        if not is_valid_uuid(menu_item_id):
            return f"Error: invalid menu_item_id format '{menu_item_id}' - must be a valid UUID"

        menu_repo = MenuItemRepository()
        restaurant_repo = RestaurantRepository()

        menu_item = menu_repo.get_by_id(menu_item_id)
        if not menu_item:
            return "Error: menu item not found"

        restaurant = restaurant_repo.get_by_id(str(menu_item["restaurant_id"]))

        result = {
            "id": str(menu_item["id"]),
            "restaurant_id": str(menu_item["restaurant_id"]),
            "restaurant_name": restaurant.get("name") if restaurant else None,
            "name": menu_item.get("name"),
            "description": menu_item.get("description"),
            "categories": menu_item.get("categories", []),
            "cuisines": menu_item.get("cuisines", []),
            "price": (
                float(menu_item.get("price", 0)) if menu_item.get("price") else None
            ),
            "image_url": menu_item.get("image_url", []),
        }

        return json.dumps(result, default=str)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_menu_item_details",
                "description": "Get detailed information about a specific menu item by ID.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "menu_item_id": {
                            "type": "string",
                            "description": "Menu item ID (UUID format).",
                        },
                    },
                    "required": ["menu_item_id"],
                },
            },
        }
