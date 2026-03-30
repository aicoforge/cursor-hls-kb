# Copyright (c) 2026 AICOFORGE. All rights reserved.
# CC BY-NC 4.0 — non-commercial use only. See LICENSE.
# Commercial use: kevinjan@aicoforge.com
"""
HLS Knowledge Base - FastAPI Server
Provides RESTful API for Cursor to query and record HLS designs

Concurrency Safety Measures:
- complete_iteration uses FOR UPDATE to lock the project row (serializes concurrent writes for the same project)
- complete_iteration's fallback path (when project_id doesn't exist) uses
  INSERT ON CONFLICT DO NOTHING to atomically create the project, eliminating the TOCTOU window;
  after successful creation, a follow-up FOR UPDATE is issued to block concurrent TXs
  for the same project_id in the window between INSERT project and MAX+1 calculation.
- complete_iteration uses FOR UPDATE to lock rules_effectiveness rows (prevents lost updates)
- create_project uses INSERT ON CONFLICT atomic operation (prevents duplicate projects, concurrency-safe)

DB schema constraints (init.sql.in):
- UNIQUE(name, type) ON projects — prevents same-type same-name projects
- UNIQUE(project_id, iteration_number) ON design_iterations — prevents duplicate iteration numbers

"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID, uuid4
import asyncpg
import os
import json
import hashlib  # For computing SHA256 hash of code_snapshot
from decimal import Decimal  # For precise avg_ii_improvement calculation, avoiding floating-point accumulation errors

# ==================== Configuration (from environment) ====================
DB_USER = os.getenv("DB_ADMIN", "admin")
DB_PASS = os.getenv("DB_ADMIN_PASS", "admin_passwd")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "hls_knowledge")
KB_API_PORT = int(os.getenv("KB_API_PORT", "8000"))

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

def compute_code_hash(code_snapshot: str) -> str:
    """
    Compute the SHA256 hash of the full code_snapshot text.

    Computes directly on the raw code_snapshot without any comment removal or formatting.
    Simple and reliable, avoids hash errors caused by unstable comment formats.

    Prerequisite: code_snapshot must be the exact code submitted to csynth, without post-modification.
    """
    return hashlib.sha256(code_snapshot.encode('utf-8')).hexdigest()


app = FastAPI(
    title="HLS Knowledge Base API",
    description="Knowledge base for HLS design patterns and optimization",
    version="1.0.0"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== Database Connection ====================
async def get_db_pool():
    """Get database connection pool"""
    return await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)

@app.on_event("startup")
async def startup():
    app.state.pool = await get_db_pool()
    print(f"✓ Database pool created: {DATABASE_URL}")

@app.on_event("shutdown")
async def shutdown():
    await app.state.pool.close()
    print("✓ Database pool closed")

# ==================== Pydantic Models ====================
class ProjectCreate(BaseModel):
    name: str
    type: str = Field(..., description="Project type: fir, matmul, conv, etc.")
    description: Optional[str] = None
    target_device: Optional[str] = "xilinx_fpga_board_b"  # Default value for POST /api/projects 

class DesignIterationCreate(BaseModel):
    project_id: UUID
    approach_description: str
    code_snapshot: str
    pragmas_used: List[str]
    prompt_used: Optional[str] = None
    cursor_reasoning: Optional[str] = None
    user_reference_code: Optional[str] = Field(None, description="User-provided reference code (C/C++/pseudocode). None if not provided")
    user_specification: Optional[str] = Field(None, description="User's requirements and constraints. None if not provided")
    reference_metadata: Optional[Dict[str, Any]] = Field(None, description="Reference metadata JSON. None if not provided")

class SynthesisResultData(BaseModel):
    """Synthesis result data (used by complete_iteration)"""
    ii_achieved: int
    ii_target: int
    latency_cycles: int
    timing_met: bool
    resource_usage: Dict[str, int]
    clock_period_ns: Optional[float] = 10.0

class RuleApplication(BaseModel):
    rule_code: Optional[str] = None  # Filled by Cursor after semantic matching (preferred)
    rule_description: Optional[str] = None  # Auxiliary note from Cursor. Not used by API for queries or statistics updates.
    # The rule's specific description comes from hls_rules.rule_text (fetched via exact rule_code match).
    # hls_rules.description stores import metadata (source file, line number), unrelated to this field.
    previous_ii: int
    current_ii: int
    success: bool
    category: Optional[str] = None

class CompleteIterationCreate(BaseModel):
    project_id: UUID
    project_name: Optional[str] = None
    project_type: str = Field(..., description="Project type: fir, matmul, conv, etc.")
    target_device: Optional[str] = "xilinx_fpga_board_a"  # Default value for auto-create
    iteration: DesignIterationCreate
    synthesis_result: SynthesisResultData  # Version without iteration_id
    rules_applied: List[RuleApplication] = []

# ==================== API Endpoints ====================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        async with app.state.pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return {
            "status": "healthy",
            "database": "connected",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }

# ---------- Projects ----------
@app.get("/api/projects")
async def list_projects(
    type: Optional[str] = Query(None, description="Filter by project type: fir, matmul, conv, etc."),
    limit: int = Query(50, ge=1, le=200, description="Max results"),
    offset: int = Query(0, ge=0, description="Offset for pagination")
):
    """List all projects (REST: GET = list)"""
    async with app.state.pool.acquire() as conn:
        if type:
            rows = await conn.fetch("""
                SELECT id, name, type, description, target_device, created_at, updated_at
                FROM projects WHERE type = $1
                ORDER BY type, name
                LIMIT $2 OFFSET $3
            """, type, limit, offset)
            total = await conn.fetchval("SELECT COUNT(*) FROM projects WHERE type = $1", type)
        else:
            rows = await conn.fetch("""
                SELECT id, name, type, description, target_device, created_at, updated_at
                FROM projects
                ORDER BY type, name
                LIMIT $1 OFFSET $2
            """, limit, offset)
            total = await conn.fetchval("SELECT COUNT(*) FROM projects")
        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "results": [dict(r) for r in rows]
        }

@app.post("/api/projects")
async def create_project(project: ProjectCreate):
    """Create a new project (REST: POST = create)
    
    Name must be unique within the same type; returns 409 Conflict with existing project_id on duplicate.
    Uses INSERT ON CONFLICT atomic operation, concurrency-safe.
    """
    async with app.state.pool.acquire() as conn:
        project_id = uuid4()
        # INSERT ON CONFLICT: atomic operation, concurrency-safe
        # If (name, type) already exists -> DO NOTHING, RETURNING returns no rows
        result = await conn.fetchrow("""
            INSERT INTO projects (id, name, type, description, target_device)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (name, type) DO NOTHING
            RETURNING id
        """, project_id, project.name, project.type, project.description, project.target_device)
        
        if result:
            # INSERT succeeded
            return {
                "project_id": str(project_id),
                "name": project.name,
                "type": project.type
            }
        else:
            # Conflict: (name, type) already exists, retrieve existing project_id and return 409
            existing = await conn.fetchrow("""
                SELECT id FROM projects WHERE name = $1 AND type = $2
            """, project.name, project.type)
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "project_name_conflict",
                    "message": f"Project '{project.name}' already exists for type '{project.type}'",
                    "existing_project_id": str(existing['id'])
                }
            )

@app.get("/api/projects/{project_id}")
async def get_project(project_id: UUID):
    """Get project details"""
    async with app.state.pool.acquire() as conn:
        project = await conn.fetchrow("""
            SELECT * FROM projects WHERE id = $1
        """, project_id)
        
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        
        return dict(project)

# ---------- Knowledge Base Queries ----------
@app.get("/api/design/similar")
async def find_similar_designs(
    project_type: str = Query(..., description="Project type: fir, matmul, conv"),
    target_ii: Optional[int] = Query(None, description="Target II value"),
    limit: int = Query(5, ge=1, le=20, description="Number of results")
):
    """Query similar successful design cases"""
    async with app.state.pool.acquire() as conn:
        query = """
            SELECT 
                di.id as iteration_id,
                di.project_id as project_id,
                p.name as project_name,
                p.type as project_type,
                di.iteration_number,
                di.approach_description,
                di.code_hash,
                di.pragmas_used,
                di.user_specification,
                di.cursor_reasoning,
                sr.ii_achieved,
                sr.ii_target,
                sr.latency_cycles,
                sr.resource_usage,
                di.created_at
            FROM design_iterations di
            JOIN projects p ON di.project_id = p.id
            JOIN synthesis_results sr ON di.id = sr.iteration_id
            WHERE p.type = $1
            AND sr.ii_achieved IS NOT NULL
        """
        
        params = [project_type]
        
        if target_ii is not None:
            query += " AND sr.ii_achieved <= $2"
            params.append(target_ii)
            query += " ORDER BY sr.ii_achieved ASC"
        else:
            query += " ORDER BY sr.ii_achieved ASC"
        
        query += f" LIMIT ${len(params) + 1}"
        params.append(limit)
        
        results = await conn.fetch(query, *params)
        
        return {
            "query": {
                "project_type": project_type,
                "target_ii": target_ii,
                "limit": limit
            },
            "results": [dict(r) for r in results]
        }

@app.get("/api/design/{iteration_id}/code")
async def get_iteration_code(iteration_id: UUID):
    """Get full details of a specific iteration (including code_snapshot and all design context)
    
    Use case: When you need to view the complete code, reasoning process, or reference code
    Note: Response may be large (code_snapshot + user_reference_code); only query when necessary
    """
    async with app.state.pool.acquire() as conn:
        result = await conn.fetchrow("""
            SELECT 
                di.id,
                di.iteration_number,
                di.approach_description,
                di.code_snapshot,
                di.code_hash,
                di.pragmas_used,
                di.user_specification,
                di.cursor_reasoning,
                di.prompt_used,
                di.user_reference_code,
                p.name as project_name
            FROM design_iterations di
            JOIN projects p ON di.project_id = p.id
            WHERE di.id = $1
        """, iteration_id)
        
        if not result:
            raise HTTPException(status_code=404, detail="Iteration not found")
        
        return {
            "iteration_id": str(result['id']),
            "iteration_number": result['iteration_number'],
            "project_name": result['project_name'],
            "approach_description": result['approach_description'],
            "code_snapshot": result['code_snapshot'],
            "code_hash": result['code_hash'],
            "pragmas_used": result['pragmas_used'],
            "user_specification": result['user_specification'],
            "cursor_reasoning": result['cursor_reasoning'],
            "prompt_used": result['prompt_used'],
            "user_reference_code": result['user_reference_code']
        }

@app.get("/api/rules/effective")
async def get_effective_rules(
    project_type: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    rule_type: Optional[str] = Query(None),  # 'official' or 'user_defined'
    min_success_rate: float = Query(0.0, ge=0.0, le=1.0)
):
    """Get effective HLS rules (supports rule_type filtering)
    
    project_type filtering logic:
    - With project_type: LEFT JOIN condition includes re.project_type = $N,
      ensuring rules that have records for other project_types but not for the target
      still appear (times_applied=0) and are not incorrectly excluded.
    - Without project_type: LEFT JOIN has no project_type condition,
      returns all rules with aggregated statistics across project_types.
    """
    async with app.state.pool.acquire() as conn:
        # Dynamically build LEFT JOIN condition: project_type goes in JOIN ON, not WHERE
        # Prevents rules with records for other project_types from being excluded by WHERE
        join_conditions = ["r.id = re.rule_id"]
        conditions = []  # WHERE conditions (only for hls_rules table columns)
        params = []
        
        if project_type:
            params.append(project_type)
            join_conditions.append(f"re.project_type = ${len(params)}")
        
        join_clause = " AND ".join(join_conditions)
        
        query = f"""
            SELECT * FROM (
                SELECT 
                    r.id,
                    r.rule_code,
                    r.rule_type,
                    r.rule_text,
                    r.category,
                    r.priority,
                    r.source,
                    COALESCE(re.times_applied, 0) as times_applied,
                    COALESCE(re.success_count, 0) as success_count,
                    CASE 
                        WHEN COALESCE(re.times_applied, 0) > 0 
                        THEN CAST(COALESCE(re.success_count, 0) AS FLOAT) / re.times_applied
                        ELSE 0
                    END as success_rate,
                    re.avg_ii_improvement
                FROM hls_rules r
                LEFT JOIN rules_effectiveness re ON {join_clause}
        """
        
        if category:
            params.append(category)
            conditions.append(f"r.category = ${len(params)}")
        
        if rule_type:
            params.append(rule_type)
            conditions.append(f"r.rule_type = ${len(params)}")
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        # Close subquery, add min_success_rate filter
        query += """
            ) AS filtered_rules
            WHERE success_rate >= $""" + str(len(params) + 1) + """
            ORDER BY success_rate DESC, priority DESC
        """
        params.append(min_success_rate)
        
        results = await conn.fetch(query, *params)
        
        return {
            "filters": {
                "project_type": project_type,
                "category": category,
                "rule_type": rule_type,
                "min_success_rate": min_success_rate
            },
            "rules": [dict(r) for r in results]
        }

@app.get("/api/rules/categories")
async def get_rule_categories():
    """Return all category values present in hls_rules (alphabetically sorted)

    Use case: For Cursor's dual-track query category inference phase,
    selecting from the known set rather than free inference, improving match accuracy.
    """
    async with app.state.pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT DISTINCT category FROM hls_rules
            ORDER BY category ASC
        """)
        return {
            "categories": [row['category'] for row in rows]
        }

# ---------- Complete Iteration (all-in-one endpoint) ----------
@app.post("/api/design/complete_iteration")
async def record_complete_iteration(data: CompleteIterationCreate):
    """
    Record a complete design iteration (recommended)
    Single API call to: create project, record iteration, record synthesis result, update rule effectiveness
    """
    async with app.state.pool.acquire() as conn:
        async with conn.transaction():
            # 1. Confirm project exists (FOR UPDATE locks the project row, serializes concurrent writes for the same project)
            project_exists = await conn.fetchval(
                "SELECT id FROM projects WHERE id = $1 FOR UPDATE", data.project_id
            )
            
            project_created = not bool(project_exists)
            if not project_exists:
                project_name = data.project_name or f"{data.project_type.upper()}_Design"
                # INSERT ON CONFLICT: atomic operation, eliminates TOCTOU window
                # If (name, type) already exists -> DO NOTHING, RETURNING returns no rows
                result = await conn.fetchrow("""
                    INSERT INTO projects (id, name, type, description, target_device)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (name, type) DO NOTHING
                    RETURNING id
                """, data.project_id, project_name, data.project_type,
                    f"Auto-created project for {data.project_type} design",
                    data.target_device)
                
                if result:
                    # Creation succeeded, issue follow-up FOR UPDATE to lock the project row
                    # Ensures subsequent MAX(iteration_number)+1 is serialized equivalently to the normal path
                    await conn.fetchval(
                        "SELECT id FROM projects WHERE id = $1 FOR UPDATE",
                        data.project_id
                    )
                else:
                    # Conflict: (name, type) already exists (created by another TX first)
                    # The other TX has committed, so SELECT will find the existing record
                    existing = await conn.fetchrow("""
                        SELECT id FROM projects WHERE name = $1 AND type = $2
                    """, project_name, data.project_type)
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "error": "project_name_conflict",
                            "message": f"Project '{project_name}' already exists for type '{data.project_type}'. Use existing project_id.",
                            "existing_project_id": str(existing['id'])
                        }
                    )
            
            # 2. Get iteration number
            iteration_num = await conn.fetchval("""
                SELECT COALESCE(MAX(iteration_number), 0) + 1
                FROM design_iterations
                WHERE project_id = $1
            """, data.project_id)
            
            # 3. Insert iteration record
            iteration_id = uuid4()
            
            # Compute SHA256 hash of the full code_snapshot (no comment removal)
            code_hash = compute_code_hash(data.iteration.code_snapshot)
            
            await conn.execute("""
                INSERT INTO design_iterations (
                    id, project_id, iteration_number, approach_description,
                    code_snapshot, code_hash, pragmas_used, prompt_used, cursor_reasoning,
                    user_reference_code, user_specification, reference_metadata
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            """, iteration_id, data.project_id, iteration_num,
                data.iteration.approach_description, data.iteration.code_snapshot, code_hash,
                data.iteration.pragmas_used, data.iteration.prompt_used,
                data.iteration.cursor_reasoning,
                data.iteration.user_reference_code, data.iteration.user_specification,
                json.dumps(data.iteration.reference_metadata) if data.iteration.reference_metadata else None)
            
            # 4. Insert synthesis result
            result_id = uuid4()
            await conn.execute("""
                INSERT INTO synthesis_results (
                    id, iteration_id, ii_achieved, ii_target, latency_cycles,
                    timing_met, resource_usage, clock_period_ns
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """, result_id, iteration_id, data.synthesis_result.ii_achieved,
                data.synthesis_result.ii_target, data.synthesis_result.latency_cycles,
                data.synthesis_result.timing_met,
                json.dumps(data.synthesis_result.resource_usage),
                data.synthesis_result.clock_period_ns)
            
            # 5. Record rule application effectiveness (with rollback info collection + _rules_applied snapshot)
            rules_recorded = 0
            rollback_changes = []
            rules_applied_snapshot = []  # Plan B: Write _rules_applied after Step 5 completes
            for rule_app in data.rules_applied:
                rule = None
                if rule_app.rule_code:
                    rule = await conn.fetchrow("""
                        SELECT id, rule_text, category, priority
                        FROM hls_rules WHERE rule_code = $1
                    """, rule_app.rule_code)
                
                # Exact rule_code match is the only rule lookup method
                # No rule_code or no match -> skip rules_effectiveness update
                # Cursor is responsible for finding the correct rule_code via semantic matching before recording
                
                if rule:
                    ii_improvement = rule_app.previous_ii - rule_app.current_ii
                    success = rule_app.success and ii_improvement > 0
                    
                    # FOR UPDATE: prevents lost updates when multiple concurrent writes target the same rule+project_type
                    # TX B waits for TX A to commit before reading, ensuring prev_state snapshot and calculations are based on latest values
                    existing = await conn.fetchrow("""
                        SELECT id, times_applied, success_count,
                               avg_ii_improvement, last_applied_at
                        FROM rules_effectiveness
                        WHERE rule_id = $1 AND project_type = $2
                        FOR UPDATE
                    """, rule['id'], data.project_type)
                    
                    if existing:
                        rollback_changes.append({
                            "re_id": str(existing['id']),
                            "rule_id": str(rule['id']),
                            "action": "update",
                            "prev_state": {
                                "times_applied": existing['times_applied'],
                                "success_count": existing['success_count'],
                                "avg_ii_improvement": float(existing['avg_ii_improvement'] or 0),
                                "last_applied_at": existing['last_applied_at'].isoformat() if existing['last_applied_at'] else None
                            }
                        })
                        
                        new_times = existing['times_applied'] + 1
                        new_success = existing['success_count'] + (1 if success else 0)
                        # Use Decimal for precise calculation, avoiding floating-point accumulation errors
                        old_avg = Decimal(str(existing['avg_ii_improvement'] or 0))
                        old_total = old_avg * existing['success_count']
                        new_total = old_total + (ii_improvement if success else 0)
                        new_avg = float(new_total / new_success) if new_success > 0 else 0
                        
                        await conn.execute("""
                            UPDATE rules_effectiveness
                            SET times_applied = $1, success_count = $2,
                                avg_ii_improvement = $3, last_applied_at = CURRENT_TIMESTAMP
                            WHERE id = $4
                        """, new_times, new_success, new_avg, existing['id'])
                    else:
                        new_re_id = uuid4()
                        rollback_changes.append({
                            "re_id": str(new_re_id),
                            "rule_id": str(rule['id']),
                            "action": "insert",
                            "prev_state": None
                        })
                        
                        await conn.execute("""
                            INSERT INTO rules_effectiveness (
                                id, rule_id, project_type, times_applied, success_count,
                                avg_ii_improvement, last_applied_at
                            ) VALUES ($1, $2, $3, $4, $5, $6, CURRENT_TIMESTAMP)
                        """, new_re_id, rule['id'], data.project_type, 1,
                            1 if success else 0, ii_improvement if success else 0)
                    
                    rules_recorded += 1

                    # Plan B: Collect _rules_applied snapshot (only entries that matched hls_rules)
                    # api_success = API-side recalculation (Cursor-reported success + actual II decrease)
                    rules_applied_snapshot.append({
                        "rule_code": rule_app.rule_code,
                        "rule_text": rule['rule_text'],       # From hls_rules (not available on Cursor side)
                        "category": rule['category'],
                        "previous_ii": rule_app.previous_ii,
                        "current_ii": rule_app.current_ii,
                        "cursor_success": rule_app.success,   # Cursor's self-reported assessment
                        "api_success": success,               # API recalculation (core value: checks if II actually decreased)
                        "ii_improvement": ii_improvement
                    })
            
            # 6. Merge _rollback_info and _rules_applied into reference_metadata
            # _rules_applied: only entries where rule_code matched hls_rules (same level as _rollback_info)
            # Merge semantics: {**existing_meta, **rollback_meta}, does not overwrite Cursor-provided custom fields
            rollback_meta = {
                "_rollback_info": {
                    "project_created": project_created,
                    "project_id": str(data.project_id),
                    "synthesis_result_id": str(result_id),
                    "rules_changes": rollback_changes
                },
                "_rules_applied": rules_applied_snapshot
            }
            existing_meta = data.iteration.reference_metadata or {}
            merged_meta = {**existing_meta, **rollback_meta}
            
            await conn.execute("""
                UPDATE design_iterations SET reference_metadata = $1 WHERE id = $2
            """, json.dumps(merged_meta), iteration_id)
            
            return {
                "status": "success",
                "iteration_id": str(iteration_id),
                "iteration_number": iteration_num,
                "project_id": str(data.project_id),
                "rules_recorded": rules_recorded,
                "message": f"Complete iteration record created (iteration #{iteration_num}, {rules_recorded} rule effectiveness record(s) updated)"
            }

# ---------- Analytics ----------
@app.get("/api/analytics/project/{project_id}/progress")
async def get_project_progress(project_id: UUID):
    """Get project optimization progress"""
    async with app.state.pool.acquire() as conn:
        iterations = await conn.fetch("""
            SELECT 
                di.id as iteration_id,
                di.iteration_number,
                di.approach_description,
                sr.ii_achieved,
                sr.latency_cycles,
                sr.timing_met,
                sr.resource_usage,
                di.created_at
            FROM design_iterations di
            LEFT JOIN synthesis_results sr ON di.id = sr.iteration_id
            WHERE di.project_id = $1
            ORDER BY di.iteration_number ASC
        """, project_id)
        
        if not iterations:
            raise HTTPException(status_code=404, detail="No iterations found")
        
        # Calculate improvement
        progress = []
        for i, iter in enumerate(iterations):
            item = dict(iter)
            if i > 0 and iter['ii_achieved'] and iterations[i-1]['ii_achieved']:
                item['ii_improvement'] = iterations[i-1]['ii_achieved'] - iter['ii_achieved']
            progress.append(item)
        
        return {
            "project_id": str(project_id),
            "total_iterations": len(iterations),
            "iterations": progress
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=KB_API_PORT)
