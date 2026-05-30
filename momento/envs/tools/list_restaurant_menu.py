import json
from typing import Any, Dict
from momento.envs.repository import MenuItemRepository, RestaurantRepository
from momento.envs.tools.base import Tool
from momento.utils.utils import is_valid_uuid


def _compact_menu_item(record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(record.get("id")),
        "name": record.get("name"),
        "description": record.get("description"),
        "categories": record.get("categories", []),
        "cuisines": record.get("cuisines", []),
        "price": float(record.get("price", 0)) if record.get("price") else None,
        "image_url": record.get("image_url", []),
    }


class ListRestaurantMenu(Tool):
    @staticmethod
    def invoke(
        restaurant_id: str,
    ) -> str:
        if not is_valid_uuid(restaurant_id):
            return f"Error: invalid restaurant_id format '{restaurant_id}' - must be a valid UUID"

        restaurant_repo = RestaurantRepository()
        menu_repo = MenuItemRepository()

        if not restaurant_repo.exists(restaurant_id):
            return "Error: restaurant not found"

        menu_items = menu_repo.list_by_restaurant(restaurant_id)
        return json.dumps(
            [_compact_menu_item(item) for item in menu_items], default=str
        )

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "list_restaurant_menu",
                "description": "List all menu items available at a specific restaurant.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "restaurant_id": {
                            "type": "string",
                            "description": "Restaurant ID (UUID format).",
                        },
                    },
                    "required": ["restaurant_id"],
                },
            },
        }
