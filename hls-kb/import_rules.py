#!/usr/bin/env python3
# Copyright (c) 2026 AICOFORGE. All rights reserved.
# CC BY-NC 4.0 — non-commercial use only. See LICENSE.
# Commercial use: kevinjan@aicoforge.com
"""
HLS Knowledge Base - Rule Import Tool

Usage:
  python import_rules.py --type official   # Import rules_ug1399.txt (official rules)
  python import_rules.py --type user       # Import rules_user_defined.txt (user-defined rules)
  python import_rules.py --type all        # Import both types (default)

"""

import asyncio
import asyncpg
import argparse
import os
import re
from uuid import uuid5, UUID, NAMESPACE_DNS
from typing import List, Dict, Optional
from pathlib import Path

# ============================================================================
# Database Connection (from environment variables)
# ============================================================================
DB_USER = os.getenv("DB_ADMIN", "admin")
DB_PASS = os.getenv("DB_ADMIN_PASS", "admin_passwd")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "hls_knowledge")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

# ============================================================================
# Deterministic UUID
# ============================================================================
HLS_NAMESPACE = uuid5(NAMESPACE_DNS, "hls-knowledge-base.rules")

def deterministic_uuid(rule_type: str, rule_code: Optional[str], rule_text: str) -> UUID:
    """Generate a deterministic UUID based on rule_type + rule_code/rule_text, ensuring consistent IDs across rebuilds"""
    prefix = "official" if rule_type == "official" else "user_defined"
    key = rule_code if rule_code else rule_text
    return uuid5(HLS_NAMESPACE, f"{prefix}:{key}")

# ============================================================================
# Category Configuration (by rule_type)
# ============================================================================



# ============================================================================
# Shared Utility Functions
# ============================================================================

def determine_priority(rule_text: str) -> int:
    """Determine priority based on keyword strength: 9/7/5/4"""
    t = rule_text.lower()
    if any(kw in t for kw in ['always', 'must', 'critical', 'never']):
        return 9
    if any(kw in t for kw in ['do not', 'avoid', 'ensure', 'should']):
        return 7
    if any(kw in t for kw in ['consider', 'may', 'recommend', 'prefer']):
        return 5
    return 4

# ============================================================================
# Parse Functions (by rule_type)
# ============================================================================

def parse_official_rules(filepath: str) -> List[Dict]:
    """Parse rules_ug1399.txt -> rule_type='official'"""
    print(f"[Parse] {filepath} (official rules)...")

    if not Path(filepath).exists():
        print(f"✗ File not found: {filepath}")
        return []

    content = Path(filepath).read_text(encoding='utf-8')
    rules = []
    current_section = None

    for lineno, line in enumerate(content.split('\n'), 1):
        s = line.strip()
        if not s or s == '---' or s.startswith('alwaysApply:'):
            continue

        # Section/category comment: # Category: Dataflow ...
        if s.startswith('#'):
            if 'category:' in s.lower():
                m = re.search(r'category:\s*(\w+)', s, re.IGNORECASE)
                if m:
                    current_section = m.group(1).lower()
            continue

        # Rule line: - [R001] text  or  - text
        if s.startswith('- '):
            rule_text = s[2:].strip()
            if len(rule_text) < 10:
                continue

            rule_code = None
            if rule_text.startswith('[R') and ']' in rule_text:
                end = rule_text.index(']')
                rule_code = rule_text[1:end]          # e.g. R001
                rule_text = rule_text[end + 1:].strip()

            category = current_section or 'general'

            rules.append({
                'rule_code':   rule_code,
                'rule_text':   rule_text,
                'category':    category,
                'priority':    determine_priority(rule_text),
                'description': f'Official rule (line {lineno}) from {filepath}',
                'source':      'UG1399',
                'rule_type':   'official',
            })

    _print_stats(rules, 'official rules')
    return rules


def parse_user_defined(filepath: str) -> List[Dict]:
    """Parse rules_user_defined.txt -> rule_type='user_defined'"""
    print(f"[Parse] {filepath} (user-defined rules)...")

    if not Path(filepath).exists():
        print(f"✗ File not found: {filepath}")
        return []

    content = Path(filepath).read_text(encoding='utf-8')
    rules = []
    current_section = None

    for lineno, line in enumerate(content.split('\n'), 1):
        s = line.strip()
        if not s or s == '---' or s.startswith('alwaysApply:'):
            continue

        # Section/category comment
        if s.startswith('#'):
            if 'category:' in s.lower():
                m = re.search(r'category:\s*(\w+)', s, re.IGNORECASE)
                if m:
                    current_section = m.group(1).lower()
            continue

        # Rule line: - [P001] text
        if s.startswith('- [P') and ']' in s:
            end = s.index(']')
            rule_code = s[3:end]           # e.g. P001
            rule_text = s[end + 1:].strip()
            if len(rule_text) < 10:
                continue

            category = current_section or 'optimization'

            rules.append({
                'rule_code':   rule_code,
                'rule_text':   rule_text,
                'category':    category,
                'priority':    determine_priority(rule_text),
                'description': f'User-defined {rule_code} from {filepath} (line {lineno})',
                'source':      'User',
                'rule_type':   'user_defined',
            })

    _print_stats(rules, 'user-defined rules')
    return rules


def _print_stats(rules: List[Dict], label: str):
    print(f"✓ Parsing complete, found {len(rules)} {label}")
    stats: dict = {}
    for r in rules:
        stats[r['category']] = stats.get(r['category'], 0) + 1
    for cat, cnt in sorted(stats.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {cnt}")
    print()

# ============================================================================
# Import to Database (generic)
# ============================================================================

async def import_rules_to_db(rules: List[Dict], mode: str = 'upsert'):
    """
    Generic import function; rule_type is already included in each rule dict.

    mode:
      upsert  - Update if exists (default)
      skip    - Skip if exists
      replace - Delete all records of the same rule_type first, then re-insert
    """
    if not rules:
        return

    rule_type = rules[0]['rule_type']
    print(f"[Import] rule_type={rule_type}, total {len(rules)} rule(s) (mode={mode})...")

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        if mode == 'replace':
            print(f"  Clearing existing records with rule_type='{rule_type}'...")
            await conn.execute("""
                DELETE FROM rules_effectiveness
                WHERE rule_id IN (SELECT id FROM hls_rules WHERE rule_type = $1)
            """, rule_type)
            await conn.execute("DELETE FROM hls_rules WHERE rule_type = $1", rule_type)
            print("  ✓ Cleared\n")

        inserted = updated = skipped = 0

        for rule in rules:
            try:
                rule_id = deterministic_uuid(rule['rule_type'], rule.get('rule_code'), rule['rule_text'])

                # Look up existing record
                existing_id = None
                if rule.get('rule_code'):
                    existing_id = await conn.fetchval(
                        "SELECT id FROM hls_rules WHERE rule_code = $1 AND rule_type = $2",
                        rule['rule_code'], rule_type
                    )
                if not existing_id:
                    existing_id = await conn.fetchval(
                        "SELECT id FROM hls_rules WHERE rule_text = $1 AND rule_type = $2",
                        rule['rule_text'], rule_type
                    )

                if existing_id:
                    if mode == 'skip':
                        skipped += 1
                        continue
                    # upsert / replace (replace already cleared, won't reach here)
                    await conn.execute("""
                        UPDATE hls_rules
                        SET rule_code = $1, category = $2, priority = $3,
                            description = $4, source = $5
                        WHERE id = $6
                    """, rule.get('rule_code'), rule['category'], rule['priority'],
                        rule['description'], rule['source'], existing_id)
                    updated += 1
                else:
                    await conn.execute("""
                        INSERT INTO hls_rules
                            (id, rule_code, rule_type, rule_text, category, priority, description, source)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    """, rule_id, rule.get('rule_code'), rule_type, rule['rule_text'],
                        rule['category'], rule['priority'], rule['description'], rule['source'])
                    inserted += 1

            except Exception as e:
                print(f"  ✗ {rule.get('rule_code', '?')} - {rule['rule_text'][:50]}... ({e})")
                skipped += 1

        print(f"\n{'='*60}")
        print(f"✓ Inserted {inserted}  Updated {updated}  Skipped {skipped}")
        print(f"{'='*60}\n")

        # Statistics
        stats = await conn.fetch("""
            SELECT category, COUNT(*) as cnt, ROUND(AVG(priority),2) as avg_p
            FROM hls_rules WHERE rule_type = $1
            GROUP BY category ORDER BY cnt DESC
        """, rule_type)

        print(f"Database statistics (rule_type={rule_type}):")
        print(f"  {'Category':<20} {'Count':<8} {'Avg Priority'}")
        print("  " + "-"*40)
        for row in stats:
            print(f"  {row['category']:<20} {row['cnt']:<8} {row['avg_p']}")
        total = await conn.fetchval("SELECT COUNT(*) FROM hls_rules WHERE rule_type=$1", rule_type)
        print(f"  {'Total':<20} {total}\n")

    finally:
        await conn.close()

# ============================================================================
# Verify & Summary
# ============================================================================

async def verify_import(rule_type: Optional[str] = None):
    """Verify import results; rule_type=None shows all"""
    label = rule_type or 'all'
    print(f"[Verify] rule_type={label}...")
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        where = "WHERE rule_type = $1" if rule_type else ""
        params = [rule_type] if rule_type else []

        total = await conn.fetchval(f"SELECT COUNT(*) FROM hls_rules {where}", *params)
        print(f"  Total rules: {total}")

        high = await conn.fetch(f"""
            SELECT rule_code, category, rule_text
            FROM hls_rules {where} {'AND' if where else 'WHERE'} priority >= 9
            ORDER BY category, rule_code LIMIT 10
        """, *params)

        print(f"  High-priority rules (top 10):")
        for i, r in enumerate(high, 1):
            preview = r['rule_text'][:65] + ('...' if len(r['rule_text']) > 65 else '')
            print(f"    {i}. [{r['rule_code'] or '?'}] [{r['category']}] {preview}")

        dist = await conn.fetch(f"""
            SELECT category, COUNT(*) as cnt FROM hls_rules {where}
            GROUP BY category ORDER BY cnt DESC
        """, *params)
        print("  Category distribution:")
        for row in dist:
            bar = "█" * min(row['cnt'] // 3, 40)
            print(f"    {row['category']:<20} {bar} ({row['cnt']})")
        print()
    finally:
        await conn.close()


async def export_summary(rule_type: Optional[str], output_file: str):
    """Export summary to text file"""
    print(f"[Summary] Generating {output_file}...")
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        where = "WHERE rule_type = $1" if rule_type else ""
        params = [rule_type] if rule_type else []

        stats = await conn.fetch(f"""
            SELECT category,
                   COUNT(*) as cnt,
                   MIN(priority) as min_p,
                   MAX(priority) as max_p,
                   ROUND(AVG(priority),2) as avg_p
            FROM hls_rules {where}
            GROUP BY category ORDER BY cnt DESC
        """, *params)

        total = await conn.fetchval(f"SELECT COUNT(*) FROM hls_rules {where}", *params)

        with open(output_file, 'w', encoding='utf-8') as f:
            title = f"HLS Knowledge Base - Import Summary ({rule_type or 'all'})"
            f.write(title + '\n' + '=' * 70 + '\n\n')
            f.write(f"Total: {total}\n\n")
            f.write(f"{'Category':<20} {'Count':<8} {'Range':<12} {'Avg'}\n")
            f.write('-' * 55 + '\n')
            for row in stats:
                f.write(f"{row['category']:<20} {row['cnt']:<8} "
                        f"{row['min_p']}-{row['max_p']:<9} {row['avg_p']}\n")
            f.write('-' * 55 + '\n')

        print(f"✓ Summary saved to: {output_file}\n")
    finally:
        await conn.close()

# ============================================================================
# Main
# ============================================================================

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='HLS Knowledge Base - Unified Rule Import Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python import_rules.py                          # Import both types (all, upsert)
  python import_rules.py --type official          # Import official rules only
  python import_rules.py --type user              # Import user-defined rules only
        """
    )
    parser.add_argument(
        '--type', choices=['official', 'user', 'all'], default='all',
        help='Rule type to import (default: all)'
    )
    parser.add_argument(
        '--no-verify', action='store_true',
        help='Skip verification step'
    )
    parser.add_argument(
        '--no-summary', action='store_true',
        help='Skip summary file generation'
    )
    return parser


async def run(args):
    print("=" * 70)
    print("HLS Knowledge Base - Unified Rule Import Tool")
    print(f"  type={args.type}")
    print(f"  DB: {DB_HOST}:{DB_PORT}/{DB_NAME} (user={DB_USER})")
    print("=" * 70 + "\n")

    tasks = []

    # --- Determine which imports to run ---
    run_official = args.type in ('official', 'all')
    run_user     = args.type in ('user', 'all')

    # --- Official rules ---
    if run_official:
        filepath = "rules_ug1399.txt"
        official_rules = parse_official_rules(filepath)
        if official_rules:
            try:
                await import_rules_to_db(official_rules, mode='upsert')
            except Exception as e:
                print(f"✗ Official rules import failed: {e}")

    # --- User-defined rules ---
    if run_user:
        filepath = "rules_user_defined.txt"
        user_rules = parse_user_defined(filepath)
        if user_rules:
            try:
                await import_rules_to_db(user_rules, mode='upsert')
            except Exception as e:
                print(f"✗ User-defined rules import failed: {e}")

    # --- Verify ---
    if not args.no_verify:
        verify_type = None if args.type == 'all' else (
            'official' if args.type == 'official' else 'user_defined'
        )
        try:
            await verify_import(verify_type)
        except Exception as e:
            print(f"✗ Verification error: {e}")

    # --- Summary ---
    if not args.no_summary:
        summary_type = None if args.type == 'all' else (
            'official' if args.type == 'official' else 'user_defined'
        )
        summary_file = f"import_summary_{args.type}.txt"
        try:
            await export_summary(summary_type, summary_file)
        except Exception as e:
            print(f"✗ Summary generation error: {e}")

    print("=" * 70)
    print("✓ All operations complete!")
    print("=" * 70)
    print("\nCommon queries:")
    print("  curl 'http://localhost:8000/api/rules/effective?rule_type=official'")
    print("  curl 'http://localhost:8000/api/rules/effective?rule_type=user_defined'")
    print("  curl 'http://localhost:8000/api/rules/effective?min_success_rate=0&category=pipeline'")


if __name__ == "__main__":
    parser = build_arg_parser()
    args = parser.parse_args()
    asyncio.run(run(args))
