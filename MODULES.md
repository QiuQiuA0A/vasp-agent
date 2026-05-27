# VASP Agent — Project Module Map

Total: ~4,448 lines. File listing grouped by module, with line counts and responsibilities.

## 1. Entry Point & Config (132 lines)
| File | Lines | Purpose |
|------|-------|---------|
| `backend/app/main.py` | 36 | FastAPI startup, CORS, static file serving |
| `backend/app/core/config.py` | 96 | Env vars, SLURM defaults, VASP parameter presets |

## 2. API Routes (443 lines)
| File | Lines | Purpose |
|------|-------|---------|
| `backend/app/api/routes.py` | 443 | All endpoints: generate, download, analyze x6, POTCAR, surface |

## 3. Data Models (90 lines)
| File | Lines | Purpose |
|------|-------|---------|
| `backend/app/models/schemas.py` | 90 | Pydantic request/response models, enums |

## 4. Core Generation Services (558 lines)
| File | Lines | Purpose |
|------|-------|---------|
| `backend/app/services/vasp_input.py` | 292 | Main generation flow: INCAR/POSCAR/POTCAR/KPOINTS/SLURM |
| `backend/app/services/vasp_templates.py` | 136 | Template engine: render_incar(), render_kpoints(), render_slurm() |
| `backend/app/services/modeling.py` | 265 | Structure parsing: SMILES->XYZ, formula->3D, CIF/XYZ/MOL |

## 5. POTCAR Management (190 lines)
| File | Lines | Purpose |
|------|-------|---------|
| `backend/app/services/potcar.py` | 70 | POTCAR concatenation, element path lookup |
| `backend/app/services/potcar_manager.py` | 120 | Library management: import/delete/stats/multi-functional |

## 6. Surface Slab Modeling (366 lines)
| File | Lines | Purpose |
|------|-------|---------|
| `backend/app/services/surface.py` | 366 | Metal registry, SlabGenerator, POSCAR+INCAR for surfaces |

## 7. Result Parsers (1,103 lines)
| File | Lines | Parses |
|------|-------|--------|
| `backend/app/services/parsers/outcar.py` | 220 | Energy, forces, HOMO/LUMO, dipole |
| `backend/app/services/parsers/vasprun.py` | 298 | Full XML: energies/forces/bands/DOS/dielectric |
| `backend/app/services/parsers/oszicar.py` | 248 | SCF convergence diagnostics |
| `backend/app/services/parsers/xdatcar.py` | 133 | MD trajectory |
| `backend/app/services/parsers/contcar.py` | 118 | Final structure, XYZ export |
| `backend/app/services/parsers/eigenval.py` | 86 | Band eigenvalues, gap |

## 8. User Experience (113 lines)
| File | Lines | Purpose |
|------|-------|---------|
| `backend/app/services/user_messages.py` | 113 | Technical error -> friendly Chinese messages |

## 9. Frontend (1,318 lines)
| File | Lines | Purpose |
|------|-------|---------|
| `frontend/index.html` | 253 | Page structure |
| `frontend/app.js` | 654 | Interaction logic, 3D viewer, file upload |
| `frontend/style.css` | 411 | Styles |

## 10. Tests (338 lines)
| File | Lines | Purpose |
|------|-------|---------|
| `.claude/skills/run-vasp-agent/smoke.sh` | 338 | Smoke tests (81 assertions) |
