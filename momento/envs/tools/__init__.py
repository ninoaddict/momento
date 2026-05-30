from momento.envs.tools.base import Tool, PolicyViolationError

# Reservation tools
from momento.envs.tools.cancel_reservation import CancelReservation
from momento.envs.tools.check_availability import CheckRestaurantAvailability
from momento.envs.tools.create_reservation import CreateReservation
from momento.envs.tools.get_reservation_details import GetReservationDetails
from momento.envs.tools.list_user_reservations import ListUserReservations
from momento.envs.tools.update_reservation import UpdateReservation

# Search and query tools
from momento.envs.tools.get_menu_item_details import GetMenuItemDetails
from momento.envs.tools.get_restaurant_details import GetRestaurantDetails
from momento.envs.tools.list_restaurant_menu import ListRestaurantMenu
from momento.envs.tools.query_menu_items import QueryMenuItems
from momento.envs.tools.search_restaurants import SearchRestaurants

# Order tools
from momento.envs.tools.cancel_order import CancelOrder
from momento.envs.tools.create_order import CreateOrder
from momento.envs.tools.get_delivery_providers import GetDeliveryProviders
from momento.envs.tools.get_order_details import GetOrderDetails
from momento.envs.tools.list_user_orders import ListUserOrders

# Membership tools
from momento.envs.tools.apply_membership import ApplyMembership
from momento.envs.tools.cancel_membership import CancelMembership
from momento.envs.tools.renew_membership import RenewMembership
from momento.envs.tools.get_membership_status import GetMembershipStatus
from momento.envs.tools.get_membership_benefits import GetMembershipBenefits

# Other tools
from momento.envs.tools.does_category_exist import DoesCategoryExist
from momento.envs.tools.does_cuisine_exist import DoesCuisineExist
from momento.envs.tools.get_user_details import GetUserDetails

# Text-to-SQL tools
from momento.envs.tools.get_database_schema import GetDatabaseSchema
from momento.envs.tools.execute_sql import ExecuteSQL


ALL_TOOLS = [
    # Reservation tools
    CheckRestaurantAvailability,
    CreateReservation,
    CancelReservation,
    UpdateReservation,
    GetReservationDetails,
    ListUserReservations,
    # Search and query tools
    SearchRestaurants,
    QueryMenuItems,
    GetMenuItemDetails,
    GetRestaurantDetails,
    ListRestaurantMenu,
    # Order tools
    CreateOrder,
    CancelOrder,
    GetOrderDetails,
    ListUserOrders,
    GetDeliveryProviders,
    # Membership tools
    ApplyMembership,
    CancelMembership,
    RenewMembership,
    GetMembershipStatus,
    GetMembershipBenefits,
    # Other tools
    GetUserDetails,
    DoesCuisineExist,
    DoesCategoryExist,
    # Text-to-SQL tools
    GetDatabaseSchema,
    ExecuteSQL,
]

__all__ = [
    "Tool",
    "PolicyViolationError",
    # Reservation tools
    "CheckRestaurantAvailability",
    "CreateReservation",
    "CancelReservation",
    "UpdateReservation",
    "GetReservationDetails",
    "ListUserReservations",
    # Search and query tools
    "SearchRestaurants",
    "QueryMenuItems",
    "GetMenuItemDetails",
    "GetRestaurantDetails",
    "ListRestaurantMenu",
    # Order tools
    "CreateOrder",
    "CancelOrder",
    "GetOrderDetails",
    "ListUserOrders",
    "GetDeliveryProviders",
    # Membership tools
    "ApplyMembership",
    "CancelMembership",
    "RenewMembership",
    "GetMembershipStatus",
    "GetMembershipBenefits",
    # Other tools
    "GetUserDetails",
    "DoesCuisineExist",
    "DoesCategoryExist",
    # Text-to-SQL tools
    "GetDatabaseSchema",
    "ExecuteSQL",
    # All tools list
    "ALL_TOOLS",
]
