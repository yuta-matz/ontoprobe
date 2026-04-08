"""Generate synthetic EC data with intentional patterns and load into DuckDB."""

import csv
import random
from datetime import date, timedelta
from pathlib import Path

from ontoprobe.config import SEED_DIR
from ontoprobe.db.connection import get_connection

random.seed(42)

REGIONS = ["tokyo", "osaka", "fukuoka", "sapporo", "nagoya"]
SEGMENTS = ["new", "returning", "vip"]

CATEGORIES = [
    (1, "electronics", None),
    (2, "fashion", None),
    (3, "food", None),
    (4, "home", None),
    (5, "winter_fashion", 2),
    (6, "gift_sets", 4),
]

PRODUCTS = [
    # (id, name, category_id, price, is_seasonal)
    (1, "Wireless Earbuds", 1, 4980, False),
    (2, "USB-C Cable", 1, 1280, False),
    (3, "Smartphone Case", 1, 1980, False),
    (4, "T-Shirt Basic", 2, 2480, False),
    (5, "Sneakers", 2, 8980, False),
    (6, "Winter Coat", 5, 15980, True),
    (7, "Knit Scarf", 5, 3480, True),
    (8, "Organic Coffee", 3, 1680, False),
    (9, "Green Tea Set", 3, 2980, False),
    (10, "Desk Lamp", 4, 4480, False),
    (11, "Christmas Gift Box", 6, 5980, True),
    (12, "New Year Hamper", 6, 8980, True),
]

CAMPAIGNS = [
    (1, "Summer Sale", "discount", "2025-07-01", "2025-07-31", 20),
    (2, "Free Ship Week", "free_shipping", "2025-05-15", "2025-05-22", 0),
    (3, "Black Friday", "discount", "2025-11-25", "2025-11-30", 30),
    (4, "Year End Sale", "discount", "2025-12-20", "2025-12-31", 25),
    (5, "Spring Campaign", "free_shipping", "2025-03-01", "2025-03-15", 0),
]

START_DATE = date(2025, 1, 1)
END_DATE = date(2025, 12, 31)


def _generate_customers(n: int = 200) -> list[dict]:
    rows = []
    for i in range(1, n + 1):
        signup = START_DATE + timedelta(days=random.randint(0, 180))
        segment = random.choices(SEGMENTS, weights=[50, 35, 15])[0]
        rows.append({
            "customer_id": i,
            "email": f"customer{i}@example.com",
            "signup_date": signup.isoformat(),
            "region": random.choice(REGIONS),
            "customer_segment": segment,
        })
    return rows


def _active_campaign(order_date: date) -> int | None:
    for cid, _, _, start, end, _ in CAMPAIGNS:
        if date.fromisoformat(start) <= order_date <= date.fromisoformat(end):
            return cid
    return None


def _generate_orders_and_items(customers: list[dict]) -> tuple[list[dict], list[dict]]:
    orders = []
    items = []
    order_id = 1
    item_id = 1

    for day_offset in range((END_DATE - START_DATE).days + 1):
        current_date = START_DATE + timedelta(days=day_offset)
        month = current_date.month
        campaign_id = _active_campaign(current_date)

        # Base daily orders, more in Q4
        base_orders = 8 if month >= 10 else 5
        # Campaign boost
        if campaign_id is not None:
            campaign = next(c for c in CAMPAIGNS if c[0] == campaign_id)
            if campaign[2] == "discount":
                base_orders = int(base_orders * 1.25)
            else:
                base_orders = int(base_orders * 1.15)

        n_orders = random.randint(max(1, base_orders - 2), base_orders + 3)

        for _ in range(n_orders):
            customer = random.choice(customers)
            segment = customer["customer_segment"]

            # VIP customers buy more items and higher-priced products
            if segment == "vip":
                n_items = random.randint(2, 5)
                price_mult = 1.5
            elif segment == "returning":
                n_items = random.randint(1, 3)
                price_mult = 1.1
            else:
                n_items = random.randint(1, 2)
                price_mult = 1.0

            order_total = 0.0
            order_items = []

            for _ in range(n_items):
                product = random.choice(PRODUCTS)
                pid, _, cat_id, base_price, is_seasonal = product

                # Seasonal products spike in Q4
                if is_seasonal and month not in (10, 11, 12):
                    if random.random() > 0.1:
                        product = random.choice([p for p in PRODUCTS if not p[4]])
                        pid, _, cat_id, base_price, is_seasonal = product

                qty = random.randint(1, 3) if segment == "vip" else 1
                unit_price = round(base_price * price_mult, 0)
                line_total = unit_price * qty

                order_items.append({
                    "order_item_id": item_id,
                    "order_id": order_id,
                    "product_id": pid,
                    "quantity": qty,
                    "unit_price": int(unit_price),
                    "line_total": int(line_total),
                })
                order_total += line_total
                item_id += 1

            # Discount from campaign
            discount = 0.0
            if campaign_id is not None:
                campaign = next(c for c in CAMPAIGNS if c[0] == campaign_id)
                dp = campaign[5]
                if dp > 0:
                    discount = round(order_total * dp / 100, 0)

            orders.append({
                "order_id": order_id,
                "customer_id": customer["customer_id"],
                "order_date": current_date.isoformat(),
                "total_amount": int(order_total - discount),
                "discount_amount": int(discount),
                "campaign_id": campaign_id,
                "status": "completed",
            })
            items.extend(order_items)
            order_id += 1

    return orders, items


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def generate_seed_data() -> None:
    """Generate all CSV seed files."""
    customers = _generate_customers()
    orders, order_items = _generate_orders_and_items(customers)

    _write_csv(SEED_DIR / "customers.csv", customers)
    _write_csv(SEED_DIR / "products.csv", [
        {"product_id": p[0], "name": p[1], "category_id": p[2], "price": p[3], "is_seasonal": p[4]}
        for p in PRODUCTS
    ])
    _write_csv(SEED_DIR / "product_categories.csv", [
        {"category_id": c[0], "category_name": c[1], "parent_category_id": c[2] or ""}
        for c in CATEGORIES
    ])
    _write_csv(SEED_DIR / "orders.csv", orders)
    _write_csv(SEED_DIR / "order_items.csv", order_items)
    _write_csv(SEED_DIR / "campaigns.csv", [
        {
            "campaign_id": c[0], "campaign_name": c[1], "campaign_type": c[2],
            "start_date": c[3], "end_date": c[4], "discount_percent": c[5],
        }
        for c in CAMPAIGNS
    ])


def load_seed_to_duckdb() -> None:
    """Load CSV seed data into DuckDB."""
    conn = get_connection()
    for csv_file in sorted(SEED_DIR.glob("*.csv")):
        table_name = csv_file.stem
        conn.execute(f"""
            CREATE OR REPLACE TABLE {table_name} AS
            SELECT * FROM read_csv_auto('{csv_file}')
        """)
    conn.close()


if __name__ == "__main__":
    generate_seed_data()
    load_seed_to_duckdb()
    print("Seed data generated and loaded into DuckDB.")
