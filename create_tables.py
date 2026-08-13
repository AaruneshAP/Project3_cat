"""
create_tables.py
Reads schema.sql, runs it against the Neon Postgres DB, then verifies
the tickets table exists by querying information_schema.
"""

from dotenv import load_dotenv
import os
from pathlib import Path
from sqlalchemy import create_engine, text

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL not found in .env")

schema_path = Path(__file__).parent / "schema.sql"
ddl = schema_path.read_text()

engine = create_engine(DATABASE_URL)

print("Running schema.sql against the database...")
with engine.begin() as conn:
    conn.execute(text(ddl))
print("DDL executed successfully.\n")

VERIFY_QUERY = """
SELECT column_name, data_type, is_nullable, column_default
FROM   information_schema.columns
WHERE  table_name = 'tickets'
ORDER  BY ordinal_position;
"""

print(f"{'Column':<22} {'Type':<25} {'Nullable':<10} {'Default'}")
print("-" * 75)

with engine.connect() as conn:
    rows = conn.execute(text(VERIFY_QUERY)).fetchall()
    for row in rows:
        col, dtype, nullable, default = row
        print(f"{col:<22} {dtype:<25} {nullable:<10} {default or ''}")

print(f"\nTable 'tickets' confirmed -- {len(rows)} column(s) found.")
