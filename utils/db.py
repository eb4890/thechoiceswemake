import streamlit as st
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://choices_user:your_very_strong_password_here@localhost:5433/choices_archive")

conn = st.connection(
    name="db",
    type="sql",
    url=DATABASE_URL
)

def execute_write(sql: str, params=None):
    """
    Execute a write query using SQLAlchemy's connection management.
    Handles transactions automatically to ensure data is saved.
    """
    with conn._instance.begin() as connection:
        connection.exec_driver_sql(sql, params or ())
