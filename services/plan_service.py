# services/plan_service.py
# Plan functions live in product_service.py — re-export them from here
# so admin_handlers can import from services.plan_service as expected.

from services.product_service import (  # noqa: F401
    get_plans_by_product,
    get_plan_by_id,
    add_plan,
    update_plan,
    delete_plan,
)