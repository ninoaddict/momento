import json
from typing import Any, Dict, List
from momento.envs.repository import MenuItemRepository
from momento.envs.tools.base import Tool


class DoesCategoryExist(Tool):
    @staticmethod
    def invoke(categories: List[str]) -> str:
        menu_repo = MenuItemRepository()
        categories = [category.lower() for category in categories]
        unique_categories = menu_repo.get_unique_categories()
        res = [{"category": category, "exists": category in unique_categories} for category in categories]
        return json.dumps(res, default=str)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "does_category_exist",
                "description": "Check if given categories exist among the menu items in the system.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "categories": {
                            "type": "array",
                            "items": {
                                "type": "string"
                            },
                            "description": "The categories to check for existence among the menu items."
                        }
                    },
                    "required": ["categories"],
                },
            },
        }
