from app.core.config import VASP_DEFAULTS, COMMON_DEFAULTS
from app.services.modeling import parse_structure, get_formula, get_element_list_from_xyz
from app.services.potcar import generate_potcar, assess_potcar_availability
from app.services.vasp_templates import (
    render_incar, render_kpoints, render_kpoints_kspacing,
    render_kpoints_band, render_slurm, BAND_PATHS,
)
from app.models.schemas import CalcType, VASPRequest, CalculationResponse, FileContent


def generate_vasp_files(request: VASPRequest) -> CalculationResponse:
    """Generate all VASP input files for a calculation request."""
    warnings: list[str] = []

    xyz_str, mol, lattice = parse_structure(
        request.structure.data, request.structure.format.value
    )
    elements = get_element_list_from_xyz(xyz_str)
    formula = get_formula(mol)
    is_crystal = lattice is not None

    potcar_avail = assess_potcar_availability(elements, request.functional)
    missing = [el for el, ok in potcar_avail.items() if not ok]
    if missing:
        warnings.append(
            f"POTCAR files missing for: {', '.join(missing)}. "
            f"Place {request.functional} POTCARs in potcar_library/{request.functional}/<element>/POTCAR."
        )

    calc_sets = _build_calc_sets(request, is_crystal, lattice)

    files: list[FileContent] = []
    for calc_step in calc_sets:
        incar = render_incar(calc_step["params"], calc_step["label"])
        poscar = _generate_poscar(xyz_str, formula, lattice)
        potcar = generate_potcar(elements, request.functional)
        kpoints = calc_step.get("kpoints", _default_kpoints(is_crystal, request.calc_type))
        slurm = render_slurm(_sanitize_jobname(formula))

        prefix = calc_step["prefix"]
        files.extend([
            FileContent(filename=f"{prefix}_INCAR", content=incar),
            FileContent(filename=f"{prefix}_POSCAR", content=poscar),
            FileContent(filename=f"{prefix}_POTCAR", content=potcar),
            FileContent(filename=f"{prefix}_KPOINTS", content=kpoints),
            FileContent(filename=f"{prefix}_run.slurm", content=slurm),
        ])

    return CalculationResponse(
        calc_type=request.calc_type,
        name=request.name,
        files=files,
        warnings=warnings,
        summary=_build_summary(request, formula, elements, len(calc_sets)),
    )


def _build_calc_sets(request: VASPRequest, is_crystal: bool,
                     lattice: list[tuple[float, float, float]] | None = None) -> list[dict]:
    """Build the list of calculation steps needed."""
    base_params = dict(COMMON_DEFAULTS)

    if request.encut is not None:
        base_params["ENCUT"] = request.encut

    if is_crystal:
        base_params["ISMEAR"] = 1
        base_params["SIGMA"] = 0.1

    if request.calc_type == CalcType.OPTIMIZATION:
        params = {**base_params, **VASP_DEFAULTS["optimization"]}
        if request.nsw is not None:
            params["NSW"] = request.nsw
        return [{"label": "Geometry Optimization", "prefix": "opt", "params": params}]

    elif request.calc_type == CalcType.HOMO_LUMO:
        opt_params = {**base_params, **VASP_DEFAULTS["optimization"]}
        static_params = {**base_params, **VASP_DEFAULTS["static"]}
        return [
            {"label": "Step 1 - Optimization", "prefix": "opt", "params": opt_params},
            {"label": "Step 2 - Static (HOMO-LUMO)", "prefix": "static", "params": static_params},
        ]

    elif request.calc_type == CalcType.DIPOLE:
        static_params = {**base_params, **VASP_DEFAULTS["dipole"]}
        return [{"label": "Static with Dipole", "prefix": "dipole", "params": static_params}]

    elif request.calc_type == CalcType.AIMD:
        params = {**base_params, **VASP_DEFAULTS["aimd"]}
        if request.temperature is not None:
            params["TEBEG"] = request.temperature
            params["TEEND"] = request.temperature
        if request.nsw is not None:
            params["NSW"] = request.nsw
        return [{"label": "AIMD (NVT)", "prefix": "aimd", "params": params}]

    elif request.calc_type == CalcType.FREQUENCY:
        params = {**base_params, **VASP_DEFAULTS["frequency"]}
        if request.encut is not None:
            params["ENCUT"] = request.encut
        return [{"label": "Vibrational Frequencies", "prefix": "freq", "params": params}]

    elif request.calc_type == CalcType.DOS:
        params = {**base_params, **VASP_DEFAULTS["dos"]}
        if request.encut is not None:
            params["ENCUT"] = request.encut
        kpoints = render_kpoints((8, 8, 8)) if is_crystal else render_kpoints((1, 1, 1))
        return [{"label": "DOS Calculation", "prefix": "dos", "params": params, "kpoints": kpoints}]

    elif request.calc_type == CalcType.BAND:
        if not is_crystal:
            raise ValueError("Band structure calculations require a periodic system (CIF input).")
        scf_params = {**base_params, **VASP_DEFAULTS["static"]}
        band_params = {**base_params, **VASP_DEFAULTS["band"]}
        if request.encut is not None:
            scf_params["ENCUT"] = request.encut
            band_params["ENCUT"] = request.encut
        scf_kpoints = render_kpoints((8, 8, 8), "Gamma", "Band - SCF mesh")
        band_kpoints = render_kpoints_band(_guess_band_path(lattice))
        return [
            {"label": "Step 1 - SCF (Band)", "prefix": "scf", "params": scf_params, "kpoints": scf_kpoints},
            {"label": "Step 2 - Band Structure", "prefix": "band", "params": band_params, "kpoints": band_kpoints},
        ]

    elif request.calc_type == CalcType.WORK_FUNCTION:
        params = {**base_params, **VASP_DEFAULTS["work_function"]}
        if request.encut is not None:
            params["ENCUT"] = request.encut
        kpoints = render_kpoints((6, 6, 6)) if is_crystal else render_kpoints((1, 1, 1))
        return [{"label": "Work Function", "prefix": "wf", "params": params, "kpoints": kpoints}]

    raise NotImplementedError(f"Unknown calc_type: {request.calc_type}")


def _sanitize_jobname(formula: str) -> str:
    return "".join(c for c in formula if c.isalnum() or c in "_-")


def _generate_poscar(
    xyz_str: str,
    formula: str,
    lattice: list[tuple[float, float, float]] | None = None,
) -> str:
    """Convert XYZ to POSCAR format. Uses lattice vectors for crystals, auto-box for molecules."""
    lines = xyz_str.strip().split("\n")
    atoms_data = []
    species_order = []

    for line in lines:
        parts = line.strip().split()
        if len(parts) >= 4:
            symbol = parts[0]
            if len(symbol) > 2 or not symbol[0].isalpha():
                continue
            try:
                x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                atoms_data.append((symbol, x, y, z))
                if symbol not in species_order:
                    species_order.append(symbol)
            except ValueError:
                continue

    if not atoms_data:
        return "# POSCAR - empty\n"

    counts = {s: sum(1 for a in atoms_data if a[0] == s) for s in species_order}

    if lattice:
        poscar_lines = [
            f"{formula}",
            "1.0",
            f"  {lattice[0][0]:12.8f}  {lattice[0][1]:12.8f}  {lattice[0][2]:12.8f}",
            f"  {lattice[1][0]:12.8f}  {lattice[1][1]:12.8f}  {lattice[1][2]:12.8f}",
            f"  {lattice[2][0]:12.8f}  {lattice[2][1]:12.8f}  {lattice[2][2]:12.8f}",
            "  " + "  ".join(species_order),
            "  " + "  ".join(str(counts[s]) for s in species_order),
            "Cartesian",
        ]
        for symbol, x, y, z in atoms_data:
            poscar_lines.append(f"  {x:14.8f}  {y:14.8f}  {z:14.8f}")
    else:
        xs = [a[1] for a in atoms_data]
        ys = [a[2] for a in atoms_data]
        zs = [a[3] for a in atoms_data]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        min_z, max_z = min(zs), max(zs)
        span_x, span_y, span_z = max_x - min_x, max_y - min_y, max_z - min_z
        padding = max(span_x, span_y, span_z) * 0.3 + 8.0
        center = ((max_x + min_x) / 2, (max_y + min_y) / 2, (max_z + min_z) / 2)
        lattice_const = max(span_x, span_y, span_z) + padding

        poscar_lines = [
            f"{formula}",
            "1.0",
            f"{lattice_const:12.6f} 0.000000 0.000000",
            f"0.000000 {lattice_const:12.6f} 0.000000",
            f"0.000000 0.000000 {lattice_const:12.6f}",
            "  " + "  ".join(species_order),
            "  " + "  ".join(str(counts[s]) for s in species_order),
            "Cartesian",
        ]
        for symbol, x, y, z in atoms_data:
            poscar_lines.append(
                f"  {x - center[0]:14.8f}  {y - center[1]:14.8f}  {z - center[2]:14.8f}"
            )

    poscar_lines.append("")
    return "\n".join(poscar_lines)


def _default_kpoints(is_crystal: bool, calc_type: CalcType) -> str:
    """Return default KPOINTS string for a given system and calculation type."""
    if not is_crystal:
        return render_kpoints((1, 1, 1))
    if calc_type == CalcType.DOS:
        return render_kpoints((8, 8, 8), "Gamma", "DOS dense mesh")
    if calc_type == CalcType.WORK_FUNCTION:
        return render_kpoints((6, 6, 6), "Gamma", "Work function mesh")
    return render_kpoints((4, 4, 4))


def _classify_lattice(lattice: list[tuple[float, float, float]]) -> str:
    """Classify the Bravais lattice type from real-space vectors.

    Returns one of: cubic, tetragonal, orthorhombic, hexagonal, monoclinic, generic.
    """
    import math

    a, b, c = lattice

    def _norm(v):
        return math.sqrt(v[0]**2 + v[1]**2 + v[2]**2)

    def _angle(v1, v2):
        dot = v1[0]*v2[0] + v1[1]*v2[1] + v1[2]*v2[2]
        n = _norm(v1) * _norm(v2)
        cos = max(-1.0, min(1.0, dot / (n + 1e-12)))
        return math.degrees(math.acos(cos))

    na, nb, nc = _norm(a), _norm(b), _norm(c)

    # Angles: α = ∠(b,c), β = ∠(a,c), γ = ∠(a,b)
    alpha = _angle(b, c)
    beta = _angle(a, c)
    gamma = _angle(a, b)

    # Relative length tolerance: 5%
    def len_eq(x, y):
        return abs(x - y) / max(x, y, 0.01) < 0.05

    def is_90(ang):
        return abs(ang - 90.0) < 2.0

    ab = len_eq(na, nb)
    bc = len_eq(nb, nc)
    ac = len_eq(na, nc)

    all_90 = is_90(alpha) and is_90(beta) and is_90(gamma)

    # Cubic: a = b = c, all 90°
    if ab and bc and all_90:
        return "cubic"

    # Tetragonal: a = b ≠ c, all 90°
    if ab and not bc and all_90:
        return "tetragonal"
    if ac and not ab and all_90:
        return "tetragonal"

    # Orthorhombic: all angles 90°, all lengths differ
    if all_90 and not ab and not bc and not ac:
        return "orthorhombic"

    # Hexagonal: a = b ≠ c, α = β = 90°, γ = 120°
    if ab and not bc and is_90(alpha) and is_90(beta) and abs(gamma - 120.0) < 5.0:
        return "hexagonal"

    # Monoclinic: exactly two 90° angles
    n90 = sum(1 for ang in (alpha, beta, gamma) if is_90(ang))
    if n90 == 2:
        return "monoclinic"

    return "generic"


def _guess_band_path(lattice: list[tuple[float, float, float]] | None) -> list[tuple[float, float, float, str]]:
    """Guess the high-symmetry k-path for a lattice, with proper classification.

    Uses standardized paths from Seek-path / AFLOW conventions.
    Falls back to a generic Γ→X→M→Y→Γ→Z path for unrecognized lattices.
    """
    if lattice is None:
        return BAND_PATHS["generic"]

    lat_type = _classify_lattice(lattice)

    # Map classification to standard paths:
    # - cubic/fcc → unified cubic path (Γ-X-U-K-Γ-L-W-K)
    # - bcc → special bcc path (we detect cubic but can't separate bcc from vectors)
    # - tetragonal → Γ-X-M-Γ-Z-R-A-Z
    # - orthorhombic → Γ-X-S-Y-Γ-Z-U-R-T-Z
    # - hexagonal → hcp path
    # - monoclinic / generic → basic Γ-X-M-Y-Γ-Z path
    if lat_type == "cubic":
        return BAND_PATHS["fcc"]
    if lat_type == "hexagonal":
        return BAND_PATHS["hcp"]

    return BAND_PATHS.get(lat_type, BAND_PATHS["generic"])


def _build_summary(request: VASPRequest, formula: str, elements: list[str], n_steps: int) -> str:
    calc_labels = {
        "optimization": "结构优化 (Geometry Optimization)",
        "homo_lumo": "HOMO-LUMO 计算 (优化 + 静态计算)",
        "dipole": "偶极矩计算 (Dipole Moment)",
        "aimd": "分子动力学模拟 (AIMD, NVT 系综)",
        "frequency": "振动频率 (Vibrational Frequencies)",
        "dos": "态密度 (Density of States)",
        "band": "能带结构 (Band Structure)",
        "work_function": "功函数 (Work Function)",
    }
    return (
        f"分子式: {formula}\n"
        f"元素: {', '.join(elements)}\n"
        f"计算类型: {calc_labels.get(request.calc_type, request.calc_type)}\n"
        f"计算步数: {n_steps}\n"
        f"输入格式: {request.structure.format.value}\n"
        f"电荷: {request.charge}  自旋多重度: {request.multiplicity}"
    )
