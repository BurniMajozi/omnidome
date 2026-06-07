"""One-shot script to create IoT tables in Supabase."""
import asyncio
import os
from urllib.parse import quote, unquote

# Load .env from project root
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())

raw_url = os.environ.get("DATABASE_URL", "")

# Manual parse: postgresql://USER:***@HOST:PORT/DB
# Split on '://' first, then split credentials from host
scheme_rest = raw_url.split("://", 1)
rest = scheme_rest[1]  # USER:***@HOST:PORT/DB

# Find the last @ to split credentials from host (password may contain @)
at_idx = rest.rfind("@")
credentials = rest[:at_idx]
host_part = rest[at_idx + 1:]

# Split credentials into user:***
colon_idx = credentials.index(":")
username = credentials[:colon_idx]
password = credentials[colon_idx + 1:]

# Split host_part into HOST:PORT/DB
slash_idx = host_part.index("/")
host_port = host_part[:slash_idx]
database = host_part[slash_idx + 1:]

colon2_idx = host_port.rfind(":")
host = host_port[:colon2_idx]
port = host_port[colon2_idx + 1:]

# The .env password may be URL-encoded; decode it first so asyncpg gets the raw password
password = unquote(password)
safe_url = f"postgresql+asyncpg://{username}:{quote(password, safe='')}@{host}:{port}/{database}"

print(f"Connecting to: postgresql+asyncpg://{username}:****@{host}:{port}/{database}")

import services.iot.models  # noqa: F401
from services.iot.models import Base
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text


async def main():
    engine = create_async_engine(safe_url, pool_pre_ping=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ All IoT tables created in Supabase.")

    async with engine.begin() as conn:
        result = await conn.execute(text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name LIKE 'iot_%' "
            "ORDER BY table_name"
        ))
        tables = [row[0] for row in result.fetchall()]
        print(f"\n📋 IoT tables in Supabase ({len(tables)}):")
        for t in tables:
            print(f"   • {t}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
