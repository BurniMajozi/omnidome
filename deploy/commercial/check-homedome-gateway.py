"""Run inside IoT: prove private gateway routing without any customer token."""
import os
import urllib.request
import urllib.error
from services.iot.managed_gateway import INTERNAL_URL, check_target

assert os.getenv("HOME_DOME_LOCAL_GATEWAY_ENABLED") == "true"
check_target(INTERNAL_URL)
with urllib.request.urlopen(INTERNAL_URL + "/", timeout=15) as response:
    assert response.status == 200
try:
    urllib.request.urlopen(INTERNAL_URL + "/api/", timeout=15)
    raise AssertionError("Home Assistant should require authentication")
except urllib.error.HTTPError as error:
    assert error.code == 401
print("Private gateway routing: verified. Home Assistant API requires authentication.")
