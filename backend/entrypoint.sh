#!/bin/sh
set -e

# Activate the venv directly — avoids uv run which tries to
# re-install the project and fails on read-only .pth files.
export PATH="/app/.venv/bin:$PATH"

# Ensure bijlagen directories exist (volume mounts may override image dirs)
mkdir -p /data/bijlagen/chat 2>/dev/null || true

# Verify write access — fail fast with actionable error
if ! touch /data/bijlagen/chat/.write_test_$$ 2>/dev/null; then
    echo "ERROR: /data/bijlagen/chat is not writable"
    echo "Current user: $(id)"
    ls -la /data/bijlagen/ 2>/dev/null || ls -la /data/ 2>/dev/null || true
    exit 1
fi
rm -f /data/bijlagen/chat/.write_test_$$ 2>/dev/null || true

echo "Running database migrations..."
alembic upgrade head

echo "Starting parlementair import worker..."
python -m bouwmeester.worker &

echo "Starting uvicorn..."
exec uvicorn bouwmeester.core.app:create_app --factory --host 0.0.0.0 --port 8080 --proxy-headers --forwarded-allow-ips='*'
