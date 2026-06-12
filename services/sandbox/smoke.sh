#!/usr/bin/env bash
# Smoke-test the sandbox image directly (no API/DB). Stages a trivial passing
# solution + test in a temp dir and runs the container with the same isolation
# flags the SandboxClient uses, then prints the JSON result payload.
set -euo pipefail

IMAGE="${1:-python-coach-sandbox:latest}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

cat > "$TMP/solution.py" <<'PY'
def answer():
    return 42
PY

cat > "$TMP/test_answer.py" <<'PY'
from solution import answer

def test_answer():
    assert answer() == 42
PY

docker run --rm \
  --network none \
  --read-only \
  --tmpfs /work:rw,size=32m,noexec,uid=10001,gid=10001 \
  --memory 256m --memory-swap 256m \
  --cpus 1.0 \
  --pids-limit 128 \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  -v "$TMP:/code:ro" \
  "$IMAGE"
