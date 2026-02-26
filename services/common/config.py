from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    auth_mode: str = "header"
    auth_db_enforce: bool = False
    auth_enforce_modules: bool = True
    auth_enforce_rbac: bool = True
    license_enforcement: str = "warn"

    database_url: str = "postgresql://postgres:postgres@localhost:5432/postgres"
    supabase_url: str = ""
    supabase_anon_key: str = ""

    # Deepgram Voice AI
    deepgram_api_key: str = ""

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)


settings = Settings()
