"""Generate mock data for TechGear Customer Support Agent using Faker."""

import json
import random
from datetime import datetime, timedelta
from pathlib import Path

from faker import Faker

fake = Faker()
Faker.seed(42)
random.seed(42)

PRODUCT_CATALOG = [
    {"product_id": "PROD-001", "name": "TechGear Wireless Earbuds", "price": 49.99, "category": "audio"},
    {"product_id": "PROD-002", "name": "TechGear USB-C Hub", "price": 34.99, "category": "accessories"},
    {"product_id": "PROD-003", "name": "TechGear Mechanical Keyboard", "price": 89.99, "category": "peripherals"},
    {"product_id": "PROD-004", "name": "TechGear Gaming Mouse", "price": 59.99, "category": "peripherals"},
    {"product_id": "PROD-005", "name": "TechGear Webcam Pro", "price": 79.99, "category": "video"},
    {"product_id": "PROD-006", "name": "TechGear Monitor Stand", "price": 39.99, "category": "accessories"},
    {"product_id": "PROD-007", "name": "TechGear Laptop Sleeve", "price": 19.99, "category": "accessories"},
    {"product_id": "PROD-008", "name": "TechGear Portable Charger", "price": 29.99, "category": "power"},
    {"product_id": "PROD-009", "name": "TechGear Noise Cancelling Headphones", "price": 129.99, "category": "audio"},
    {"product_id": "PROD-010", "name": "TechGear Smart Speaker", "price": 99.99, "category": "audio"},
]

ORDER_STATUSES = ["delivered", "shipped", "processing", "cancelled", "returned"]
PLANS = ["basic", "pro", "enterprise"]
ACCOUNT_STATUSES = ["active", "active", "active", "active", "suspended", "pending_verification"]

NOW = datetime(2026, 3, 24)


def generate_order(order_num: int, customer_id: str) -> dict:
    """Generate a single order."""
    order_id = f"ORD-{order_num:05d}"
    num_items = random.randint(1, 3)
    products = random.sample(PRODUCT_CATALOG, num_items)

    items = []
    total = 0.0
    for p in products:
        qty = random.randint(1, 2)
        items.append({
            "product_id": p["product_id"],
            "product_name": p["name"],
            "quantity": qty,
            "unit_price": p["price"],
        })
        total += p["price"] * qty

    total = round(total, 2)
    status = random.choice(ORDER_STATUSES)

    ordered_at = fake.date_time_between(start_date="-90d", end_date="-1d")
    delivered_at = None
    return_eligible = False

    if status == "delivered":
        delivered_at = ordered_at + timedelta(days=random.randint(2, 10))
        days_since_delivery = (NOW - delivered_at).days
        return_eligible = days_since_delivery <= 30
    elif status == "returned":
        delivered_at = ordered_at + timedelta(days=random.randint(2, 5))

    return {
        "order_id": order_id,
        "customer_id": customer_id,
        "items": items,
        "total_amount": total,
        "status": status,
        "ordered_at": ordered_at.isoformat(),
        "delivered_at": delivered_at.isoformat() if delivered_at else None,
        "return_eligible": return_eligible,
    }


def generate_data():
    """Generate 50 customers with ~125 orders total."""
    customers_by_id = {}
    orders_by_id = {}
    order_counter = 1

    for i in range(1, 51):
        customer_id = f"CUST-{i:04d}"
        num_orders = random.randint(1, 5)
        order_ids = []

        for _ in range(num_orders):
            order = generate_order(order_counter, customer_id)
            orders_by_id[order["order_id"]] = order
            order_ids.append(order["order_id"])
            order_counter += 1

        customer = {
            "customer_id": customer_id,
            "first_name": fake.first_name(),
            "last_name": fake.last_name(),
            "email": fake.email(),
            "phone": fake.phone_number(),
            "plan": random.choice(PLANS),
            "account_status": random.choice(ACCOUNT_STATUSES),
            "satisfaction_score": round(random.uniform(1.0, 5.0), 1),
            "created_at": fake.date_time_between(start_date="-2y", end_date="-90d").isoformat(),
            "order_ids": order_ids,
        }
        customers_by_id[customer_id] = customer

    db = {
        "product_catalog": PRODUCT_CATALOG,
        "customers_by_id": customers_by_id,
        "orders_by_id": orders_by_id,
        "refund_log": [],
        "escalation_log": [],
    }

    out_path = Path(__file__).parent.parent / "data" / "mock_db.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(db, f, indent=2)

    print(f"Generated {len(customers_by_id)} customers, {len(orders_by_id)} orders")
    print(f"Saved to {out_path}")


if __name__ == "__main__":
    generate_data()
