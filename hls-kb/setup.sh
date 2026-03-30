#!/bin/bash
# Copyright (c) 2026 AICOFORGE. All rights reserved.
# CC BY-NC 4.0 — non-commercial use only. See LICENSE.
# Commercial use: kevinjan@aicoforge.com

set -e  # Stop immediately on error

echo "============================================================"
echo "HLS Knowledge Base - Full Re-initialization"
echo "============================================================"
echo ""

# Switch to the script's directory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "${SCRIPT_DIR}"

echo "Current directory: $(pwd)"
echo ""

# ==================== Environment Variable Definitions (edit this block directly) ====================
KB_API_PORT=8000
DB_HOST=localhost
DB_ADMIN=admin             # Admin account (used by KB host, read-write access)
DB_ADMIN_PASS=admin_passwd
DB_USER=hls_user               # General account (used by Vitis-HLS host, read-only access)
DB_PASS=hls_user_passwd
DB_NAME=hls_knowledge
DB_PORT=5432
# ======================================================================

echo "------------------------------------------------------------"
echo "  KB_API_PORT   = ${KB_API_PORT}"
echo "  DB_HOST       = ${DB_HOST}"
echo "  DB_ADMIN      = ${DB_ADMIN}"
echo "  DB_ADMIN_PASS = ${DB_ADMIN_PASS}"
echo "  DB_USER       = ${DB_USER}"
echo "  DB_PASS       = ${DB_PASS}"
echo "  DB_NAME       = ${DB_NAME}"
echo "  DB_PORT       = ${DB_PORT}"
echo "------------------------------------------------------------"
echo ""

# ==================== Generate .env file ====================
ENV_FILE="${SCRIPT_DIR}/.env"

cat > "${ENV_FILE}" <<EOF
KB_API_PORT=${KB_API_PORT}
DB_HOST=${DB_HOST}
DB_ADMIN=${DB_ADMIN}
DB_ADMIN_PASS=${DB_ADMIN_PASS}
DB_USER=${DB_USER}
DB_PASS=${DB_PASS}
DB_NAME=${DB_NAME}
DB_PORT=${DB_PORT}
DATABASE_URL=postgresql://${DB_ADMIN}:${DB_ADMIN_PASS}@${DB_HOST}:${DB_PORT}/${DB_NAME}
EOF

echo "✓ Generated .env file: ${ENV_FILE}"

# ==================== Write to ~/.bashrc (ensure env vars persist after reboot) ====================
BASHRC="${HOME}/.bashrc"
SOURCE_LINE="set -a; source ${ENV_FILE}; set +a  # HLS Knowledge Base"

# Remove old HLS Knowledge Base lines and any stale DATABASE_URL exports (if any), then add the new line
if [ -f "${BASHRC}" ]; then
    grep -v "# HLS Knowledge Base" "${BASHRC}" \
        | grep -v "^export DATABASE_URL=" \
        | grep -v "^export DB_ADMIN=" \
        | grep -v "^export DB_ADMIN_PASS=" \
        | grep -v "^export DB_USER=" \
        | grep -v "^export DB_PASS=" \
        | grep -v "^export DB_NAME=" \
        | grep -v "^export DB_HOST=" \
        | grep -v "^export DB_PORT=" \
        > "${BASHRC}.tmp" || true
    mv "${BASHRC}.tmp" "${BASHRC}"
fi

echo "${SOURCE_LINE}" >> "${BASHRC}"
echo "✓ Added source .env to ${BASHRC}"
echo ""

# Export variables for use in the rest of this script
export KB_API_PORT DB_HOST DB_ADMIN DB_ADMIN_PASS DB_USER DB_PASS DB_NAME DB_PORT
export DATABASE_URL="postgresql://${DB_ADMIN}:${DB_ADMIN_PASS}@${DB_HOST}:${DB_PORT}/${DB_NAME}"

# Derive container names
CONTAINER_DB="${DB_NAME}-db"
CONTAINER_API="${DB_NAME}-api"

# ==================== Generate init.sql (use sed to replace placeholders) ====================
echo "[1/11] Generating init.sql..."
if [ -f init.sql.in ]; then
    sed \
        -e "s/__DB_ADMIN__/${DB_ADMIN}/g" \
        -e "s/__DB_USER__/${DB_USER}/g" \
        -e "s/__DB_PASS__/${DB_PASS}/g" \
        -e "s/__DB_NAME__/${DB_NAME}/g" \
        init.sql.in > init.sql
    echo "✓ init.sql generated from init.sql.in (sed replaced __DB_ADMIN__ → ${DB_ADMIN}, __DB_USER__ → ${DB_USER})"
else
    echo "❗ init.sql.in not found, using existing init.sql"
fi
echo ""

# ==================== 1. Stop and remove containers and volumes ====================
echo "[2/11] Stopping and removing containers and volumes..."
docker-compose down -v
if [ $? -eq 0 ]; then
    echo "✓ Containers and volumes removed"
else
    echo "✗ Removal failed"
    exit 1
fi
echo ""

# ==================== 2. Confirm volume deletion ====================
echo "[3/11] Confirming volume deletion..."
COMPOSE_PROJECT=$(basename "${SCRIPT_DIR}")
EXPECTED_VOLUME="${COMPOSE_PROJECT}_postgres_data"
if ! docker volume ls --format '{{.Name}}' | grep -q "^${EXPECTED_VOLUME}$"; then
    echo "✓ Volume fully cleaned (${EXPECTED_VOLUME} does not exist)"
else
    echo "❗ Volume still exists: ${EXPECTED_VOLUME}"
    echo "  Attempting forced removal..."
    docker volume rm "${EXPECTED_VOLUME}" && echo "✓ Forced removal successful" || echo "✗ Forced removal failed, please run manually: docker volume rm ${EXPECTED_VOLUME}"
fi
echo ""

# ==================== 3. Remove old API image to force full rebuild ====================
echo "[4/11] Removing old API image to force full rebuild..."
OLD_IMAGE="${COMPOSE_PROJECT}-api"
# Also try common naming convention: directory_service
OLD_IMAGE_ALT="${COMPOSE_PROJECT}_api"
REMOVED_ANY=false

for IMG in "${OLD_IMAGE}" "${OLD_IMAGE_ALT}" "hls-kb-api"; do
    if docker image inspect "${IMG}" > /dev/null 2>&1; then
        docker rmi "${IMG}" && echo "✓ Removed image: ${IMG}" && REMOVED_ANY=true || echo "  ❗ Could not remove ${IMG} (may still be referenced)"
    fi
done

if [ "${REMOVED_ANY}" = false ]; then
    echo "  (No old API image found, will build fresh)"
fi
echo ""

# ==================== 4. Clean up dangling images and build cache ====================
echo "[5/11] Cleaning up dangling images and unused build cache..."
BEFORE_SIZE=$(docker system df --format '{{.Size}}' 2>/dev/null | head -1 || echo "unknown")

# Remove dangling images (untagged layers from previous builds)
DANGLING=$(docker images -f "dangling=true" -q)
if [ -n "${DANGLING}" ]; then
    echo "  Removing $(echo "${DANGLING}" | wc -w) dangling image(s)..."
    docker rmi ${DANGLING} 2>/dev/null && echo "  ✓ Dangling images removed" || echo "  ❗ Some dangling images could not be removed (in use)"
else
    echo "  (No dangling images found)"
fi

# Prune build cache
docker builder prune -f > /dev/null 2>&1 && echo "✓ Build cache cleared" || echo "  ❗ Build cache prune skipped"
echo ""

# ==================== 5. Rebuild image and restart containers ====================
echo "[6/11] Building new image and starting containers..."
docker-compose up -d --build
if [ $? -eq 0 ]; then
    echo "✓ Image rebuilt and containers started"
else
    echo "✗ Build or startup failed"
    exit 1
fi
echo ""

# ==================== 6. Wait for PostgreSQL initialization ====================
echo "[7/11] Waiting for PostgreSQL initialization (10 seconds)..."
sleep 10
echo "✓ Wait complete"
echo ""

# ==================== 7. Check PostgreSQL status ====================
echo "[8/11] Checking PostgreSQL status..."
for i in {1..10}; do
    if docker exec "${CONTAINER_DB}" pg_isready -U "${DB_ADMIN}" -d "${DB_NAME}" > /dev/null 2>&1; then
        echo "✓ PostgreSQL is ready"
        break
    fi
    if [ $i -eq 10 ]; then
        echo "✗ PostgreSQL not ready, check logs: docker logs ${CONTAINER_DB}"
        exit 1
    fi
    echo "  Waiting... ($i/10)"
    sleep 2
done
echo ""

# ==================== 8. Verify schema ====================
echo "[9/11] Verifying database schema..."
RULE_CODE=$(docker exec "${CONTAINER_DB}" psql -U "${DB_ADMIN}" -d "${DB_NAME}" -t -c \
    "SELECT column_name FROM information_schema.columns WHERE table_name='hls_rules' AND column_name='rule_code';" | xargs)
RULE_TYPE=$(docker exec "${CONTAINER_DB}" psql -U "${DB_ADMIN}" -d "${DB_NAME}" -t -c \
    "SELECT column_name FROM information_schema.columns WHERE table_name='hls_rules' AND column_name='rule_type';" | xargs)

if [ "$RULE_CODE" == "rule_code" ] && [ "$RULE_TYPE" == "rule_type" ]; then
    echo "✓ Schema is correct (contains rule_code and rule_type)"
else
    echo "✗ Schema is incorrect!"
    echo "  rule_code: $RULE_CODE"
    echo "  rule_type: $RULE_TYPE"
    exit 1
fi
echo ""

# ==================== 9. Check API health (no extra restart needed — already fresh) ====================
echo "[10/11] Checking API health..."
for i in {1..10}; do
    if curl -s "http://localhost:${KB_API_PORT}/health" > /dev/null 2>&1; then
        HEALTH_STATUS=$(curl -s "http://localhost:${KB_API_PORT}/health" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
        if [ "$HEALTH_STATUS" == "healthy" ]; then
            echo "✓ API health status: $HEALTH_STATUS"
            break
        fi
    fi
    if [ $i -eq 10 ]; then
        echo "✗ API not ready, check logs: docker logs ${CONTAINER_API}"
        exit 1
    fi
    echo "  Waiting... ($i/10)"
    sleep 2
done
echo ""

# ==================== 10. Import all rules (official rules + user-defined) ====================
echo "[11/11] Importing all rules..."
if python3 import_rules.py --type all > /tmp/import_rules.log 2>&1; then
    OFFICIAL_COUNT=$(docker exec "${CONTAINER_DB}" psql -U "${DB_ADMIN}" -d "${DB_NAME}" -t -c \
        "SELECT COUNT(*) FROM hls_rules WHERE rule_type='official';" | xargs)
    PROMPT_COUNT=$(docker exec "${CONTAINER_DB}" psql -U "${DB_ADMIN}" -d "${DB_NAME}" -t -c \
        "SELECT COUNT(*) FROM hls_rules WHERE rule_type='user_defined';" | xargs)
    echo "✓ Successfully imported ${OFFICIAL_COUNT:-?} official rules"
    echo "✓ Successfully imported ${PROMPT_COUNT:-?} user-defined rules"
else
    echo "✗ Import failed, check logs: /tmp/import_rules.log"
    exit 1
fi
echo ""

# ==================== Final Verification ====================
echo "============================================================"
echo "Final Verification"
echo "============================================================"
echo ""

# Check totals
TOTAL=$(docker exec "${CONTAINER_DB}" psql -U "${DB_ADMIN}" -d "${DB_NAME}" -t -c \
    "SELECT COUNT(*) FROM hls_rules;" | xargs)
OFFICIAL=$(docker exec "${CONTAINER_DB}" psql -U "${DB_ADMIN}" -d "${DB_NAME}" -t -c \
    "SELECT COUNT(*) FROM hls_rules WHERE rule_type='official';" | xargs)
USER_DEFINED=$(docker exec "${CONTAINER_DB}" psql -U "${DB_ADMIN}" -d "${DB_NAME}" -t -c \
    "SELECT COUNT(*) FROM hls_rules WHERE rule_type='user_defined';" | xargs)

echo "Database Statistics:"
echo "  Official rules  (official):     $OFFICIAL"
echo "  User-defined    (user_defined): $USER_DEFINED"
echo "  ──────────────────────────────"
echo "  Total:                          $TOTAL"
echo ""

# API test
echo "API Test:"
API_RULES=$(curl -s "http://localhost:${KB_API_PORT}/api/rules/effective?min_success_rate=0&limit=1" | \
    grep -o '"rules":\[' > /dev/null && echo "✓" || echo "✗")
echo "  Rules query: ${API_RULES}"
echo ""

echo "============================================================"
echo "✓ Initialization complete!"
echo "============================================================"
echo ""
echo "Next step:"
echo "  Access API: curl http://localhost:${KB_API_PORT}/health"
echo ""