---
name: run-vasp-agent
description: Build, run, drive, and screenshot the VASP Agent web app. Use when asked to start VASP Agent, launch the server, test input generation, take a screenshot, or interact with the running app.
---

VASP Agent — automated VASP input generation and output analysis web tool.  
Backend: FastAPI + RDKit + ASE.  Frontend: vanilla HTML/CSS/JS.  
Drive it via `curl` for the API, or `chrome --headless` for screenshots.

All paths below are relative to `backend/` unless noted otherwise.

## Prerequisites

```bash
# Python 3.14 (RDKit prebuilt wheels target this version)
# If using a newer Python (3.15+), RDKit wheels may not exist —
# install Python 3.14 and use `py -3.14` instead of `python`.
```

## Setup

```bash
cd backend
py -3.14 -m pip install fastapi uvicorn pydantic rdkit numpy ase
```

No build step. No env vars required (POTCAR library path defaults to `backend/potcar_library/`).

## Run (agent path)

Use the smoke script — it starts the server, runs 26 checks, and stops it:

```bash
# From project root:
bash .claude/skills/run-vasp-agent/smoke.sh
```

Or start/stop manually:

```bash
cd backend
py -3.14 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
# Wait for ready:
curl -s http://localhost:8000/api/v1/health
# → {"status":"ok"}

# Quick generation test:
curl -s -X POST http://localhost:8000/api/v1/generate \
  -H "Content-Type: application/json" \
  -d '{"calc_type":"optimization","structure":{"format":"smiles","data":"O"},"charge":0,"multiplicity":1,"name":"water"}'

# Stop:
pkill -f "uvicorn app.main:app"
```

### API endpoints

| method | path | purpose |
|---|---|---|
| GET | `/api/v1/health` | health check |
| GET | `/api/v1/calc-types` | list supported calc types + input formats |
| POST | `/api/v1/generate` | generate VASP input files (INCAR, POSCAR, POTCAR, KPOINTS, SLURM) |
| POST | `/api/v1/download` | generate + return ZIP |
| POST | `/api/v1/analyze/{outcar,eigenval,oszicar,vasprun,xdatcar,contcar}` | parse VASP output (multipart file upload) |
| GET | `/api/v1/potcar/status` | POTCAR library status (94-element map) |
| POST | `/api/v1/potcar/import` | import one POTCAR (auto-detect element) |
| POST | `/api/v1/potcar/import-multi` | bulk import POTCARs |
| DELETE | `/api/v1/potcar/{element}` | remove one POTCAR |
| GET | `/` | serve frontend SPA |
| GET | `/{filename}` | serve static assets (js, css) |

### Screenshots

Chrome/Edge headless on Windows:

```bash
mkdir -p /tmp/vasp-agent-shots
"/c/Program Files/Google/Chrome/Application/chrome.exe" \
  --headless=new --disable-gpu --window-size=1280,1400 \
  --screenshot="/tmp/vasp-agent-shots/vasp-agent.png" \
  --virtual-time-budget=8000 \
  "http://localhost:8000"
```

Screenshots → `/tmp/vasp-agent-shots/`.

## Run (human path)

```bash
cd backend
py -3.14 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000` in a browser → fill in SMILES/公式/坐标 → choose calculation type → click 生成.  Stop with Ctrl-C.

## Test

There is no formal test suite. The smoke script is the test:

```bash
bash .claude/skills/run-vasp-agent/smoke.sh
```

Expected: "All tests PASSED." covering health, frontend serving, generation (4 calc types × 4 input formats), ZIP download, error handling, and POTCAR library.

## Gotchas

- **Python 3.15+**: RDKit has no prebuilt wheels. Use Python 3.14 (`py -3.14`).
- **POTCAR files are proprietary**: The library ships empty. Users must import their own VASP pseudopotentials via the UI or API.
- **Windows `bash` heredoc hang**: Multi-line inline Python in bash scripts hangs on msys2. Use single-line `printf` for JSON payloads or a Python helper file instead.
- **curl file upload on Windows**: `curl -F "file=@/path/file"` with msys2 curl may crash (exit 26). Use Python `requests` or the browser for file-upload endpoints.
- **CIF input requires ASE**: If `ase` is not installed, CIF parsing fails at runtime. Install with `pip install ase`.
- **Port conflict**: The smoke script reuses an already-running server on port 8000. If you want to start fresh, `pkill -f uvicorn` first.
