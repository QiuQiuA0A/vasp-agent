from app.core.config import VASP_DEFAULTS, COMMON_DEFAULTS
from app.services.modeling import parse_structure, get_formula, get_element_list_from_xyz
from app.services.potcar import generate_potcar, assess_potcar_availability
from app.services.vasp_templates import render_incar, render_kpoints, render_slurm
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

    calc_sets = _build_calc_sets(request, is_crystal)

    files: list[FileContent] = []
    for calc_step in calc_sets:
        incar = render_incar(calc_step["params"], calc_step["label"])
        poscar = _generate_poscar(xyz_str, formula, lattice)
        potcar = generate_potcar(elements, request.functional)
        kpoints = render_kpoints((4, 4, 4) if is_crystal else (1, 1, 1))
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


def _build_calc_sets(request: VASPRequest, is_crystal: bool) -> list[dict]:
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


def _build_summary(request: VASPRequest, formula: str, elements: list[str], n_steps: int) -> str:
    calc_labels = {
        "optimization": "结构优化 (Geometry Optimization)",
        "homo_lumo": "HOMO-LUMO 计算 (优化 + 静态计算)",
        "dipole": "偶极矩计算 (Dipole Moment)",
        "aimd": "分子动力学模拟 (AIMD, NVT 系综)",
    }
    return (
        f"分子式: {formula}\n"
        f"元素: {', '.join(elements)}\n"
        f"计算类型: {calc_labels.get(request.calc_type, request.calc_type)}\n"
        f"计算步数: {n_steps}\n"
        f"输入格式: {request.structure.format.value}\n"
        f"电荷: {request.charge}  自旋多重度: {request.multiplicity}"
    )
