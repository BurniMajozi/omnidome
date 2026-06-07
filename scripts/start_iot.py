"""Start the IoT service with the correct DATABASE_URL from .env."""
import os
import subprocess
import sys

env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")

# Load .env
with open(env_path) as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

# Re-encode the password properly for asyncpg via SQLAlchemy
# The .env password has %40 for @ which make_url handles, but asyncpg
# needs the URL-encoded form
from urllib.parse import quote, unquote
from sqlalchemy.engine import make_url

raw = os.environ["DATABASE_URL"]
url = make_url(raw)  # This already decodes %40 -> @
# Rebuild with properly encoded password
safe = quote(url.password or "", safe="")
async_url = f"postgresql+asyncpg://{url.username}:{safe}@{url.host}:{url.port}/{url.database}"
os.environ["DATABASE_URL"] = async_url

# Start uvicorn
os.execv(
    sys.executable,
    [sys.executable, "-m", "uvicorn", "services.iot.main:app",
     "--host", "0.0.0.0", "--port", "8006"]
)
