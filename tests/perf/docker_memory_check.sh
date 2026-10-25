#!/usr/bin/env bash
# Run the Phase 3 pipeline under a hard container memory limit (swap disabled)
# on an input >= 5x the limit, then report peak RSS and OOMKilled.
# Usage: tests/perf/docker_memory_check.sh [limit_mb=256] [factor=5]
set -euo pipefail
LIMIT_MB=${1:-256}
FACTOR=${2:-5}
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
WORK=$(mktemp -d)
trap 'docker rm -f openstudio-memcheck >/dev/null 2>&1 || true; rm -rf "$WORK"' EXIT
TARGET=$((LIMIT_MB * FACTOR * 1024 * 1024))
python3 - "$WORK/big.csv" "$TARGET" <<'PY'
import sys
path, target = sys.argv[1], int(sys.argv[2])
with open(path, "w", newline="") as f:
    f.write("id,name,amount\r\n")
    i = 1
    while f.tell() < target:
        f.write("".join(f"{j},name{j}{'x' * 40},{j % 1000}\r\n" for j in range(i, i + 50000)))
        i += 50000
PY
SIZE=$(stat -c %s "$WORK/big.csv")
docker rm -f openstudio-memcheck >/dev/null 2>&1 || true
docker run --name openstudio-memcheck --user "$(id -u):$(id -g)" --memory="${LIMIT_MB}m" --memory-swap="${LIMIT_MB}m" \
  -v "$ROOT":/app:ro -v "$WORK":/data -w /app python:3.12-slim \
  python tests/_pipeline_worker.py /data/big.csv /data/out.csv /data/work --batch-size 1000 | tee "$WORK/stats.json"
echo "input_bytes=$SIZE limit_bytes=$((LIMIT_MB * 1024 * 1024)) ratio=$(python3 -c "print(round($SIZE/($LIMIT_MB*1048576),2))")"
docker inspect openstudio-memcheck --format 'OOMKilled={{.State.OOMKilled}} ExitCode={{.State.ExitCode}} Memory={{.HostConfig.Memory}} MemorySwap={{.HostConfig.MemorySwap}}'
