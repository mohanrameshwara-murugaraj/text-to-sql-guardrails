"""Deterministic synthetic business data for the Text-to-SQL portfolio project.

No user or company data is used. All timestamps and monetary values are fixed
by construction so benchmark queries can be reproduced exactly.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import random

import duckdb


SEED = 42
CUSTOMER_COUNT = 40
PRODUCT_COUNT = 16
ORDER_COUNT = 240


def build_database(path: str | Path) -> Path:
    """Recreate a local DuckDB file with deterministic sales data."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()  # Explicitly destructive *setup* operation; never expose via API.
    rng = random.Random(SEED)
    with duckdb.connect(str(target)) as con:
        con.execute("""
            CREATE TABLE customers (
                customer_id INTEGER PRIMARY KEY,
                customer_name VARCHAR NOT NULL,
                region VARCHAR NOT NULL,
                segment VARCHAR NOT NULL
            );
            CREATE TABLE products (
                product_id INTEGER PRIMARY KEY,
                product_name VARCHAR NOT NULL,
                category VARCHAR NOT NULL,
                unit_price DECIMAL(12, 2) NOT NULL
            );
            CREATE TABLE orders (
                order_id INTEGER PRIMARY KEY,
                customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
                order_date DATE NOT NULL,
                status VARCHAR NOT NULL
            );
            CREATE TABLE order_items (
                order_item_id INTEGER PRIMARY KEY,
                order_id INTEGER NOT NULL REFERENCES orders(order_id),
                product_id INTEGER NOT NULL REFERENCES products(product_id),
                quantity INTEGER NOT NULL,
                unit_price DECIMAL(12, 2) NOT NULL
            );
            CREATE TABLE refunds (
                refund_id INTEGER PRIMARY KEY,
                order_id INTEGER NOT NULL REFERENCES orders(order_id),
                refund_date DATE NOT NULL,
                refund_amount DECIMAL(12, 2) NOT NULL
            );
        """)
        regions = ("North", "South", "East", "West")
        segments = ("SMB", "Mid-Market", "Enterprise")
        customers = [(i, f"Customer {i:03d}", regions[(i - 1) % 4], segments[(i - 1) % 3])
                     for i in range(1, CUSTOMER_COUNT + 1)]
        categories = ("Hardware", "Software", "Services", "Accessories")
        products = [(i, f"Product {i:02d}", categories[(i - 1) % 4], round(20 + i * 13.5, 2))
                    for i in range(1, PRODUCT_COUNT + 1)]
        con.executemany("INSERT INTO customers VALUES (?, ?, ?, ?)", customers)
        con.executemany("INSERT INTO products VALUES (?, ?, ?, ?)", products)
        orders = []
        items = []
        refunds = []
        item_id = 1
        refund_id = 1
        base = date(2024, 1, 1)
        for order_id in range(1, ORDER_COUNT + 1):
            customer_id = rng.randint(1, CUSTOMER_COUNT)
            order_date = base + timedelta(days=rng.randint(0, 729))
            status = "cancelled" if order_id % 17 == 0 else "completed"
            orders.append((order_id, customer_id, order_date, status))
            gross_total = 0.0
            for _ in range(rng.randint(1, 3)):
                product_id = rng.randint(1, PRODUCT_COUNT)
                quantity = rng.randint(1, 4)
                price = products[product_id - 1][3]
                items.append((item_id, order_id, product_id, quantity, price))
                gross_total += quantity * price
                item_id += 1
            if status == "completed" and order_id % 11 == 0:
                # Synthetic partial refund after purchase. No refunds on cancelled orders.
                refunds.append((refund_id, order_id, order_date + timedelta(days=5),
                                round(gross_total * 0.2, 2)))
                refund_id += 1
        con.executemany("INSERT INTO orders VALUES (?, ?, ?, ?)", orders)
        con.executemany("INSERT INTO order_items VALUES (?, ?, ?, ?, ?)", items)
        con.executemany("INSERT INTO refunds VALUES (?, ?, ?, ?)", refunds)
        con.execute("CHECKPOINT")
    return target
