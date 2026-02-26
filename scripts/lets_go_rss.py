#!/usr/bin/env python3
"""
Let's Go RSS - Main entry point
Lightweight RSS subscription manager for multiple platforms.
"""

import sys
import os
from pathlib import Path
from typing import Any, Dict
import click

from rss_engine import add, list_sub, stats, update

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

# Resolve directories relative to this script
SKILL_DIR = Path(__file__).parent.parent
SCRIPTS_DIR = SKILL_DIR / "scripts"
ASSETS_DIR = SKILL_DIR / "assets"

# Add scripts directory to Python path
sys.path.insert(0, str(SCRIPTS_DIR))

# Ensure assets directory exists
ASSETS_DIR.mkdir(exist_ok=True)

def initialize_database():
    """Initialize database if it doesn't exist"""
    skill_dir = Path(__file__).parent.parent
    assets_dir = skill_dir / "assets"
    db_path = assets_dir / "rss_database.db"

    if not db_path.exists():
        print("\n🔧 Initializing database...")
        sys.path.insert(0, str(Path(__file__).parent))
        from database import RSSDatabase

        # Create database
        _db = RSSDatabase(str(db_path))
        print("✅ Database initialized")


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.pass_context
def cli(ctx: click.Context) -> None:
    """Lets-Go-RSS CLI."""
    initialize_database()
    db_path = str(ASSETS_DIR / "rss_database.db")
    os.environ.setdefault("RSS_ASSETS_DIR", str(ASSETS_DIR))
    ctx.obj = {"db_path": db_path}

@click.command("status", help="Read cached report (for bot push, no fetching)")
@click.pass_obj
def status(obj: Dict[str, Any]):
    db_path = obj["db_path"]
    report_path = os.path.join(os.path.dirname(db_path) or ".", "latest_update.md")
    if os.path.exists(report_path):
        with open(report_path, "r", encoding="utf-8") as f:
            print(f.read())
    else:
        print("⚠️ 尚无缓存报告。请先运行 --update 生成。")
    return

cli.add_command(status)
cli.add_command(list_sub)
cli.add_command(add)
cli.add_command(stats)
cli.add_command(update)
if __name__ == "__main__":
    cli()
