import io
import re
from collections import Counter

from rdkit import Chem
from rdkit.Chem import AllChem, RWMol
from rdkit.Geometry import Point3D


def smiles_to_xyz(smiles: str) -> tuple[str, Chem.Mol]:
    """Convert SMILES to XYZ string with 3D coordinates. Returns (xyz_string, mol_with_H)."""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"Invalid SMILES string: {smiles}")

    mol = Chem.AddHs(mol)

    status = AllChem.EmbedMolecule(mol, randomSeed=42)
    if status != 0:
        raise ValueError(
            f"Failed to generate 3D conformation for '{smiles}'. "
            "The molecule may be too constrained or have unusual bonding."
        )

    try:
        AllChem.MMFFOptimizeMolecule(mol)
    except Exception:
        AllChem.UFFOptimizeMolecule(mol)

    conf = mol.GetConformer()
    atoms = mol.GetAtoms()

    lines = [str(mol.GetNumAtoms()), smiles, ""]
    for atom in atoms:
        pos = conf.GetAtomPosition(atom.GetIdx())
        lines.append(f"{atom.GetSymbol():<2s}  {pos.x:10.6f}  {pos.y:10.6f}  {pos.z:10.6f}")

    return "\n".join(lines), mol


def parse_structure(data: str, input_format: str) -> tuple[str, Chem.Mol, list[tuple[float, float, float]] | None]:
    """Parse structure input and return (XYZ string, RDKit Mol, lattice_vectors or None)."""
    if input_format == "smiles":
        xyz, mol = smiles_to_xyz(data)
        return xyz, mol, None

    elif input_format == "formula":
        # Try SMILES first, fall back to chemical formula parsing
        mol = Chem.MolFromSmiles(data)
        if mol is not None:
            xyz, mol = smiles_to_xyz(data)
            return xyz, mol, None
        # Not a SMILES — try parsing as chemical formula (H2O, NaCl, Fe2O3, etc.)
        try:
            xyz, mol = _formula_to_xyz_mol(data)
            return xyz, mol, None
        except ValueError:
            raise ValueError(
                f"Cannot interpret '{data}' as SMILES or chemical formula. "
                "Provide a SMILES string (e.g. 'O' for water, 'c1ccccc1' for benzene) "
                "or a simple formula like 'H2O', 'NaCl', 'C6H6'."
            )

    elif input_format == "xyz":
        mol = _xyz_to_mol(data)
        return data, mol, None

    elif input_format == "cif":
        xyz, mol, lattice = _cif_to_xyz_mol(data)
        return xyz, mol, lattice

    elif input_format == "mol":
        mol = Chem.MolFromMolBlock(data)
        if mol is None:
            raise ValueError("Invalid MOL block")
        xyz = Chem.MolToXYZBlock(mol)
        return xyz, mol, None

    raise ValueError(f"Unsupported format: {input_format}")


def _xyz_to_mol(xyz_str: str) -> Chem.Mol:
    """Convert XYZ string to RDKit Mol. Supports standard (4-col) and extended (multi-col) formats."""
    lines = xyz_str.strip().split("\n")
    mol = Chem.RWMol()
    atoms_data = []

    for line in lines:
        parts = line.strip().split()
        if len(parts) >= 4:
            try:
                symbol = parts[0]
                if len(symbol) > 2 or not symbol[0].isalpha():
                    continue
                x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                atoms_data.append((symbol, x, y, z))
            except ValueError:
                continue

    for symbol, _, _, _ in atoms_data:
        atom = Chem.Atom(symbol)
        mol.AddAtom(atom)

    if mol.GetNumAtoms() == 0:
        raise ValueError("Could not parse any atoms from XYZ input")

    conf = Chem.Conformer(mol.GetNumAtoms())
    for i, (_, x, y, z) in enumerate(atoms_data):
        conf.SetAtomPosition(i, Point3D(x, y, z))

    mol.AddConformer(conf)
    result = mol.GetMol()
    try:
        Chem.SanitizeMol(result)
    except Exception:
        pass
    return result


def _cif_to_xyz_mol(cif_data: str) -> tuple[str, Chem.Mol, list[tuple[float, float, float]]]:
    """Parse CIF data to XYZ string, RDKit Mol, and lattice vectors using ASE."""
    from ase.io import read, write

    atoms = read(io.StringIO(cif_data), format="cif")

    buf = io.StringIO()
    write(buf, atoms, format="xyz")
    xyz_str = buf.getvalue()

    mol = _xyz_to_mol(xyz_str)
    cell = atoms.get_cell()
    lattice = [
        (float(cell[0][0]), float(cell[0][1]), float(cell[0][2])),
        (float(cell[1][0]), float(cell[1][1]), float(cell[1][2])),
        (float(cell[2][0]), float(cell[2][1]), float(cell[2][2])),
    ]
    return xyz_str, mol, lattice


def get_formula(mol: Chem.Mol) -> str:
    return _formula_from_elements(mol)


def _formula_from_elements(mol: Chem.Mol) -> str:
    """Compute formula by counting elements (fallback for inorganic/crystals)."""
    counts = Counter(atom.GetSymbol() for atom in mol.GetAtoms())
    result = []
    for el in ["C", "H"]:
        if el in counts:
            c = counts.pop(el)
            result.append(f"{el}{c if c > 1 else ''}")
    for el in sorted(counts):
        c = counts[el]
        result.append(f"{el}{c if c > 1 else ''}")
    return "".join(result)


def get_element_list(mol: Chem.Mol) -> list[str]:
    symbols = set()
    for atom in mol.GetAtoms():
        symbols.add(atom.GetSymbol())
    return sorted(symbols)


# ── Chemical formula parsing ───────────────────────────────────────────


def _parse_chemical_formula(formula: str) -> list[tuple[str, int]]:
    """Parse a chemical formula string into element/count pairs.

    Examples: 'H2O' → [('H',2), ('O',1)], 'Fe2O3' → [('Fe',2), ('O',3)]
    """
    tokens = re.findall(r"([A-Z][a-z]?)(\d*)", formula)
    if not tokens:
        raise ValueError(f"Unrecognized chemical formula: {formula}")
    result: list[tuple[str, int]] = []
    for symbol, count_str in tokens:
        count = int(count_str) if count_str else 1
        # Basic validation: element symbols are 1-2 chars, first uppercase
        if not re.match(r"^[A-Z][a-z]?$", symbol):
            raise ValueError(f"Invalid element symbol '{symbol}' in formula '{formula}'")
        result.append((symbol, count))
    return result


def _formula_to_xyz_mol(formula: str) -> tuple[str, Chem.Mol]:
    """Convert a chemical formula to XYZ + Mol by placing atoms in 3D.

    Since formulas lack bonding information, atoms are placed using distance
    geometry with random starting coordinates. The resulting geometry is a
    rough starting point — the user should follow with a VASP optimization.
    """
    pairs = _parse_chemical_formula(formula)
    total_atoms = sum(c for _, c in pairs)

    if total_atoms == 0:
        raise ValueError(f"No atoms found in formula '{formula}'")

    if total_atoms > 200:
        raise ValueError(f"Formula '{formula}' has {total_atoms} atoms — too many for auto-generation")

    # Build molecule with isolated atoms (no bonds)
    mol = Chem.RWMol()
    for symbol, count in pairs:
        for _ in range(count):
            mol.AddAtom(Chem.Atom(symbol))

    mol.UpdatePropertyCache(strict=False)

    # Single atom — place at origin
    if total_atoms == 1:
        mol = mol.GetMol()
        conf = Chem.Conformer(1)
        conf.SetAtomPosition(0, Point3D(0.0, 0.0, 0.0))
        mol.AddConformer(conf)
        return _mol_to_xyz_str(mol, formula), mol

    # Multi-atom: use distance geometry to scatter atoms in 3D space
    ps = AllChem.ETKDGv3()
    ps.randomSeed = 42
    ps.useRandomCoords = True
    ps.pruneRmsThresh = 0.1
    status = AllChem.EmbedMolecule(mol, ps)
    if status != 0:
        # Fallback: manual linear chain
        conf = Chem.Conformer(total_atoms)
        for i in range(total_atoms):
            conf.SetAtomPosition(i, Point3D(i * 1.5, 0.0, 0.0))
        mol = mol.GetMol()
        mol.AddConformer(conf)
    else:
        mol = mol.GetMol()

    try:
        AllChem.UFFOptimizeMolecule(mol, maxIters=100)
    except Exception:
        pass

    return _mol_to_xyz_str(mol, formula), mol


def _mol_to_xyz_str(mol: Chem.Mol, label: str = "") -> str:
    """Convert an RDKit Mol to XYZ string."""
    conf = mol.GetConformer()
    lines = [str(mol.GetNumAtoms()), label or "", ""]
    for atom in mol.GetAtoms():
        pos = conf.GetAtomPosition(atom.GetIdx())
        lines.append(f"{atom.GetSymbol():<2s}  {pos.x:10.6f}  {pos.y:10.6f}  {pos.z:10.6f}")
    return "\n".join(lines)


def get_element_list_from_xyz(xyz_str: str) -> list[str]:
    """Extract unique elements from XYZ string in order of first appearance.

    Order MUST match POSCAR species ordering — otherwise POTCAR concatenation
    will produce an element sequence that VASP rejects.
    """
    symbols: list[str] = []
    for line in xyz_str.strip().split("\n"):
        parts = line.strip().split()
        if len(parts) >= 4:
            symbol = parts[0]
            if len(symbol) <= 2 and symbol[0].isalpha() and symbol not in symbols:
                symbols.append(symbol)
    return symbols
