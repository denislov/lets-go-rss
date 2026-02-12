#!/usr/bin/env python3
"""
Let's Go RSS - Main entry point
Lightweight RSS subscription manager for multiple platforms.
"""

import sys
import os
from pathlib import Path

# Resolve directories relative to this script
SKILL_DIR = Path(__file__).parent.parent
SCRIPTS_DIR = SKILL_DIR / "scripts"
ASSETS_DIR = SKILL_DIR / "assets"

# Add scripts directory to Python path
sys.path.insert(0, str(SCRIPTS_DIR))

# Ensure assets directory exists
ASSETS_DIR.mkdir(exist_ok=True)


def ensure_dependencies():
    """Check and install dependencies if needed."""
    setup_script = SCRIPTS_DIR / "setup.py"
    if not setup_script.exists():
        return True

    import subprocess
    result = subprocess.run(
        [sys.executable, str(setup_script)],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print("⚠️  Setup check completed with warnings")
        return False
    return True


def print_cached_status() -> int:
    """Print cached report directly without importing engine dependencies."""
    report_path = ASSETS_DIR / "latest_update.md"
    if report_path.exists():
        print(report_path.read_text(encoding="utf-8"))
        return 0
    print("⚠️ 尚无缓存报告。请先运行 --update 生成。")
    return 0


def main():
    """Main entry point — delegates to rss_engine with correct paths."""
    # Fast path: --status should not require runtime scraping dependencies (e.g. httpx).
    if "--status" in sys.argv:
        sys.exit(print_cached_status())

    # Skip setup for --skip-setup (cron jobs)
    skip_setup = '--skip-setup' in sys.argv
    if not skip_setup:
        if not ensure_dependencies():
            print("⚠️  Dependency setup had warnings, continuing anyway...")

    # Remove --skip-setup from argv so argparse doesn't complain
    sys.argv = [a for a in sys.argv if a != '--skip-setup']

    # Pass absolute db_path to engine instead of os.chdir()
    db_path = str(ASSETS_DIR / "rss_database.db")
    os.environ.setdefault("RSS_ASSETS_DIR", str(ASSETS_DIR))

    from rss_engine import main as rss_main
    rss_main(db_path=db_path)


if __name__ == "__main__":
    main()
