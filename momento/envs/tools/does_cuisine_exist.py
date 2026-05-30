import json
from typing import Any, Dict, List
from momento.envs.repository import MenuItemRepository
from momento.envs.tools.base import Tool


class DoesCuisineExist(Tool):
    @staticmethod
    def invoke(cuisines: List[str]) -> str:
        menu_repo = MenuItemRepository()
        cuisines = [cuisine.lower() for cuisine in cuisines]
        unique_cuisines = menu_repo.get_unique_cuisines()
        res = [{"cuisine": cuisine, "exists": cuisine in unique_cuisines} for cuisine in cuisines]
        return json.dumps(res, default=str)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "does_cuisine_exist",
                "description": "Check if given cuisines exist among the menu items in the system.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "cuisines": {
                            "type": "array",
                            "items": {
                                "type": "string"
                            },
                            "description": "The cuisines to check for existence among the menu items."
                        }
                    },
                    "required": ["cuisines"],
                },
            },
        }
