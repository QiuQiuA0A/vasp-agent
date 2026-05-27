import io
import zipfile
from fastapi import APIRouter, HTTPException, File, UploadFile
from fastapi.responses import StreamingResponse
from app.models.schemas import VASPRequest, CalculationResponse, SurfaceRequest, SurfaceResponse, SurfaceGenerateRequest
from app.services.vasp_input import generate_vasp_files
from app.services.surface import (
    build_slab, get_poscar, list_metals, SlabConfig, generate_surface_files,
)
from app.services.parsers.outcar import parse_outcar
from app.services.parsers.eigenval import parse_eigenval
from app.services.parsers.oszicar import parse_oszicar
from app.services.parsers.vasprun import parse_vasprun
from app.services.parsers.xdatcar import parse_xdatcar
from app.services.parsers.contcar import parse_contcar, contcar_to_xyz
from app.services.potcar_manager import (
    library_stats,
    list_functionals,
    detect_element,
    import_potcar,
    remove_potcar,
    bulk_import,
)
from app.services.user_messages import translate

router = APIRouter()


def _friendly_error(exc: Exception, status_code: int = 400) -> HTTPException:
    """Convert a technical exception to a user-friendly HTTPException."""
    msg = translate(str(exc))
    return HTTPException(
        status_code=status_code,
        detail={"error": msg.message, "suggestion": msg.suggestion},
    )


@router.post("/generate", response_model=CalculationResponse)
async def generate_input_files(request: VASPRequest):
    """Generate VASP input files for a given structure and calculation type."""
    try:
        return generate_vasp_files(request)
    except ValueError as e:
        raise _friendly_error(e, 400)
    except NotImplementedError as e:
        raise _friendly_error(e, 501)


@router.post("/download")
async def download_files(request: VASPRequest):
    """Generate VASP input files and return as a ZIP archive."""
    try:
        result = generate_vasp_files(request)
    except ValueError as e:
        raise _friendly_error(e, 400)
    except NotImplementedError as e:
        raise _friendly_error(e, 501)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        prefix = request.name or "vasp"
        for f in result.files:
            zf.writestr(f"{prefix}/{f.filename}", f.content)

    buf.seek(0)
    filename = f"{request.name or 'vasp'}_inputs.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/calc-types")
async def list_calc_types():
    """List supported calculation types with descriptions."""
    return {
        "calculation_types": {
            "optimization": {
                "name": "结构优化",
                "description": "Geometry optimization (ISIF=3, IBRION=2)",
                "steps": 1,
            },
            "homo_lumo": {
                "name": "HOMO-LUMO 计算",
                "description": "Optimization + static calculation with LORBIT=11",
                "steps": 2,
            },
            "dipole": {
                "name": "偶极矩",
                "description": "Static calculation with dipole correction",
                "steps": 1,
            },
            "aimd": {
                "name": "分子动力学",
                "description": "AIMD NVT ensemble with Nose-Hoover thermostat",
                "steps": 1,
            },
            "frequency": {
                "name": "振动频率",
                "description": "Vibrational frequency analysis (IBRION=5, NFREE=2)",
                "steps": 1,
            },
            "dos": {
                "name": "态密度 (DOS)",
                "description": "Density of states with dense k-mesh (NEDOS=2000, ISMEAR=-5)",
                "steps": 1,
            },
            "band": {
                "name": "能带结构",
                "description": "Band structure (SCF + non-SCF line-mode, requires CIF)",
                "steps": 2,
            },
            "work_function": {
                "name": "功函数",
                "description": "Work function (LVHAR, LVTOT) for surface systems",
                "steps": 1,
            },
        },
        "input_formats": ["smiles", "formula", "xyz", "cif", "mol"],
    }


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.post("/analyze/outcar")
async def analyze_outcar(file: UploadFile = File(...)):
    """Upload and parse an OUTCAR file. Returns extracted energies, forces, HOMO-LUMO, etc."""
    content = await file.read()
    text = content.decode("utf-8", errors="replace")
    if len(text) < 100:
        raise _friendly_error(ValueError("File too small — not a valid OUTCAR"), 400)

    result = parse_outcar(text)
    return {
        "filename": file.filename,
        "converged": result.converged,
        "total_energy_ev": result.total_energy,
        "fermi_energy_ev": result.fermi_energy,
        "max_force_ev_a": result.max_force,
        "n_scf_steps": result.n_scf_steps,
        "n_ionic_steps": result.n_ionic_steps,
        "dipole_moment_e_ang": list(result.dipole_moment) if result.dipole_moment else None,
        "dipole_total_e_ang": result.dipole_total,
        "homo_ev": result.homo,
        "lumo_ev": result.lumo,
        "gap_ev": result.gap,
        "lattice": result.lattice,
        "warnings": result.warnings,
    }


@router.post("/analyze/eigenval")
async def analyze_eigenval(file: UploadFile = File(...)):
    """Upload and parse an EIGENVAL file. Returns band structure info and HOMO-LUMO gap."""
    content = await file.read()
    text = content.decode("utf-8", errors="replace")
    if len(text) < 50:
        raise _friendly_error(ValueError("File too small — not a valid EIGENVAL"), 400)

    result = parse_eigenval(text)
    return result


@router.post("/analyze/oszicar")
async def analyze_oszicar(file: UploadFile = File(...)):
    """Upload and parse an OSZICAR file. Returns SCF convergence per ionic step and diagnostics."""
    content = await file.read()
    text = content.decode("utf-8", errors="replace")
    if len(text) < 50:
        raise _friendly_error(ValueError("File too small — not a valid OSZICAR"), 400)

    result = parse_oszicar(text)
    return {
        "filename": file.filename,
        "total_ionic_steps": result.total_ionic_steps,
        "total_scf_steps": result.total_scf_steps,
        "final_energy_ev": result.final_energy,
        "status": result.status,
        "diagnostics": result.diagnostics,
        "ionic_steps": [
            {
                "index": s.index,
                "n_scf": s.n_scf,
                "final_energy_ev": s.final_energy,
                "final_dE_ev": s.final_dE,
            }
            for s in result.ionic_steps
        ],
    }


@router.post("/analyze/vasprun")
async def analyze_vasprun(file: UploadFile = File(...)):
    """Upload and parse a vasprun.xml file. Extracts energies, forces, eigenvalues, DOS, etc."""
    content = await file.read()
    text = content.decode("utf-8", errors="replace")
    if len(text) < 200:
        raise _friendly_error(ValueError("File too small — not a valid vasprun.xml"), 400)
    if not text.strip().startswith("<?xml") and "<modeling>" not in text[:500]:
        raise _friendly_error(ValueError("Not a valid VASP vasprun.xml"), 400)

    result = parse_vasprun(text)
    return {
        "filename": file.filename,
        "system": result.system,
        "incar_params": result.incar_params,
        "n_ionic_steps": result.n_ionic_steps,
        "energies": result.energies,
        "forces_last": result.forces[-1] if result.forces else None,
        "stress_last": result.stress[-1] if result.stress else None,
        "homo_ev": result.homo,
        "lumo_ev": result.lumo,
        "gap_ev": result.gap,
        "fermi_from_dos_ev": result.fermi_from_dos,
        "n_eigenvalues": len(result.eigenvalues),
        "n_dos_points": len(result.dos_total),
        "n_pdos_points": len(result.dos_partial),
        "final_lattice": result.final_lattice,
        "final_positions": result.final_positions[:20],
        "dielectric": result.dielectric_data,
        "warnings": result.warnings,
    }


@router.post("/analyze/xdatcar")
async def analyze_xdatcar(file: UploadFile = File(...)):
    """Upload and parse an XDATCAR file. Returns MD trajectory summary."""
    content = await file.read()
    text = content.decode("utf-8", errors="replace")
    if len(text) < 100:
        raise _friendly_error(ValueError("File too small — not a valid XDATCAR"), 400)

    result = parse_xdatcar(text)
    return {
        "filename": file.filename,
        "formula": result.formula,
        "n_atoms": result.n_atoms,
        "n_frames": result.n_frames,
        "elements": result.elements,
        "counts": result.counts,
        "lattice": result.lattice,
        "first_frame_atoms": result.atoms_frame,
        # Per-frame energy-like proxy: last coordinate of each frame
        "frame_summary": [
            {"index": f.index, "n_atoms": len(f.positions)}
            for f in result.frames[:10]  # first 10 frames for preview
        ],
        "total_frames": result.n_frames,
        "first_atom_trajectory": _extract_atom_trajectory(result, 0),
    }


@router.post("/analyze/contcar")
async def analyze_contcar(file: UploadFile = File(...)):
    """Upload and parse a CONTCAR file. Returns final structure info."""
    content = await file.read()
    text = content.decode("utf-8", errors="replace")
    if len(text) < 50:
        raise _friendly_error(ValueError("File too small — not a valid CONTCAR"), 400)

    result = parse_contcar(text)
    return {
        "filename": file.filename,
        "formula": result.formula,
        "lattice_constant": result.lattice_constant,
        "lattice": result.lattice,
        "elements": result.elements,
        "counts": result.counts,
        "n_atoms": result.n_atoms,
        "coordinate_type": result.coordinate_type,
        "selective": result.selective,
        "atoms": result.atoms[:20],  # first 20 for preview
        "total_atoms": len(result.atoms),
        "xyz": contcar_to_xyz(result),
    }


def _extract_atom_trajectory(result, atom_idx: int) -> list[list[float]]:
    """Extract x,y,z trajectory for a single atom across frames."""
    traj = []
    for frame in result.frames:
        if atom_idx < len(frame.positions):
            traj.append(frame.positions[atom_idx])
    return traj


# ── POTCAR library management ──────────────────────────────────────────


@router.get("/potcar/status")
async def potcar_status(functional: str = "PBE"):
    """Get POTCAR library status for a given functional."""
    return library_stats(functional)


@router.get("/potcar/functionals")
async def potcar_functionals():
    """List available XC functionals with element counts."""
    return list_functionals()


@router.post("/potcar/import")
async def potcar_import(file: UploadFile = File(...)):
    """Import a single POTCAR file into the library. Element is auto-detected."""
    content = await file.read()
    text = content.decode("utf-8", errors="replace")
    if len(text) < 100:
        raise _friendly_error(ValueError("File too small — not a valid POTCAR"), 400)
    try:
        elem, folder = import_potcar(text)
        return {"status": "ok", "element": elem, "folder": folder}
    except ValueError as e:
        raise _friendly_error(e, 400)


@router.post("/potcar/import-multi")
async def potcar_import_multi(files: list[UploadFile] = File(...)):
    """Import multiple POTCAR files at once."""
    items = []
    for f in files:
        content = await f.read()
        text = content.decode("utf-8", errors="replace")
        items.append((f.filename, text))
    results = bulk_import(items)
    return {"results": results}


@router.delete("/potcar/{element}")
async def potcar_delete(element: str):
    """Remove a POTCAR for a given element from the library."""
    removed = remove_potcar(element)
    if not removed:
        raise HTTPException(404, detail={"error": f"POTCAR 库中未找到元素 '{element}' 的势文件", "suggestion": "该元素可能尚未导入，请先在 POTCAR 库管理页面导入"})
    return {"status": "removed", "element": element}


@router.post("/potcar/detect")
async def potcar_detect(file: UploadFile = File(...)):
    """Upload a POTCAR file to detect which element it contains."""
    content = await file.read()
    text = content.decode("utf-8", errors="replace")
    elem = detect_element(text)
    if not elem:
        raise _friendly_error(ValueError("Cannot detect element"), 400)
    return {"element": elem}


# ── Surface slab building ────────────────────────────────────────────────


@router.get("/surface/metals")
async def surface_metals():
    """List registered metals with available surface orientations."""
    return list_metals()


@router.post("/surface/build", response_model=SurfaceResponse)
async def surface_build(request: SurfaceRequest):
    """Build a metal slab, optionally with an adsorbed molecule.

    Supports Method B: user provides a pre-positioned XYZ for the adsorbate.
    """
    try:
        config = SlabConfig(
            metal=request.metal,
            surface=request.surface,
            layers=request.layers,
            vacuum=request.vacuum,
            fix_bottom=request.fix_bottom,
        )
        slab = build_slab(config)
        result = get_poscar(slab, config, request.xyz)

        summary_parts = [f"{result.metal}({result.surface}), {result.n_slab_atoms} 个金属原子"]
        if result.n_molecule_atoms > 0:
            summary_parts.append(
                f"吸附分子: {result.n_molecule_atoms} 个原子 "
                f"({' + '.join(f'{el}({c})' for el, c in zip(result.elements[1:], result.counts[1:]))})"
            )
        else:
            summary_parts.append("无吸附分子（纯表面）")

        return SurfaceResponse(
            metal=result.metal,
            surface=result.surface,
            n_slab_atoms=result.n_slab_atoms,
            n_molecule_atoms=result.n_molecule_atoms,
            n_total=result.n_total,
            poscar=result.poscar,
            elements=result.elements,
            counts=result.counts,
            summary=" | ".join(summary_parts),
        )
    except ValueError as e:
        raise _friendly_error(e, 400)
    except NotImplementedError as e:
        raise _friendly_error(e, 501)


@router.post("/surface/generate")
async def surface_generate(request: SurfaceGenerateRequest):
    """Build slab + generate all VASP input files (INCAR, POSCAR, POTCAR, KPOINTS, SLURM).

    Combines slab building with auto-generated INCAR/KPOINTS optimized for
    metal surface relaxation (ISIF=2, ISMEAR=1, Monkhorst-Pack k-points with kz=1).
    """
    from app.models.schemas import FileContent

    try:
        config = SlabConfig(
            metal=request.metal,
            surface=request.surface,
            layers=request.layers,
            vacuum=request.vacuum,
            fix_bottom=request.fix_bottom,
        )
        slab = build_slab(config)
        files = generate_surface_files(config, slab, request.xyz, request.functional)

        file_list = [
            FileContent(filename=name, content=content)
            for name, content in files.items()
        ]

        result = get_poscar(slab, config, request.xyz)
        summary_parts = [f"{result.metal}({result.surface}), {result.n_slab_atoms} slab atoms"]
        if result.n_molecule_atoms > 0:
            summary_parts.append(f"{result.n_molecule_atoms} molecule atoms")
        return {
            "metal": config.metal,
            "surface": config.surface,
            "name": request.name,
            "files": file_list,
            "summary": " | ".join(summary_parts),
        }
    except ValueError as e:
        raise _friendly_error(e, 400)
    except NotImplementedError as e:
        raise _friendly_error(e, 501)
