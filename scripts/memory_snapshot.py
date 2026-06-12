from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MEMORY_ROOT = ROOT / "docs" / "omnidome-memory"
BUILD_LOG_DIR = MEMORY_ROOT / "10-build-log"
INDEX = MEMORY_ROOT / "00-index.md"


def run(command: list[str]) -> str:
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception as exc:
        return f"Command failed before execution: {exc}"

    output = completed.stdout.strip()
    error = completed.stderr.strip()
    parts = []
    if output:
        parts.append(output)
    if error:
        parts.append(error)
    if completed.returncode != 0:
        parts.append(f"exit_code={completed.returncode}")
    return "\n".join(parts).strip() or "(no output)"


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "snapshot"


def fenced(command: str, output: str) -> str:
    return f"### `{command}`\n\n```text\n{output}\n```\n"


def update_index(note_path: Path, title: str) -> None:
    if not INDEX.exists():
        return

    rel = note_path.relative_to(MEMORY_ROOT).with_suffix("").as_posix()
    link = f"- [[{rel}|{title}]]"
    text = INDEX.read_text(encoding="utf-8")
    marker = "## Active Build Threads\n\n"

    if link in text or marker not in text:
        return

    text = text.replace(marker, marker + link + "\n")
    INDEX.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture an OmniDome memory snapshot.")
    parser.add_argument("--title", required=True, help="Short title for this memory note.")
    parser.add_argument("--notes", default="", help="Optional human notes to include.")
    parser.add_argument(
        "--no-compose",
        action="store_true",
        help="Skip docker compose config inspection.",
    )
    args = parser.parse_args()

    now = dt.datetime.now().astimezone()
    date = now.strftime("%Y-%m-%d")
    timestamp = now.strftime("%Y-%m-%d-%H%M%S")
    title = args.title.strip()
    slug = slugify(title)
    note_path = BUILD_LOG_DIR / f"{timestamp}-{slug}.md"

    BUILD_LOG_DIR.mkdir(parents=True, exist_ok=True)

    sections = [
        "---",
        "type: build-log",
        f"date: {date}",
        "area: []",
        "status: captured",
        "---",
        "",
        f"# {title}",
        "",
        "## Notes",
        "",
        args.notes.strip() or "(none provided)",
        "",
        "## Snapshot",
        "",
        fenced("git branch --show-current", run(["git", "branch", "--show-current"])),
        fenced("git rev-parse --short HEAD", run(["git", "rev-parse", "--short", "HEAD"])),
        fenced("git status --short", run(["git", "status", "--short"])),
        fenced("git log --oneline -10", run(["git", "log", "--oneline", "-10"])),
    ]

    if not args.no_compose:
        sections.extend(
            [
                fenced("docker compose config --services", run(["docker", "compose", "config", "--services"])),
                fenced(
                    "docker compose -f docker-compose.production.yml config --services",
                    run(["docker", "compose", "-f", "docker-compose.production.yml", "config", "--services"]),
                ),
            ]
        )

    sections.extend(
        [
            "## Links",
            "",
            "- [[../00-index]]",
            "",
        ]
    )

    note_path.write_text("\n".join(sections), encoding="utf-8")
    update_index(note_path, title)
    print(note_path.relative_to(ROOT).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

