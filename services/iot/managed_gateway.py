"""Operator-enabled local gateway. Never accept its internal target from a request."""
import os
from fastapi import HTTPException

INTERNAL_URL = "http://omnidome-home-gateway:8123"
PUBLIC_URL = "http://localhost:8123"


def enabled():
    return os.getenv("HOME_DOME_LOCAL_GATEWAY_ENABLED", "false").lower() == "true"


def check_target(url):
    if not enabled() or url != INTERNAL_URL:
        raise ValueError("Managed gateway target is not enabled")


def target_for(home):
    if not home.managed_gateway_key:
        return None
    if home.managed_gateway_key != "local" or not enabled():
        raise HTTPException(409, "The assigned local gateway is not enabled")
    return INTERNAL_URL
