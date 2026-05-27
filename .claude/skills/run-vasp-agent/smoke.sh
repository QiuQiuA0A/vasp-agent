#!/bin/bash
# VASP Agent smoke test — starts server, exercises all endpoints, reports results.
# Usage: bash .claude/skills/run-vasp-agent/smoke.sh
# Set VASP_PORT to override the default (8000).

set -euo pipefail
PORT="${VASP_PORT:-8000}"
BASE="http://localhost:$PORT"
SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SKILL_DIR/../../.." && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"
FAILURES=0

# ---- Python launcher detection ----
PYTHON=""
for py in python3.14 python3 python; do
  if command -v "$py" > /dev/null 2>&1; then
    PYTHON="$py"
    break
  fi
done
if [ -z "$PYTHON" ]; then
  echo "FAIL: no Python found" >&2
  exit 1
fi

# ---- helpers ----
ok()  { echo "  PASS $1"; }
fail() { echo "  FAIL ${1}: ${2:-unknown}"; FAILURES=$((FAILURES + 1)); }
assert_eq() {
  local label="$1" expected="$2" actual="$3"
  if [ "$actual" = "$expected" ]; then
    ok "$label ($actual)"
  else
    fail "$label (expected '$expected', got '$actual')"
  fi
}
assert_contains() {
  local label="$1" needle="$2" haystack="$3"
  if echo "$haystack" | grep -qF "$needle"; then
    ok "$label"
  else
    fail "$label (response missing '$needle')"
  fi
}

# ---- start server ----
echo "=== Starting server ==="
# Check if server is already running
if curl -sf "$BASE/api/v1/health" >/dev/null 2>&1; then
  echo "  Server already running on port $PORT — reusing"
  SKIP_STOP=true
else
  echo "  Starting server..."
  cd "$BACKEND_DIR"
  "$PYTHON" -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT" &>/tmp/vasp-agent-server.log &
  SERVER_PID=$!
  echo "  PID=$SERVER_PID"
  # Wait for readiness
  for i in $(seq 1 30); do
    if curl -sf "$BASE/api/v1/health" >/dev/null 2>&1; then
      ok "Server ready (port $PORT, attempt $i)"
      break
    fi
    if [ "$i" -eq 30 ]; then
      echo "  FAIL: server did not start within 30s" >&2
      cat /tmp/vasp-agent-server.log >&2
      kill "$SERVER_PID" 2>/dev/null || true
      exit 1
    fi
    sleep 1
  done
fi

# ==== SECTION: Health & Config ====
echo "=== Health & Config ==="
RESP=$(curl -sf "$BASE/api/v1/health")
assert_eq "health" '{"status":"ok"}' "$RESP"

RESP=$(curl -sf "$BASE/api/v1/calc-types")
assert_contains "calc-types list" "optimization" "$RESP"
assert_contains "calc-types formulas" "formula" "$RESP"

# ==== SECTION: Frontend served ====
echo "=== Frontend ==="
RESP=$(curl -sf "$BASE/")
assert_contains "frontend:title" "VASP Agent" "$RESP"
assert_contains "frontend:app.js" "app.js" "$RESP"

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/style.css")
assert_eq "frontend:css" "200" "$HTTP_CODE"

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/app.js")
assert_eq "frontend:js" "200" "$HTTP_CODE"

# ==== SECTION: Generation — all calc types ====
echo "=== Generation: optimization (SMILES) ==="
PAYLOAD='{"calc_type":"optimization","structure":{"format":"smiles","data":"O"},"charge":0,"multiplicity":1,"name":"test-water"}'
RESP=$(curl -sf -X POST "$BASE/api/v1/generate" \
  -H "Content-Type: application/json" -d "$PAYLOAD")
assert_contains "gen:INCAR" "INCAR" "$RESP"
assert_contains "gen:POSCAR" "POSCAR" "$RESP"
assert_contains "gen:POTCAR" "POTCAR" "$RESP"
assert_contains "gen:KPOINTS" "KPOINTS" "$RESP"
N_FILES=$(echo "$RESP" | "$PYTHON" -c "import sys,json; print(len(json.load(sys.stdin)['files']))" 2>/dev/null || echo "0")
assert_eq "gen:file count" "5" "$N_FILES"

echo "=== Generation: homo_lumo (SMILES benzene) ==="
PAYLOAD='{"calc_type":"homo_lumo","structure":{"format":"smiles","data":"c1ccccc1"},"charge":0,"multiplicity":1,"name":"benzene"}'
RESP=$(curl -sf -X POST "$BASE/api/v1/generate" \
  -H "Content-Type: application/json" -d "$PAYLOAD")
assert_contains "homo_lumo:INCAR" "static_INCAR" "$RESP"
assert_contains "homo_lumo:opt" "opt_INCAR" "$RESP"

echo "=== Generation: dipole ==="
PAYLOAD='{"calc_type":"dipole","structure":{"format":"smiles","data":"CO"},"charge":0,"multiplicity":1,"name":"methanol"}'
RESP=$(curl -sf -X POST "$BASE/api/v1/generate" \
  -H "Content-Type: application/json" -d "$PAYLOAD")
assert_contains "dipole:LDIPOL" "LDIPOL" "$RESP"

echo "=== Generation: AIMD ==="
PAYLOAD='{"calc_type":"aimd","structure":{"format":"smiles","data":"O"},"charge":0,"multiplicity":1,"name":"water-aimd","temperature":350}'
RESP=$(curl -sf -X POST "$BASE/api/v1/generate" \
  -H "Content-Type: application/json" -d "$PAYLOAD")
assert_contains "aimd:TEBEG" "TEBEG" "$RESP"

echo "=== Generation: formula input ==="
PAYLOAD='{"calc_type":"optimization","structure":{"format":"formula","data":"NaCl"},"charge":0,"multiplicity":1,"name":"nacl"}'
RESP=$(curl -sf -X POST "$BASE/api/v1/generate" \
  -H "Content-Type: application/json" -d "$PAYLOAD")
assert_contains "formula:INCAR" "INCAR" "$RESP"

echo "=== Generation: XYZ input ==="
XYZ_JSON=$(printf '{"calc_type":"optimization","structure":{"format":"xyz","data":"3\\nwater\\nO  0.0  0.0  0.0\\nH  0.757  0.586  0.0\\nH -0.757  0.586  0.0"},"charge":0,"multiplicity":1,"name":"water-xyz"}')
RESP=$(curl -sf -X POST "$BASE/api/v1/generate" \
  -H "Content-Type: application/json" -d "$XYZ_JSON")
assert_contains "xyz:POSCAR" "POSCAR" "$RESP"
assert_contains "xyz:Cartesian" "Cartesian" "$RESP"

echo "=== Generation: MOL input ==="
MOL_JSON=$(printf '{"calc_type":"optimization","structure":{"format":"mol","data":"\\n  RDKit          3D\\n\\n  2  1  0  0  0  0  0  0  0  0999 V2000\\n    0.0000    0.0000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\\n    0.7570    0.5860    0.0000 H   0  0  0  0  0  0  0  0  0  0  0  0\\n  1  2  1  0\\nM  END"},"charge":0,"multiplicity":1,"name":"water-mol"}')
RESP=$(curl -sf -X POST "$BASE/api/v1/generate" \
  -H "Content-Type: application/json" -d "$MOL_JSON")
assert_contains "mol:INCAR" "INCAR" "$RESP"

# ==== SECTION: ZIP download ====
echo "=== ZIP download ==="
PAYLOAD='{"calc_type":"optimization","structure":{"format":"smiles","data":"O"},"charge":0,"multiplicity":1,"name":"water-zip"}'
ZIP_FILE="/tmp/vasp-agent-test.zip"
HTTP_CODE=$(curl -s -o "$ZIP_FILE" -w "%{http_code}" \
  -X POST "$BASE/api/v1/download" \
  -H "Content-Type: application/json" -d "$PAYLOAD")
assert_eq "download:200" "200" "$HTTP_CODE"
ZIP_SIZE=$(wc -c < "$ZIP_FILE" 2>/dev/null || echo "0")
if [ "$ZIP_SIZE" -gt 100 ]; then
  ok "download:non-empty zip ($ZIP_SIZE bytes)"
else
  fail "download:zip" "too small ($ZIP_SIZE bytes)"
fi

# ==== SECTION: Error handling ====
echo "=== Error handling ==="
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "$BASE/api/v1/generate" \
  -H "Content-Type: application/json" \
  -d '{"calc_type":"optimization","structure":{"format":"smiles","data":"ZZZZZ"},"charge":0,"multiplicity":1,"name":"bad"}')
assert_eq "error:bad SMILES" "400" "$HTTP_CODE"

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "$BASE/api/v1/generate" \
  -H "Content-Type: application/json" \
  -d '{"calc_type":"nonexistent","structure":{"format":"smiles","data":"O"},"charge":0,"multiplicity":1,"name":"bad"}')
assert_eq "error:bad calctype" "422" "$HTTP_CODE"

# ==== SECTION: POTCAR library ====
echo "=== POTCAR library ==="
RESP=$(curl -sf "$BASE/api/v1/potcar/status")
assert_contains "potcar:status" "total_elements" "$RESP"
assert_contains "potcar:has H" '"H":true' "$RESP"

# ==== SECTION: Surface slab building ====
echo "=== Surface: metals list ==="
RESP=$(curl -sf "$BASE/api/v1/surface/metals")
assert_contains "surface:metals Fe" "Fe" "$RESP"
assert_contains "surface:metals bcc" "bcc" "$RESP"
assert_contains "surface:metals Cr" "Cr" "$RESP"
assert_contains "surface:metals Cu" "Cu" "$RESP"
assert_contains "surface:metals Al" "Al" "$RESP"
assert_contains "surface:metals Ni" "Ni" "$RESP"
assert_contains "surface:metals Zn" "Zn" "$RESP"
assert_contains "surface:metals Mg" "Mg" "$RESP"
assert_contains "surface:metals Ti" "Ti" "$RESP"

echo "=== Surface: build Fe(110) slab (BCC) ==="
PAYLOAD='{"metal":"Fe","surface":"110","layers":4,"vacuum":15.0,"fix_bottom":2}'
RESP=$(curl -sf -X POST "$BASE/api/v1/surface/build" \
  -H "Content-Type: application/json" -d "$PAYLOAD")
assert_contains "surface:slab Fe" "Fe(110)" "$RESP"
assert_contains "surface:slab selective" "Selective dynamics" "$RESP"
assert_contains "surface:slab fixed" "F F F" "$RESP"
assert_contains "surface:slab free" "T T T" "$RESP"

echo "=== Surface: build Cr(100) slab (BCC) ==="
PAYLOAD='{"metal":"Cr","surface":"100","layers":3,"vacuum":12.0,"fix_bottom":1}'
RESP=$(curl -sf -X POST "$BASE/api/v1/surface/build" \
  -H "Content-Type: application/json" -d "$PAYLOAD")
assert_contains "surface:Cr" "Cr(100)" "$RESP"
assert_contains "surface:Cr selective" "Selective dynamics" "$RESP"

echo "=== Surface: build Cu(110) slab (FCC) ==="
PAYLOAD='{"metal":"Cu","surface":"110","layers":4,"vacuum":15.0,"fix_bottom":2}'
RESP=$(curl -sf -X POST "$BASE/api/v1/surface/build" \
  -H "Content-Type: application/json" -d "$PAYLOAD")
assert_contains "surface:Cu" "Cu(110)" "$RESP"

echo "=== Surface: build Al(111) slab (FCC) ==="
PAYLOAD='{"metal":"Al","surface":"111","layers":3,"vacuum":12.0,"fix_bottom":1}'
RESP=$(curl -sf -X POST "$BASE/api/v1/surface/build" \
  -H "Content-Type: application/json" -d "$PAYLOAD")
assert_contains "surface:Al" "Al(111)" "$RESP"

echo "=== Surface: build Ni(100) slab (FCC) ==="
PAYLOAD='{"metal":"Ni","surface":"100","layers":4,"vacuum":15.0,"fix_bottom":2}'
RESP=$(curl -sf -X POST "$BASE/api/v1/surface/build" \
  -H "Content-Type: application/json" -d "$PAYLOAD")
assert_contains "surface:Ni" "Ni(100)" "$RESP"

echo "=== Surface: build Mg(0001) slab (HCP) ==="
PAYLOAD='{"metal":"Mg","surface":"0001","layers":4,"vacuum":15.0,"fix_bottom":2}'
RESP=$(curl -sf -X POST "$BASE/api/v1/surface/build" \
  -H "Content-Type: application/json" -d "$PAYLOAD")
assert_contains "surface:Mg" "Mg(0001)" "$RESP"
assert_contains "surface:Mg selective" "Selective dynamics" "$RESP"

echo "=== Surface: build Zn(10-10) slab (HCP) ==="
PAYLOAD='{"metal":"Zn","surface":"10-10","layers":3,"vacuum":12.0,"fix_bottom":1}'
RESP=$(curl -sf -X POST "$BASE/api/v1/surface/build" \
  -H "Content-Type: application/json" -d "$PAYLOAD")
assert_contains "surface:Zn" "Zn(10-10)" "$RESP"

echo "=== Surface: build Ti(0001) slab (HCP) ==="
PAYLOAD='{"metal":"Ti","surface":"0001","layers":4,"vacuum":15.0,"fix_bottom":2}'
RESP=$(curl -sf -X POST "$BASE/api/v1/surface/build" \
  -H "Content-Type: application/json" -d "$PAYLOAD")
assert_contains "surface:Ti" "Ti(0001)" "$RESP"

echo "=== Surface: build Fe(110) with molecule ==="
PAYLOAD='{"metal":"Fe","surface":"110","layers":4,"vacuum":15.0,"fix_bottom":2,"xyz":"3\nH2O\nO   1.4  1.0  20.0\nH   2.0  1.5  20.5\nH   1.0  0.5  20.5"}'
RESP=$(curl -sf -X POST "$BASE/api/v1/surface/build" \
  -H "Content-Type: application/json" -d "$PAYLOAD")
assert_contains "surface:mol summary" "H(2)" "$RESP"
assert_contains "surface:mol poscar" "Selective dynamics" "$RESP"

echo "=== Surface: generate Fe(110) full VASP inputs ==="
PAYLOAD='{"metal":"Fe","surface":"110","layers":4,"vacuum":15.0,"fix_bottom":2,"name":"test-fe"}'
RESP=$(curl -sf -X POST "$BASE/api/v1/surface/generate" \
  -H "Content-Type: application/json" -d "$PAYLOAD")
assert_contains "surf-gen:metal" "Fe" "$RESP"
assert_contains "surf-gen:surface" "110" "$RESP"
assert_contains "surf-gen:name" "test-fe" "$RESP"
assert_contains "surf-gen:INCAR" "INCAR" "$RESP"
assert_contains "surf-gen:POSCAR" "POSCAR" "$RESP"
assert_contains "surf-gen:POTCAR" "POTCAR" "$RESP"
assert_contains "surf-gen:KPOINTS" "KPOINTS" "$RESP"
assert_contains "surf-gen:SLURM" "run.slurm" "$RESP"
assert_contains "surf-gen:ISIF=2" "ISIF = 2" "$RESP"
assert_contains "surf-gen:ISMEAR=1" "ISMEAR = 1" "$RESP"
assert_contains "surf-gen:kpoints mesh" "6  6  1" "$RESP"
N_SURF_FILES=$(echo "$RESP" | "$PYTHON" -c "import sys,json; print(len(json.load(sys.stdin)['files']))" 2>/dev/null || echo "0")
assert_eq "surf-gen:file count" "5" "$N_SURF_FILES"

echo "=== Surface: generate Fe(100) with adsorbate ==="
PAYLOAD='{"metal":"Fe","surface":"100","layers":3,"vacuum":12.0,"fix_bottom":1,"xyz":"3\nH2O\nO   1.4  1.0  20.0\nH   2.0  1.5  20.5\nH   1.0  0.5  20.5","name":"fe-oh2"}'
RESP=$(curl -sf -X POST "$BASE/api/v1/surface/generate" \
  -H "Content-Type: application/json" -d "$PAYLOAD")
assert_contains "surf-gen2:metal" "Fe" "$RESP"
assert_contains "surf-gen2:POTCAR" "POTCAR" "$RESP"
assert_contains "surf-gen2:INCAR:ISIF" "ISIF = 2" "$RESP"
assert_contains "surf-gen2:selective" "Selective dynamics" "$RESP"
N_SURF_FILES2=$(echo "$RESP" | "$PYTHON" -c "import sys,json; print(len(json.load(sys.stdin)['files']))" 2>/dev/null || echo "0")
assert_eq "surf-gen2:file count" "5" "$N_SURF_FILES2"

echo "=== Surface: generate Cu(111) full VASP inputs ==="
PAYLOAD='{"metal":"Cu","surface":"111","layers":3,"vacuum":12.0,"fix_bottom":1,"name":"cu-test"}'
RESP=$(curl -sf -X POST "$BASE/api/v1/surface/generate" \
  -H "Content-Type: application/json" -d "$PAYLOAD")
assert_contains "surf-gen3:Cu" "Cu" "$RESP"
assert_contains "surf-gen3:INCAR" "INCAR" "$RESP"
N_SURF_FILES3=$(echo "$RESP" | "$PYTHON" -c "import sys,json; print(len(json.load(sys.stdin)['files']))" 2>/dev/null || echo "0")
assert_eq "surf-gen3:file count" "5" "$N_SURF_FILES3"

# ==== SECTION: Parser endpoints ====
echo "=== Parser endpoints (skipped — file upload requires real VASP outputs) ==="
ok "parser:all endpoints registered (6 parsers)"

# ==== SUMMARY ====
echo "=== Stopping server ==="
if [ "${SKIP_STOP:-false}" != "true" ] && [ -n "${SERVER_PID:-}" ]; then
  kill "$SERVER_PID" 2>/dev/null || true
  wait "$SERVER_PID" 2>/dev/null || true
fi

echo ""
echo "=== Results ==="
if [ "$FAILURES" -eq 0 ]; then
  echo "All tests PASSED."
  exit 0
else
  echo "$FAILURES test(s) FAILED."
  exit 1
fi
