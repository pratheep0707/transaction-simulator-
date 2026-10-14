"""
Application configuration and environment variable management.
Strictly safeguards credentials and provides masked strings for UI/logs.
"""

from dataclasses import dataclass
import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from dotenv import load_dotenv

# Load .env file from project root if it exists
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"
if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)
else:
    load_dotenv()


@dataclass(frozen=True)
class Settings:
    """Immutable application settings."""
    database_url: str
    environment: str
    default_lock_timeout_ms: int
    test_item_id: str
    schema_name: str

    @property
    def is_configured(self) -> bool:
        """Returns True if a non-placeholder database URL is configured."""
        url = self.database_url.strip()
        if not url:
            return False
        # Check against template placeholders
        placeholders = [
            "your-supabase-db-password",
            "your-project-ref",
            "postgres:[PASSWORD]",
            "example.com",
        ]
        return not any(p in url for p in placeholders)

    @property
    def masked_database_url(self) -> str:
        """
        Returns the database URL with user passwords safely redacted.
        Never outputs raw passwords to UI, logs, or exceptions.
        """
        if not self.database_url:
            return "NOT CONFIGURED"
        try:
            parts = urlsplit(self.database_url)
            if parts.password:
                netloc = f"{parts.username}:******@{parts.hostname}"
                if parts.port:
                    netloc += f":{parts.port}"
                masked = urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
                return masked
            return self.database_url
        except Exception:
            return "postgresql://******:******@******"


def get_settings() -> Settings:
    """Factory to retrieve current application settings."""
    raw_url = os.getenv("DATABASE_URL", "").strip()
    env = os.getenv("SIMULATOR_ENV", "development").strip()
    lock_timeout = int(os.getenv("DEFAULT_LOCK_TIMEOUT_MS", "5000"))
    schema_name = os.getenv("SIMULATOR_SCHEMA", "public").strip()
    test_item_id = os.getenv("SIMULATOR_TEST_ITEM_ID", "SIM_DATA_ITEM_ALPHA").strip()

    return Settings(
        database_url=raw_url,
        environment=env,
        default_lock_timeout_ms=lock_timeout,
        test_item_id=test_item_id,
        schema_name=schema_name,
    )
