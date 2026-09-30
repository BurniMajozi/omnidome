"""Analytics worker: failures must not look fresh; multi-platform posts keep one row per platform."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))

from contextlib import contextmanager  # noqa: E402

from services.analytics_worker import sync  # noqa: E402


class Conn:
    def __init__(self, log):
        self.log = log

    def execute(self, stmt, params=None):
        self.log.append((str(stmt), params))


def engine(log):
    class E:
        @contextmanager
        def begin(self):
            yield Conn(log)
    return E()


def test_failure_does_not_stamp_last_sync(monkeypatch):
    log = []
    monkeypatch.setattr(sync, "get_engine", lambda: engine(log))
    monkeypatch.setattr(sync, "_STATE_COLS_READY", True)
    sync._mark_state("t", "p", "last_hot_sync", error="boom")
    q = log[-1][0]
    assert "last_hot_sync" not in q and "last_error_at" in q and "last_attempt_at" in q
    sync._mark_state("t", "p", "last_hot_sync")
    ok = log[-1][0]
    assert "last_hot_sync = now()" in ok and "last_error = NULL" in ok


def test_multi_platform_post_gets_a_row_per_platform(monkeypatch):
    log = []
    monkeypatch.setattr(sync, "get_engine", lambda: engine(log))
    posts = [{"_id": "p1", "analytics": {"likes": 10},
              "platforms": [{"platform": "instagram"}, {"platform": "facebook"}]}]
    assert sync._upsert_posts("t", "prof", posts) == 2
    rows = log[-1][1]
    assert [r["platform"] for r in rows] == ["instagram", "facebook"]
    assert [r["likes"] for r in rows] == [10, 0]  # aggregate attributed once, never duplicated
    per = [{"_id": "p2", "platforms": [{"platform": "instagram", "analytics": {"likes": 3}},
                                        {"platform": "facebook", "analytics": {"likes": 4}}]}]
    sync._upsert_posts("t", "prof", per)
    assert [r["likes"] for r in log[-1][1]] == [3, 4]
