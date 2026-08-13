"""
test_connection.py
Loads DATABASE_URL from .env, connects to Postgres via SQLAlchemy, runs SELECT 1.
"""

from dotenv import load_dotenv
import os
from sqlalchemy import create_engine, text

# Load .env from the same directory as this script
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL not found in .env — check the file exists and is correctly formatted.")

print(f"Connecting to: {DATABASE_URL[:40]}...  (truncated for safety)")

engine = create_engine(DATABASE_URL)

with engine.connect() as conn:
    result = conn.execute(text("SELECT 1"))
    row = result.fetchone()
    print(f"SELECT 1 returned: {row[0]}")
    print("SUCCESS: Database connection verified!")
