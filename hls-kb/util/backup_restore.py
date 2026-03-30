#!/usr/bin/env python3
# Copyright (c) 2026 AICOFORGE. All rights reserved.
# CC BY-NC 4.0 — non-commercial use only. See LICENSE.
# Commercial use: kevinjan@aicoforge.com
"""
HLS Knowledge Base - Backup and Restore Tool

Functions:
  1. Create full backup (SQL)
  2. List all backups
  3. Restore backup (clears database first, then restores)

Usage:
  python3 backup_restore.py backup           # Create SQL backup
  python3 backup_restore.py list             # List all backups
  python3 backup_restore.py restore <file>   # Restore backup
"""

import subprocess
import sys
import os
import json
import asyncio
import asyncpg
from datetime import datetime
from pathlib import Path

# ==================== Configuration (from environment) ====================
SCRIPT_DIR = Path(__file__).parent.resolve()
BACKUP_DIR = SCRIPT_DIR / "backups"

DB_USER = os.getenv("DB_ADMIN",      "admin")
DB_PASS = os.getenv("DB_ADMIN_PASS", "admin_passwd")
DB_HOST = os.getenv("DB_HOST",       "localhost")
DB_PORT = os.getenv("DB_PORT",       "5432")
DB_NAME = os.getenv("DB_NAME",       "hls_knowledge")

# Container name derived from DB_NAME (consistent with docker-compose.yml)
CONTAINER_NAME = os.getenv("CONTAINER_DB", f"{DB_NAME}-db")

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Delete order respects foreign key constraints
TABLES = [
    "rules_effectiveness",
    "synthesis_results",
    "design_iterations",
    "projects",
    "hls_rules",
]

BACKUP_DIR.mkdir(exist_ok=True, parents=True)

# ==================== Color Output ====================
class C:
    G = '\033[92m'  # Green
    R = '\033[91m'  # Red
    Y = '\033[93m'  # Yellow
    B = '\033[94m'  # Blue
    N = '\033[0m'   # Normal

def success(msg): print(f"{C.G}✓ {msg}{C.N}")
def error(msg):   print(f"{C.R}✗ {msg}{C.N}")
def warning(msg): print(f"{C.Y}❗ {msg}{C.N}")
def info(msg):    print(f"{C.B}→ {msg}{C.N}")
def header(msg):  print(f"\n{'='*70}\n{msg}\n{'='*70}\n")

# ==================== Helper Functions ====================

async def get_db_stats():
    """Get database statistics via asyncpg"""
    stats = {}
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        for table in TABLES:
            stats[table] = await conn.fetchval(f"SELECT COUNT(*) FROM {table}")
    finally:
        await conn.close()
    return stats

# ==================== Backup Functions ====================

def backup_sql():
    """Create full backup (data only, schema/permissions untouched on restore)"""
    header("Create Full Backup (SQL)")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = BACKUP_DIR / f"hls_kb_full_{timestamp}.sql"

    info(f"Backup file: {backup_file.name}")
    print()

    try:
        info("Backing up database...")
        # --data-only: schema and permissions are managed by init.sql, not the backup
        cmd = f"docker exec {CONTAINER_NAME} pg_dump -U {DB_USER} --data-only {DB_NAME}"
        result = subprocess.run(cmd.split(), capture_output=True, text=True, check=True)

        with open(backup_file, 'w') as f:
            f.write(result.stdout)

        size_kb = backup_file.stat().st_size / 1024

        print()
        success(f"Backup complete!")
        print(f"\n  File: {backup_file}")
        print(f"  Size: {size_kb:.1f} KB\n")

        stats = asyncio.run(get_db_stats())
        print("  Contents:")
        for table, count in stats.items():
            print(f"    • {table:25} {count:>5} record(s)")

        metadata = {
            "backup_time": timestamp,
            "backup_type": "sql",
            "file": str(backup_file),
            "size_kb": size_kb,
            "stats": stats
        }
        metadata_file = backup_file.with_suffix('.json')
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        print()
        success(f"Metadata: {metadata_file.name}")

        return True

    except Exception as e:
        error(f"Backup failed: {e}")
        return False

def list_backups():
    """List all backups"""
    header("Backup File List")

    sql_backups = sorted(BACKUP_DIR.glob("hls_kb_*.sql"), key=lambda p: p.stat().st_mtime, reverse=True)

    if not sql_backups:
        warning("No backup files found")
        print(f"Backup directory: {BACKUP_DIR}\n")
        return

    print(f"Backup directory: {BACKUP_DIR}")
    print(f"Found {len(sql_backups)} backup file(s)\n")

    print(f"{'#':<4} {'Filename':<50} {'Size':<10} {'Date':<20}")
    print("-" * 85)

    for i, backup in enumerate(sql_backups, 1):
        size_kb = backup.stat().st_size / 1024
        mtime = datetime.fromtimestamp(backup.stat().st_mtime)

        print(f"{i:<4} {backup.name:<50} {size_kb:>6.1f} KB  {mtime.strftime('%Y-%m-%d %H:%M:%S')}")

        metadata_file = backup.with_suffix('.json')
        if metadata_file.exists():
            try:
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
                if 'stats' in metadata:
                    total = sum(v for v in metadata['stats'].values() if isinstance(v, int))
                    print(f"     └─ {total} total record(s)")
            except:
                pass

    print()
    info("Restore usage: python3 backup_restore.py restore <filename>")

async def _restore_async(backup_path: Path) -> bool:
    """Restore backup via asyncpg: DELETE all data, then psql to reload"""
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        # Clear all data in FK-safe order (silently, no schema/permission changes)
        async with conn.transaction():
            for table in TABLES:
                await conn.execute(f"DELETE FROM {table}")
    finally:
        await conn.close()

    # Restore data via psql (data-only SQL, no DDL, no permission changes)
    with open(backup_path, 'r') as f:
        sql_content = f.read()

    cmd = f"docker exec -i {CONTAINER_NAME} psql -U {DB_USER} -d {DB_NAME}"
    subprocess.run(
        cmd.split(),
        input=sql_content,
        text=True,
        check=True,
        capture_output=True
    )

    return True

def restore_backup(backup_file):
    """Restore backup (clears database first, then restores)"""
    header("Restore Database")

    # Find file
    backup_path = Path(backup_file)
    if not backup_path.exists():
        backup_path = BACKUP_DIR / backup_file
        if not backup_path.exists():
            error(f"File not found: {backup_file}")
            return False

    # Validate type
    if backup_path.suffix != '.sql':
        error(f"Only SQL backup files (.sql) are supported, received: {backup_path.suffix}")
        return False

    # Show info
    size_kb = backup_path.stat().st_size / 1024
    print(f"  File: {backup_path.name}")
    print(f"  Size: {size_kb:.1f} KB\n")

    # Confirm
    warning("This operation will overwrite the current database!")
    confirm = input("Are you sure you want to restore? (yes/no): ").strip().lower()

    if confirm != 'yes':
        info("Operation cancelled")
        return False

    print()

    try:
        info("Restoring SQL backup...")

        asyncio.run(_restore_async(backup_path))

        print()
        success("Restore complete!")
        print()

        stats = asyncio.run(get_db_stats())
        print("  Post-restore statistics:")
        for table, count in stats.items():
            print(f"    • {table:25} {count:>5} record(s)")

        return True

    except subprocess.CalledProcessError as e:
        error(f"Restore failed: {e}")
        if e.stderr:
            print(f"\nError details:\n{e.stderr[:500]}")
        return False
    except Exception as e:
        error(f"Restore failed: {e}")
        import traceback
        traceback.print_exc()
        return False

# ==================== Main ====================

def show_usage():
    print("""
HLS Knowledge Base - Backup and Restore Tool (v1.0)

Usage:
  python3 backup_restore.py backup           Create full backup (SQL)
  python3 backup_restore.py list             List all backups
  python3 backup_restore.py restore <file>   Restore backup (clears database first)

Examples:
  # Create backup
  python3 backup_restore.py backup

  # View backups
  python3 backup_restore.py list

  # Restore backup
  python3 backup_restore.py restore hls_kb_full_20251013_153225.sql
    """)

def main():
    if len(sys.argv) < 2:
        show_usage()
        return

    command = sys.argv[1]

    if command == 'backup':
        success_flag = backup_sql()
        sys.exit(0 if success_flag else 1)

    elif command == 'list':
        list_backups()

    elif command == 'restore':
        if len(sys.argv) < 3:
            error("Please specify a backup file")
            print("Usage: python3 backup_restore.py restore <file>")
            sys.exit(1)

        success_flag = restore_backup(sys.argv[2])
        sys.exit(0 if success_flag else 1)

    else:
        error(f"Unknown command: {command}")
        show_usage()
        sys.exit(1)

if __name__ == "__main__":
    main()