#!/usr/bin/env python3
# Copyright (c) 2026 AICOFORGE. All rights reserved.
# CC BY-NC 4.0 — non-commercial use only. See LICENSE.
# Commercial use: kevinjan@aicoforge.com
"""
HLS Knowledge Base Logger-Rollback Tool (v1.0)

Precise rollback using _rollback_info stored in design_iterations.reference_metadata.

Functions:
  logger:   Generate rollback log from iteration's _rollback_info
  rollback: Execute precise rollback (UPDATE prev_state / DELETE)

Usage:
  # Generate log for entire project
  python3 logger-rollback.py logger --project FIR128_Optimization

  # Generate log for specific iteration
  python3 logger-rollback.py logger --project FIR128_Optimization --iteration 4

  # Generate log for recent imports (last 1 hour)
  python3 logger-rollback.py logger --recent 1h

  # Execute rollback (with confirmation)
  python3 logger-rollback.py rollback logs/rollback_FIR128_iter4_20251012.yaml

  # Dry run (preview only)
  python3 logger-rollback.py rollback --dry-run logs/rollback_FIR128_iter4_20251012.yaml
"""

import sys
import os
import yaml
import asyncio
import asyncpg
import argparse
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from uuid import UUID

# ==================== Configuration (from environment) ====================
DB_USER = os.getenv("DB_ADMIN", "admin")
DB_PASS = os.getenv("DB_ADMIN_PASS", "admin_passwd")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "hls_knowledge")

DEFAULT_DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

class LoggerRollback:
    """Precise Logger and Rollback Tool (v1.0)"""

    def __init__(self, db_url: str, force: bool = False):
        self.db_url = db_url
        self.conn = None
        self.force = force

    async def connect(self):
        self.conn = await asyncpg.connect(self.db_url)
        print("[✓] Connected to database")

    async def close(self):
        if self.conn:
            await self.conn.close()
            print("[✓] Database connection closed")

    # ========================================================================
    # LOGGER FUNCTIONS
    # ========================================================================

    async def logger_by_project(self, project_name: str, iteration: Optional[int] = None) -> str:
        project = await self.conn.fetchrow(
            "SELECT * FROM projects WHERE name = $1 ORDER BY created_at DESC LIMIT 1",
            project_name
        )
        if not project:
            print(f"[✗] Project not found: {project_name}")
            return None

        project_id = project['id']

        if iteration:
            iterations = await self.conn.fetch(
                "SELECT * FROM design_iterations WHERE project_id = $1 AND iteration_number = $2",
                project_id, iteration
            )
        else:
            iterations = await self.conn.fetch(
                "SELECT * FROM design_iterations WHERE project_id = $1 ORDER BY iteration_number ASC",
                project_id
            )

        if not iterations:
            print(f"[✗] No iterations found for project: {project_name}")
            return None

        iter_entries = []
        has_any_rollback_info = False

        for iter_row in iterations:
            meta_raw = iter_row['reference_metadata']
            meta = None
            if meta_raw:
                if isinstance(meta_raw, str):
                    try:
                        meta = json.loads(meta_raw)
                    except json.JSONDecodeError:
                        meta = None
                elif isinstance(meta_raw, dict):
                    meta = meta_raw

            rollback_info = meta.get("_rollback_info") if meta else None

            synth = await self.conn.fetchrow(
                "SELECT id FROM synthesis_results WHERE iteration_id = $1",
                iter_row['id']
            )

            entry = {
                "iteration_id": str(iter_row['id']),
                "iteration_number": iter_row['iteration_number'],
                "approach": (iter_row['approach_description'] or "")[:80],
                "has_rollback_info": rollback_info is not None,
            }

            if rollback_info:
                has_any_rollback_info = True
                entry["project_created"] = rollback_info.get("project_created", False)
                entry["project_id"] = rollback_info.get("project_id", str(project['id']))
                entry["synthesis_result_id"] = rollback_info.get("synthesis_result_id")
                entry["rules_changes"] = rollback_info.get("rules_changes", [])
            else:
                entry["project_created"] = False
                entry["project_id"] = str(project['id'])
                entry["synthesis_result_id"] = str(synth['id']) if synth else None
                entry["rules_changes"] = []

            iter_entries.append(entry)

        if not has_any_rollback_info:
            print(f"[!] Warning: No iterations have _rollback_info metadata")
            print(f"[!] rules_effectiveness cannot be precisely restored for these iterations")

        log_path = self._generate_log_file(
            project_name=project['name'],
            project_id=str(project['id']),
            project_type=project['type'],
            iteration=iteration,
            iter_entries=iter_entries
        )

        return log_path

    async def logger_recent(self, hours: float = 1.0) -> str:
        cutoff_time = datetime.now() - timedelta(hours=hours)

        iterations = await self.conn.fetch("""
            SELECT di.*, p.name as project_name, p.id as proj_id, p.type as project_type
            FROM design_iterations di
            JOIN projects p ON di.project_id = p.id
            WHERE di.created_at > $1
            ORDER BY di.created_at DESC
        """, cutoff_time)

        if not iterations:
            print(f"[✗] No iterations found in last {hours} hour(s)")
            return None

        projects_map = {}
        for row in iterations:
            pname = row['project_name']
            if pname not in projects_map:
                projects_map[pname] = {
                    "project_id": str(row['proj_id']),
                    "project_type": row['project_type'],
                    "iterations": []
                }

            meta_raw = row['reference_metadata']
            meta = None
            if meta_raw:
                if isinstance(meta_raw, str):
                    try:
                        meta = json.loads(meta_raw)
                    except json.JSONDecodeError:
                        meta = None
                elif isinstance(meta_raw, dict):
                    meta = meta_raw

            rollback_info = meta.get("_rollback_info") if meta else None

            synth = await self.conn.fetchrow(
                "SELECT id FROM synthesis_results WHERE iteration_id = $1",
                row['id']
            )

            entry = {
                "iteration_id": str(row['id']),
                "iteration_number": row['iteration_number'],
                "approach": (row['approach_description'] or "")[:80],
                "has_rollback_info": rollback_info is not None,
                "project_created": rollback_info.get("project_created", False) if rollback_info else False,
                "project_id": (rollback_info.get("project_id") if rollback_info
                               else str(row['proj_id'])),
                "synthesis_result_id": (rollback_info.get("synthesis_result_id") if rollback_info
                                        else (str(synth['id']) if synth else None)),
                "rules_changes": rollback_info.get("rules_changes", []) if rollback_info else []
            }
            projects_map[pname]["iterations"].append(entry)

        all_entries = []
        project_id = None
        project_type = "mixed"
        for pname, pdata in projects_map.items():
            project_id = pdata["project_id"]
            project_type = pdata["project_type"]
            all_entries.extend(pdata["iterations"])

        log_path = self._generate_log_file(
            project_name="RECENT",
            project_id=project_id or "mixed",
            project_type=project_type,
            iteration=None,
            iter_entries=all_entries,
            notes=f"Recent imports from last {hours} hour(s)"
        )

        return log_path

    def _generate_log_file(
        self,
        project_name: str,
        project_id: str,
        project_type: str,
        iteration: Optional[int],
        iter_entries: List[Dict],
        notes: str = ""
    ) -> str:
        logs_dir = Path("logs")
        logs_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if iteration:
            filename = f"rollback_{project_name}_iter{iteration}_{timestamp}.yaml"
        else:
            filename = f"rollback_{project_name}_{timestamp}.yaml"

        log_path = logs_dir / filename

        if self._check_duplicate_log(project_name, iteration) and not self.force:
            existing = list(logs_dir.glob(
                f"rollback_{project_name}_iter{iteration}_*.yaml" if iteration
                else f"rollback_{project_name}_*.yaml"
            ))
            if existing:
                print(f"[!] Warning: Similar log already exists: {existing[0]}")
                response = input("Create new log anyway? [y/N]: ").strip().lower()
                if response not in ['y', 'yes']:
                    print("[!] Log creation cancelled")
                    return None

        log_data = {
            "version": "1.0",
            "project_name": project_name,
            "project_id": project_id,
            "project_type": project_type,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "timestamp": datetime.now().isoformat(),
            "operator": "logger-rollback.py v1.0",
            "notes": notes or f"Auto-generated log for {project_name}",
            "iterations": iter_entries,
            "rollback_status": "pending"
        }

        with open(log_path, 'w', encoding='utf-8') as f:
            yaml.dump(log_data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        print(f"\n[✓] Rollback log created: {log_path}")
        print(f"[✓] Iterations to rollback: {len(iter_entries)}")

        total_rules = sum(len(e.get("rules_changes", [])) for e in iter_entries)
        with_info = sum(1 for e in iter_entries if e.get("has_rollback_info"))
        without_info = len(iter_entries) - with_info
        print(f"[✓] With _rollback_info: {with_info}  |  Without: {without_info}")
        print(f"[✓] Total rules_effectiveness operations: {total_rules}")

        return str(log_path)

    def _check_duplicate_log(self, project_name: str, iteration: Optional[int]) -> bool:
        logs_dir = Path("logs")
        if not logs_dir.exists():
            return False
        pattern = (f"rollback_{project_name}_iter{iteration}_*.yaml" if iteration
                   else f"rollback_{project_name}_*.yaml")
        return len(list(logs_dir.glob(pattern))) > 0

    # ========================================================================
    # ROLLBACK FUNCTIONS
    # ========================================================================

    async def rollback(self, log_file: str, dry_run: bool = False) -> bool:
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                log_data = yaml.safe_load(f)
        except Exception as e:
            print(f"[✗] Failed to read log file: {e}")
            return False

        if log_data.get('rollback_status') == 'completed':
            print("[!] Warning: This log has already been rolled back")
            response = input("Continue anyway? [y/N]: ").strip().lower()
            if response not in ['y', 'yes']:
                return False

        self._display_summary(log_data)

        if dry_run:
            print("\n[!] DRY RUN MODE - No actual changes\n")
            self._dry_run_rollback(log_data)
            return True
        else:
            response = input("\nProceed with rollback? [y/N]: ").strip().lower()
            if response not in ['y', 'yes']:
                print("[!] Rollback cancelled")
                return False

            return await self._execute_rollback(log_data, log_file)

    def _display_summary(self, log_data: Dict):
        print("\n" + "=" * 70)
        print("  ROLLBACK SUMMARY (v1.0 - Precise)")
        print("=" * 70)
        print(f"  Project: {log_data.get('project_name', 'N/A')}")
        print(f"  Project ID: {log_data.get('project_id', 'N/A')}")
        print(f"  Type: {log_data.get('project_type', 'N/A')}")
        print(f"  Date: {log_data.get('date', 'N/A')}")

        iters = log_data.get('iterations', [])
        print(f"\n  Iterations to rollback: {len(iters)}")

        delete_project = False
        for it in iters:
            info_tag = "✓ precise" if it.get("has_rollback_info") else "❗ no _rollback_info"
            rules_count = len(it.get("rules_changes", []))
            print(f"    - iter#{it['iteration_number']}: {it.get('approach', '')[:50]}  [{info_tag}]")
            if rules_count > 0:
                updates = sum(1 for r in it["rules_changes"] if r.get("action") == "update")
                inserts = sum(1 for r in it["rules_changes"] if r.get("action") == "insert")
                print(f"      rules_effectiveness: {updates} UPDATE(restore) + {inserts} DELETE(new)")
            if it.get("project_created"):
                delete_project = True

        if delete_project:
            print(f"\n  ❗ Project(s) will be deleted if no remaining iterations (auto-created)")
        print("=" * 70)

    def _dry_run_rollback(self, log_data: Dict):
        iters = log_data.get('iterations', [])

        print("Rollback operations (reverse iteration order):\n")

        for it in reversed(iters):
            iter_id = it['iteration_id']
            iter_num = it['iteration_number']
            print(f"--- Iteration #{iter_num} ({iter_id[:8]}...) ---")

            if it.get("has_rollback_info"):
                for rc in it.get("rules_changes", []):
                    re_id = rc['re_id']
                    if rc['action'] == 'update':
                        ps = rc['prev_state']
                        print(f"  UPDATE rules_effectiveness SET times_applied={ps['times_applied']}, "
                              f"success_count={ps['success_count']}, "
                              f"avg_ii_improvement={ps['avg_ii_improvement']} "
                              f"WHERE id='{re_id[:8]}...';")
                    elif rc['action'] == 'insert':
                        print(f"  DELETE FROM rules_effectiveness WHERE id='{re_id[:8]}...';")
            else:
                print(f"  [SKIP] No _rollback_info — rules_effectiveness not touched")

            sr_id = it.get('synthesis_result_id')
            if sr_id:
                print(f"  DELETE FROM synthesis_results WHERE id='{sr_id[:8]}...';")

            print(f"  DELETE FROM design_iterations WHERE id='{iter_id[:8]}...';")

        # Unified project cleanup preview (mirrors _execute_rollback behaviour)
        dry_project_ids = {
            it["project_id"] for it in iters
            if it.get("project_id") and it["project_id"] != "mixed"
        }
        if dry_project_ids:
            print(f"\n--- Project cleanup (unified, after all iterations deleted) ---")
            for pid_str in dry_project_ids:
                print(f"  DELETE FROM projects WHERE id='{pid_str[:8]}...';"
                      f"  (only if no remaining iterations)")

    async def _execute_rollback(self, log_data: Dict, log_file: str) -> bool:
        iters = log_data.get('iterations', [])
        project_id_str = log_data.get('project_id')
        project_id = UUID(project_id_str) if project_id_str and project_id_str != "mixed" else None

        # Collect all affected project IDs upfront for unified cleanup after iteration deletion.
        # Fixes bug: when project_created=True iteration is outside this rollback batch
        # (e.g. logger_recent spanning multiple projects), empty projects were never deleted.
        affected_project_ids: set = set()
        for it in iters:
            pid_str = it.get("project_id")
            if pid_str and pid_str != "mixed":
                try:
                    affected_project_ids.add(UUID(pid_str))
                except (ValueError, AttributeError):
                    pass

        try:
            async with self.conn.transaction():
                print("\n[✓] Starting rollback transaction...\n")

                for it in reversed(iters):
                    iter_id = UUID(it['iteration_id'])
                    iter_num = it['iteration_number']
                    print(f"--- Iteration #{iter_num} ---")

                    # Step 1: Restore rules_effectiveness
                    if it.get("has_rollback_info"):
                        for rc in it.get("rules_changes", []):
                            re_id = UUID(rc['re_id'])

                            if rc['action'] == 'update':
                                ps = rc['prev_state']
                                last_applied = None
                                if ps.get('last_applied_at'):
                                    try:
                                        last_applied = datetime.fromisoformat(ps['last_applied_at'])
                                    except (ValueError, TypeError):
                                        last_applied = None

                                await self.conn.execute("""
                                    UPDATE rules_effectiveness
                                    SET times_applied = $1, success_count = $2,
                                        avg_ii_improvement = $3, last_applied_at = $4
                                    WHERE id = $5
                                """, ps['times_applied'], ps['success_count'],
                                    ps['avg_ii_improvement'], last_applied, re_id)
                                print(f"  [✓] RESTORED rules_effectiveness {str(re_id)[:8]}... "
                                      f"(applied={ps['times_applied']}, success={ps['success_count']})")

                            elif rc['action'] == 'insert':
                                await self.conn.execute(
                                    "DELETE FROM rules_effectiveness WHERE id = $1", re_id
                                )
                                print(f"  [✓] DELETED rules_effectiveness {str(re_id)[:8]}... (was new insert)")
                    else:
                        print(f"  [SKIP] No _rollback_info — rules_effectiveness not touched")

                    # Step 2: Delete synthesis_results
                    sr_id_str = it.get('synthesis_result_id')
                    if sr_id_str:
                        await self.conn.execute(
                            "DELETE FROM synthesis_results WHERE id = $1", UUID(sr_id_str)
                        )
                        print(f"  [✓] DELETED synthesis_results {sr_id_str[:8]}...")
                    else:
                        deleted = await self.conn.execute(
                            "DELETE FROM synthesis_results WHERE iteration_id = $1", iter_id
                        )
                        count = int(deleted.split()[-1]) if deleted else 0
                        if count > 0:
                            print(f"  [✓] DELETED {count} synthesis_results by iteration_id")

                    # Step 3: Delete design_iteration
                    await self.conn.execute(
                        "DELETE FROM design_iterations WHERE id = $1", iter_id
                    )
                    print(f"  [✓] DELETED design_iterations {str(iter_id)[:8]}...")

                # Step 4: Unified project cleanup after all iterations deleted.
                # Does not rely on project_created flag — checks actual remaining count.
                print(f"\n--- Project cleanup ---")
                for proj_uuid in affected_project_ids:
                    remaining = await self.conn.fetchval(
                        "SELECT COUNT(*) FROM design_iterations WHERE project_id = $1",
                        proj_uuid
                    )
                    if remaining == 0:
                        await self.conn.execute(
                            "DELETE FROM projects WHERE id = $1", proj_uuid
                        )
                        print(f"  [✓] DELETED project {str(proj_uuid)[:8]}... (no remaining iterations)")
                    else:
                        print(f"  [!] Project {str(proj_uuid)[:8]}... kept: {remaining} iteration(s) still exist")

                print(f"\n[✓] Transaction completed successfully")

            self._update_log_status(log_file, log_data)
            return True

        except Exception as e:
            print(f"\n[✗] Rollback failed: {e}")
            print(f"[!] Transaction rolled back — no changes were made")
            return False

    def _update_log_status(self, log_file: str, log_data: Dict):
        log_data['rollback_status'] = 'completed'
        log_data['rollback_timestamp'] = datetime.now().isoformat()

        with open(log_file, 'w', encoding='utf-8') as f:
            yaml.dump(log_data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        print(f"[✓] Log file updated: {log_file}")


async def main():
    parser = argparse.ArgumentParser(
        description="HLS Knowledge Base Logger-Rollback Tool (v1.0 - Precise)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate log for specific project and iteration
  python3 logger-rollback.py logger --project FIR128_Optimization --iteration 4

  # Generate log for entire project (all iterations)
  python3 logger-rollback.py logger --project FIR128_Optimization

  # Generate log for recent imports (last 1 hour)
  python3 logger-rollback.py logger --recent 1h

  # Execute rollback (with confirmation)
  python3 logger-rollback.py rollback logs/rollback_FIR128_iter4_20251012.yaml

  # Dry run (preview only)
  python3 logger-rollback.py rollback --dry-run logs/rollback_FIR128_iter4_20251012.yaml
"""
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to execute')

    logger_parser = subparsers.add_parser('logger', help='Generate rollback log')
    logger_parser.add_argument('--project', help='Project name')
    logger_parser.add_argument('--iteration', type=int, help='Iteration number (optional)')
    logger_parser.add_argument('--recent', help='Recent imports (e.g., 1h, 2h, 24h)')
    logger_parser.add_argument('--force', action='store_true', help='Skip confirmation prompts')
    logger_parser.add_argument('--db-url', default=None, help='Database URL override')

    rollback_parser = subparsers.add_parser('rollback', help='Execute rollback from log')
    rollback_parser.add_argument('log_file', help='Path to rollback log file (YAML)')
    rollback_parser.add_argument('--dry-run', action='store_true', help='Preview only')
    rollback_parser.add_argument('--db-url', default=None, help='Database URL override')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    db_url = args.db_url or DEFAULT_DATABASE_URL

    if args.command == 'logger':
        if not args.project and not args.recent:
            print("[✗] Error: Must specify --project or --recent")
            sys.exit(1)

        tool = LoggerRollback(db_url, force=args.force)

        try:
            await tool.connect()

            if args.recent:
                hours_str = args.recent.lower().replace('h', '').replace('our', '').replace('s', '')
                try:
                    hours = float(hours_str)
                except ValueError:
                    print(f"[✗] Invalid time format: {args.recent}")
                    sys.exit(1)

                log_path = await tool.logger_recent(hours)
            else:
                log_path = await tool.logger_by_project(args.project, args.iteration)

            sys.exit(0 if log_path else 1)

        finally:
            await tool.close()

    elif args.command == 'rollback':
        if not Path(args.log_file).exists():
            print(f"[✗] Log file not found: {args.log_file}")
            sys.exit(1)

        if args.dry_run:
            tool = LoggerRollback(db_url)
            success = await tool.rollback(args.log_file, dry_run=True)
        else:
            tool = LoggerRollback(db_url)
            try:
                await tool.connect()
                success = await tool.rollback(args.log_file, dry_run=False)
            finally:
                await tool.close()

        if success:
            print("\n[✓] Rollback completed successfully")
            sys.exit(0)
        else:
            print("\n[✗] Rollback failed or cancelled")
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
