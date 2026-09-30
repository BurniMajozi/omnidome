"""Rate limiter keying and memory bounds (no database needed)."""
import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from fastapi import HTTPException  # noqa: E402
from starlette.requests import Request  # noqa: E402

from services.common.rate_limiter import RateLimiter, identity_key  # noqa: E402


def req(headers=None, host="10.0.0.5"):
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request({"type": "http", "headers": raw, "client": (host, 1234), "method": "GET", "path": "/"})


def hit(limiter, request):
    try:
        asyncio.run(limiter.check(request))
        return 200
    except HTTPException as exc:
        return exc.status_code


def test_buckets_are_per_user_behind_one_proxy_ip():
    limiter = RateLimiter(max_requests=3, window_seconds=60, key_func=identity_key)
    flood = req({"x-user-id": "user-a"})
    assert [hit(limiter, flood) for _ in range(4)] == [200, 200, 200, 429]
    assert hit(limiter, req({"x-user-id": "user-b"})) == 200  # same host, other user: unaffected


def test_falls_back_to_bearer_hash_then_host():
    a, b = req({"authorization": "Bearer aaa"}), req({"authorization": "Bearer bbb"})
    assert identity_key(a) != identity_key(b)
    assert "aaa" not in identity_key(a)  # the token itself is never used as a key
    assert identity_key(req()) == "ip:10.0.0.5"
    limiter = RateLimiter(max_requests=1, window_seconds=60, key_func=identity_key)
    assert hit(limiter, a) == 200 and hit(limiter, a) == 429 and hit(limiter, b) == 200


def test_invite_accept_key_is_not_global():
    limiter = RateLimiter(max_requests=2, window_seconds=60, key_func=identity_key)
    for _ in range(2):
        limiter.check_key("ip:1.1.1.1|tok1")
    with pytest.raises(HTTPException):
        limiter.check_key("ip:1.1.1.1|tok1")
    limiter.check_key("ip:2.2.2.2|tok1")  # different caller unaffected


def test_memory_is_bounded():
    limiter = RateLimiter(max_requests=5, window_seconds=60, max_keys=50)
    for i in range(500):
        limiter.check_key(f"k{i}")
    assert len(limiter._requests) <= 50
