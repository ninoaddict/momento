import json
from typing import Any, Dict
from momento.envs.repository import OrderRepository
from momento.envs.tools.base import Tool


class GetDeliveryProviders(Tool):
    @staticmethod
    def invoke() -> str:
        order_repo = OrderRepository()
        providers = order_repo.get_delivery_providers()
        return json.dumps(providers, default=str)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_delivery_providers",
                "description": "Get list of available delivery providers for food delivery orders.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        }
