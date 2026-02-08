import os
from functools import lru_cache

from fastapi import HTTPException, status
from sqlalchemy import create_engine


@lru_cache
def get_engine():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DATABASE_URL not configured",
        )
    return create_engine(db_url, pool_pre_ping=True)
