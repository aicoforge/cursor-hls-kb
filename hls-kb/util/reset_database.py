#!/usr/bin/env python3
# Copyright (c) 2026 AICOFORGE. All rights reserved.
# CC BY-NC 4.0 — non-commercial use only. See LICENSE.
# Commercial use: kevinjan@aicoforge.com
"""
HLS Knowledge Base - Database Reset Tool
Used to clear all data and re-initialize
"""

import asyncio
import asyncpg
import os
import sys

# ==================== Configuration (from environment) ====================
DB_USER = os.getenv("DB_ADMIN", "admin")
DB_PASS = os.getenv("DB_ADMIN_PASS", "admin_passwd")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "hls_knowledge")

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

async def reset_database(confirm: bool = False):
    """Reset database (clear all data)"""
    
    if not confirm:
        print("=" * 60)
        print("❗️  Warning: This operation will delete all data!")
        print("=" * 60)
        print("\nThe following tables will be cleared:")
        print("  - rules_effectiveness")
        print("  - synthesis_results")
        print("  - design_iterations")
        print("  - projects")
        print("  - hls_rules")
        print()
        
        response = input("Are you sure you want to continue? (yes/no): ").strip().lower()
        if response not in ['yes', 'y']:
            print("Operation cancelled")
            return False
    
    print("\nStarting database reset...")
    
    conn = await asyncpg.connect(DATABASE_URL)
    
    try:
        # Delete data in foreign key dependency order
        tables = [
            'rules_effectiveness',
            'synthesis_results',
            'design_iterations',
            'projects',
            'hls_rules'
        ]
        
        for table in tables:
            count = await conn.fetchval(f"SELECT COUNT(*) FROM {table}")
            await conn.execute(f"DELETE FROM {table}")
            print(f"  ✓ Cleared {table} ({count} record(s))")
        
        print("\n✓ Database has been reset!")
        print("\nNext steps:")
        print("  Run import_hls_rules.py to import rules")
        
        return True
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        return False
    
    finally:
        await conn.close()

async def show_stats():
    """Show current database statistics"""
    print("=" * 60)
    print("Current Database Statistics")
    print("=" * 60)
    
    conn = await asyncpg.connect(DATABASE_URL)
    
    try:
        stats = {
            'projects': await conn.fetchval("SELECT COUNT(*) FROM projects"),
            'hls_rules': await conn.fetchval("SELECT COUNT(*) FROM hls_rules"),
            'design_iterations': await conn.fetchval("SELECT COUNT(*) FROM design_iterations"),
            'synthesis_results': await conn.fetchval("SELECT COUNT(*) FROM synthesis_results"),
            'rules_effectiveness': await conn.fetchval("SELECT COUNT(*) FROM rules_effectiveness"),
        }
        
        print()
        for table, count in stats.items():
            print(f"  {table:<25} {count:>10} record(s)")
        print()
        
        total = sum(stats.values())
        if total == 0:
            print("  Database is empty, ready to start importing data")
        else:
            print(f"  Total: {total} record(s)")
        print()
        
    finally:
        await conn.close()

async def main():
    """Main function"""
    if len(sys.argv) > 1 and sys.argv[1] == '--stats':
        # Show statistics only
        await show_stats()
        return
    
    # Show statistics first
    await show_stats()
    
    # Execute reset
    success = await reset_database()
    
    if success:
        # Show statistics again after reset
        print()
        await show_stats()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nOperation cancelled")
