"""Run Alembic migrations for every service that has them.

Intentionally NOT wired into any Dockerfile's CMD — running migrations as
part of container boot risks N replicas racing to apply the same migration
concurrently. Run this once, as its own deploy step, before rolling out new
service images.

Usage:
    DATABASE_URL=postgresql://admin:change_me@localhost:5432/coreconnect \
        python scripts/migrate.py [service ...]

With no arguments, runs every migrated service in turn. Each service keeps
its own Alembic history (a service-scoped alembic_version_<service> table)
since all services share one physical database — see the env.py in each
service's migrations/ directory for why.
"""
import subprocess
import sys

MIGRATED_SERVICES = ["finance", "billing", "inventory"]


def run(service: str) -> None:
    print(f"\n=== {service}: alembic upgrade head ===")
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", f"services/{service}/alembic.ini", "upgrade", "head"],
        check=False,
    )
    if result.returncode != 0:
        print(f"!!! {service} migration failed (exit {result.returncode})", file=sys.stderr)
        sys.exit(result.returncode)


if __name__ == "__main__":
    targets = sys.argv[1:] or MIGRATED_SERVICES
    unknown = set(targets) - set(MIGRATED_SERVICES)
    if unknown:
        print(f"Unknown service(s): {unknown}. Known: {MIGRATED_SERVICES}", file=sys.stderr)
        sys.exit(1)
    for svc in targets:
        run(svc)
    print("\nAll migrations applied successfully.")
