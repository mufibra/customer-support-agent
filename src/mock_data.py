"""Mock database loader for TechGear Customer Support Agent."""

import json
import os
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "mock_db.json"

_db = None


def load_db() -> dict:
    """Load the mock database from disk."""
    global _db
    if _db is None:
        if not DB_PATH.exists():
            raise FileNotFoundError(
                f"Mock DB not found at {DB_PATH}. Run: python scripts/generate_data.py"
            )
        with open(DB_PATH, "r") as f:
            _db = json.load(f)
    return _db


def save_db(db: dict) -> None:
    """Persist the mock database to disk."""
    global _db
    _db = db
    with open(DB_PATH, "w") as f:
        json.dump(db, f, indent=2)


def reset_db() -> None:
    """Force reload from disk on next access."""
    global _db
    _db = None


def get_customer(customer_id: str) -> dict | None:
    db = load_db()
    return db["customers_by_id"].get(customer_id)


def get_order(order_id: str) -> dict | None:
    db = load_db()
    return db["orders_by_id"].get(order_id)


def get_orders_by_customer(customer_id: str) -> list[dict]:
    db = load_db()
    customer = db["customers_by_id"].get(customer_id)
    if not customer:
        return []
    return [db["orders_by_id"][oid] for oid in customer.get("order_ids", [])
            if oid in db["orders_by_id"]]


def add_refund_log(entry: dict) -> None:
    db = load_db()
    db["refund_log"].append(entry)
    save_db(db)


def add_escalation_log(entry: dict) -> None:
    db = load_db()
    db["escalation_log"].append(entry)
    save_db(db)
