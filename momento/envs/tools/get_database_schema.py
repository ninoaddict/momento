import json
from typing import Any, Dict
from momento.envs.tools.base import Tool

SCHEMA_SUMMARY: Dict[str, Any] = {
    "tables": {
        "users": {
            "description": "Registered users",
            "columns": {
                "id": "TEXT PRIMARY KEY",
                "first_name": "TEXT NOT NULL",
                "last_name": "TEXT NOT NULL",
                "email": "TEXT NOT NULL",
                "gender": "ENUM (male, female, other)",
                "address1": "TEXT",
                "address2": "TEXT",
                "city": "TEXT",
                "state": "TEXT",
                "country": "TEXT",
                "zip": "TEXT",
                "phone": "TEXT",
                "created_at": "TIMESTAMPTZ",
            },
        },
        "payment_methods": {
            "description": "User payment methods",
            "columns": {
                "id": "UUID PRIMARY KEY",
                "user_id": "TEXT FK → users(id)",
                "type": "ENUM (credit_card, debit_card, paypal, apple_pay, google_pay, cash)",
                "details": "JSONB",
                "created_at": "TIMESTAMPTZ",
            },
        },
        "restaurants": {
            "description": "Restaurant listings",
            "columns": {
                "id": "UUID PRIMARY KEY",
                "name": "TEXT NOT NULL",
                "description": "TEXT",
                "address": "TEXT",
                "city": "TEXT",
                "country": "TEXT",
                "lat": "DOUBLE PRECISION",
                "lon": "DOUBLE PRECISION",
                "cuisines": "TEXT[]",
                "price_range_lower": "INTEGER",
                "price_range_upper": "INTEGER",
                "opening_hours": "JSONB",
                "capacity": "INTEGER DEFAULT 40",
                "amenities": "TEXT[]",
                "image_url": "TEXT[]",
            },
        },
        "menu_items": {
            "description": "Restaurant menu items",
            "columns": {
                "id": "UUID PRIMARY KEY",
                "restaurant_id": "UUID FK → restaurants(id)",
                "name": "TEXT NOT NULL",
                "description": "TEXT",
                "categories": "TEXT[]",
                "cuisines": "TEXT[]",
                "price": "NUMERIC",
                "image_url": "TEXT[]",
            },
        },
        "reservations": {
            "description": "Table reservations",
            "columns": {
                "id": "UUID PRIMARY KEY",
                "user_id": "TEXT FK → users(id)",
                "restaurant_id": "UUID FK → restaurants(id)",
                "date": "DATE NOT NULL",
                "time": "TIME NOT NULL",
                "party_size": "INTEGER NOT NULL",
                "special_requests": "TEXT",
                "duration_minutes": "INTEGER NOT NULL DEFAULT 90",
                "status": "ENUM (confirmed, cancelled, completed, no_show)",
                "created_at": "TIMESTAMPTZ",
            },
        },
        "orders": {
            "description": "Food orders",
            "columns": {
                "id": "UUID PRIMARY KEY",
                "user_id": "TEXT FK → users(id)",
                "restaurant_id": "UUID FK → restaurants(id)",
                "fulfillment": "ENUM (pickup, delivery)",
                "status": "ENUM (created, confirmed, preparing, ready, picked_up, on_the_way, delivered, cancelled)",
                "total_price": "NUMERIC NOT NULL",
                "currency": "TEXT DEFAULT 'USD'",
                "delivery_provider_name": "ENUM (swiftdrop, foodfly, quickdish, mealdash, carryeats)",
                "delivery_address": "TEXT",
                "special_instructions": "TEXT",
                "created_at": "TIMESTAMPTZ",
                "updated_at": "TIMESTAMPTZ",
            },
        },
        "order_items": {
            "description": "Line items within an order",
            "columns": {
                "id": "UUID PRIMARY KEY",
                "order_id": "UUID FK → orders(id)",
                "menu_item_id": "UUID FK → menu_items(id)",
                "name": "TEXT NOT NULL",
                "price": "NUMERIC NOT NULL",
                "quantity": "INTEGER NOT NULL",
                "notes": "TEXT",
            },
        },
        "memberships": {
            "description": "User membership records",
            "columns": {
                "id": "UUID PRIMARY KEY",
                "user_id": "TEXT FK → users(id)",
                "tier": "ENUM (basic, silver, gold, platinum)",
                "status": "ENUM (active, cancelled, expired)",
                "start_date": "DATE NOT NULL",
                "end_date": "DATE",
                "created_at": "TIMESTAMPTZ",
                "updated_at": "TIMESTAMPTZ",
            },
        },
        "sessions": {
            "description": "Past conversation sessions with the assistant",
            "columns": {
                "id": "UUID PRIMARY KEY",
                "user_id": "TEXT FK → users(id)",
                "started_at": "TIMESTAMPTZ NOT NULL",
                "ended_at": "TIMESTAMPTZ NOT NULL",
                "summary": "TEXT NOT NULL",
                "extracted_facts": "JSONB NOT NULL DEFAULT '{}'",
                "embedding": "vector(1024)",
                "created_at": "TIMESTAMPTZ",
            },
        },
        "session_messages": {
            "description": "Individual messages within a session",
            "columns": {
                "id": "UUID PRIMARY KEY",
                "session_id": "UUID FK → sessions(id)",
                "role": "TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'tool'))",
                "content": "JSONB NOT NULL",
                "seq": "INTEGER NOT NULL",
            },
        },
    },
    "relationships": [
        "payment_methods.user_id → users.id",
        "menu_items.restaurant_id → restaurants.id",
        "reservations.user_id → users.id",
        "reservations.restaurant_id → restaurants.id",
        "orders.user_id → users.id",
        "orders.restaurant_id → restaurants.id",
        "order_items.order_id → orders.id",
        "order_items.menu_item_id → menu_items.id",
        "memberships.user_id → users.id",
        "sessions.user_id → users.id",
        "session_messages.session_id → sessions.id",
    ],
}


class GetDatabaseSchema(Tool):
    @staticmethod
    def invoke() -> str:
        return json.dumps(SCHEMA_SUMMARY, indent=2)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_database_schema",
                "description": (
                    "Retrieve the database schema including all tables, columns, types, "
                    "and relationships. Use this before writing SQL queries to understand "
                    "the available data structure."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        }
