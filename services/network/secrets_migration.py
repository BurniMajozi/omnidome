"""Idempotent schema upgrade + in-place backfill for subscriber secrets.

* Adds the *_enc columns (ALTER ... ADD COLUMN IF NOT EXISTS) under a Postgres advisory lock so
  concurrent workers do not race. create_all() never ALTERs existing tables, hence this module.
* Backfill: legacy rows that still hold PLAINTEXT secrets are encrypted in place IF
  SECRETS_ENCRYPTION_KEY is configured; otherwise they are left untouched and a warning (counts only,
  never values) is logged. Never raises into startup.
"""

from __future__ import annotations

import logging

from sqlalchemy import text, select, or_
from sqlalchemy.orm import Session

from services.common import secretbox

logger = logging.getLogger("network.secrets_migration")

_LOCK_KEY = 8005_020_001

ALTERS = (
    "ALTER TABLE network_radius_accounts ADD COLUMN IF NOT EXISTS password_enc TEXT",
    "ALTER TABLE ont_provisioning_profiles ADD COLUMN IF NOT EXISTS loid_password_enc TEXT",
    "ALTER TABLE wifi_config_profiles ADD COLUMN IF NOT EXISTS passphrase_enc TEXT",
    "ALTER TABLE wifi_config_profiles ADD COLUMN IF NOT EXISTS guest_ssid_passphrase_enc TEXT",
)
_TABLES = ("network_radius_accounts", "ont_provisioning_profiles", "wifi_config_profiles")


def apply_alters(engine) -> None:
    """Locked, idempotent ALTERs. Tables that do not exist yet are skipped (create_all will build them
    with the columns already present)."""
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _LOCK_KEY})
        for table, ddl in (
            ("network_radius_accounts", ALTERS[0]),
            ("ont_provisioning_profiles", ALTERS[1]),
            ("wifi_config_profiles", ALTERS[2]),
            ("wifi_config_profiles", ALTERS[3]),
        ):
            if conn.execute(text("SELECT to_regclass(:t)"), {"t": table}).scalar():
                conn.execute(text(ddl))


def apply_enum_values(engine) -> None:
    """ADD VALUE cannot run inside a transaction on older Postgres: use an AUTOCOMMIT connection."""
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        if conn.execute(text("SELECT 1 FROM pg_type WHERE typname = 'notification_status'")).scalar():
            for val in ("queued_not_sent", "skipped_no_provider"):
                conn.execute(text(f"ALTER TYPE notification_status ADD VALUE IF NOT EXISTS '{val}'"))


def backfill_plaintext(session: Session) -> dict:
    """Encrypt legacy plaintext secrets in place. Returns counts (never values)."""
    from services.network.models import RadiusAccount, ONTProvisioningProfile, WiFiConfigProfile

    stats = {"radius": 0, "ont": 0, "wifi": 0, "skipped_no_key": 0}
    radius = session.execute(
        select(RadiusAccount).where(RadiusAccount.password_enc.is_(None),
                                    ~RadiusAccount.password_hash.like(secretbox.HASH_PREFIX + "%"))
    ).scalars().all()
    ont = session.execute(
        select(ONTProvisioningProfile).where(ONTProvisioningProfile.loid_password.is_not(None))
    ).scalars().all()
    wifi = session.execute(
        select(WiFiConfigProfile).where(or_(WiFiConfigProfile.passphrase.is_not(None),
                                            WiFiConfigProfile.guest_ssid_passphrase.is_not(None)))
    ).scalars().all()
    pending = len(radius) + len(ont) + len(wifi)
    if not pending:
        return stats
    if not secretbox.is_configured():
        stats["skipped_no_key"] = pending
        logger.error("%d rows still hold PLAINTEXT network secrets and SECRETS_ENCRYPTION_KEY is not configured: "
                     "set it and restart to encrypt them in place", pending)
        return stats
    for a in radius:
        plain = a.password_hash
        a.password_enc = secretbox.encrypt(plain)
        a.password_hash = secretbox.hash_password(plain)
        stats["radius"] += 1
    for o in ont:
        o.loid_password_enc = secretbox.encrypt(o.loid_password)
        o.loid_password = None
        stats["ont"] += 1
    for w in wifi:
        if w.passphrase is not None:
            w.passphrase_enc = secretbox.encrypt(w.passphrase)
            w.passphrase = None
        if w.guest_ssid_passphrase is not None:
            w.guest_ssid_passphrase_enc = secretbox.encrypt(w.guest_ssid_passphrase)
            w.guest_ssid_passphrase = None
        stats["wifi"] += 1
    return stats


def run_secrets_migration() -> None:
    """Blocking; call via run_in_threadpool. Never raises (startup must survive); DB errors propagate
    only from apply_alters' connection so run_with_db_retry can wait for Postgres."""
    from services.common.db import get_engine
    from services.network.database import get_session

    engine = get_engine()
    apply_alters(engine)
    apply_enum_values(engine)
    try:
        from services.network.models import Base
        Base.metadata.tables["network_nas_clients"].create(bind=engine, checkfirst=True)
        with get_session() as session:
            stats = backfill_plaintext(session)
        if any(stats[k] for k in ("radius", "ont", "wifi")):
            logger.info("Encrypted legacy plaintext secrets in place: %s", {k: v for k, v in stats.items()})
    except Exception as exc:  # noqa: BLE001
        logger.error("secret backfill failed (%s); service continues", type(exc).__name__)
