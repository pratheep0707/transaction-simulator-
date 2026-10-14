"""
PostgreSQL database connection management using psycopg (psycopg 3).
Provides secure connection lifecycle, SSL enforcement, safe error translation,
and connection pooling / independent connection creation for concurrent workers.
"""

from contextlib import contextmanager
from typing import Dict, Generator, Optional, Tuple
import psycopg
from psycopg import Connection, Error as PsycopgError

from config.settings import get_settings


def clean_error_message(err: Exception) -> str:
    """Sanitizes connection error message to strip sensitive credentials or internal paths."""
    msg = str(err)
    # Remove password if somehow present in raw psycopg exception string
    if "password" in msg.lower():
        lines = msg.splitlines()
        filtered = [l for l in lines if "password" not in l.lower()]
        return " ".join(filtered) if filtered else "Database authentication failed. Please verify credentials."
    return msg


def get_raw_connection(autocommit: bool = False, connect_timeout: int = 10) -> Connection:
    """
    Creates an independent direct psycopg connection.
    Essential for concurrency: each concurrent transaction T1, T2 must own
    its distinct connection to PostgreSQL.
    """
    settings = get_settings()
    if not settings.is_configured:
        raise ValueError("DATABASE_URL is not configured or contains placeholder values.")

    url = settings.database_url
    # Ensure sslmode is present for Supabase
    if "sslmode" not in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}sslmode=require"

    try:
        conn = psycopg.connect(
            url,
            autocommit=autocommit,
            connect_timeout=connect_timeout,
        )
        return conn
    except PsycopgError as e:
        sanitized = clean_error_message(e)
        raise ConnectionError(f"PostgreSQL Connection Error: {sanitized}") from None


@contextmanager
def get_connection(autocommit: bool = False) -> Generator[Connection, None, None]:
    """Context manager for acquiring and safely closing a database connection."""
    conn = get_raw_connection(autocommit=autocommit)
    try:
        yield conn
    finally:
        try:
            if not conn.closed:
                conn.close()
        except Exception:
            pass


def test_connection() -> Tuple[bool, str, Dict[str, str]]:
    """
    Tests connectivity to Supabase PostgreSQL without raising uncaught exceptions.
    Returns:
        (success, status_message, server_metadata)
    """
    settings = get_settings()
    if not settings.is_configured:
        return (
            False,
            "DATABASE_URL is missing or using placeholder values in .env. Configure your Supabase connection string to execute live database scenarios.",
            {"status": "UNCONFIGURED", "masked_url": settings.masked_database_url},
        )

    try:
        with get_connection(autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT version(), current_database(), current_user, inet_server_addr(), inet_server_port();"
                )
                row = cur.fetchone()
                if row:
                    version, db, user, s_addr, s_port = row
                    meta = {
                        "status": "CONNECTED",
                        "database": str(db),
                        "user": str(user),
                        "version": str(version).split(",")[0],
                        "server_address": str(s_addr) if s_addr else "Cloud Hosted",
                        "port": str(s_port) if s_port else "5432",
                        "masked_url": settings.masked_database_url,
                    }
                    return (True, "Successfully connected to Supabase PostgreSQL.", meta)
                return (True, "Connected, but no server metadata returned.", {})
    except Exception as e:
        cleaned = clean_error_message(e)
        return (
            False,
            f"Failed to connect to database: {cleaned}",
            {"status": "ERROR", "error": cleaned, "masked_url": settings.masked_database_url},
        )
