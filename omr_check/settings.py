import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    token: str
    allowed_users: frozenset[int]
    keys: Path
    data_dir: Path
    ttl_minutes: int

    @classmethod
    def from_env(cls):
        load_dotenv(ROOT / ".env")
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            raise ValueError("Set TELEGRAM_BOT_TOKEN in .env, then run the bot again")
        users = frozenset(int(value.strip()) for value in os.getenv("ALLOWED_USER_IDS", "").split(",") if value.strip())
        ttl = int(os.getenv("SESSION_TTL_MINUTES", "30"))
        if not 1 <= ttl <= 1440:
            raise ValueError("SESSION_TTL_MINUTES must be between 1 and 1440")
        return cls(token, users, ROOT / os.getenv("ANSWER_KEYS_PATH", "data/answer_keys.json"), ROOT / os.getenv("OMR_DATA_DIR", "var"), ttl)
