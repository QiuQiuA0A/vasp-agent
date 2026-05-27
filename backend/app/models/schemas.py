from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class CalcType(str, Enum):
    OPTIMIZATION = "optimization"
    HOMO_LUMO = "homo_lumo"
    DIPOLE = "dipole"
    AIMD = "aimd"


class InputFormat(str, Enum):
    SMILES = "smiles"
    FORMULA = "formula"
    XYZ = "xyz"
    CIF = "cif"
    MOL = "mol"


class StructureSource(BaseModel):
    format: InputFormat
    data: str = Field(min_length=1, max_length=100000, description="SMILES string, molecular formula, or file content")


class VASPRequest(BaseModel):
    calc_type: CalcType
    structure: StructureSource
    charge: int = Field(default=0, ge=-5, le=5)
    multiplicity: int = Field(default=1, ge=1, le=10)
    name: str = Field(default="molecule", max_length=100)

    # Optional overrides
    encut: Optional[int] = Field(default=None, ge=100, le=1500)
    nsw: Optional[int] = Field(default=None, ge=0, le=50000)
    temperature: Optional[float] = Field(default=None, ge=0, le=5000)
    functional: str = Field(default="PBE", max_length=10, description="XC functional: PBE, LDA, PW91")


class FileContent(BaseModel):
    filename: str
    content: str


class CalculationResponse(BaseModel):
    calc_type: CalcType
    name: str
    files: list[FileContent]
    warnings: list[str] = []
    summary: str = ""


class SurfaceRequest(BaseModel):
    """Request to build a metal slab with optional adsorbed molecule."""
    metal: str = Field(min_length=1, max_length=3, description="Element symbol, e.g. Fe")
    surface: str = Field(min_length=1, max_length=10, description="Miller index, e.g. 110")
    layers: int = Field(default=4, ge=1, le=20)
    vacuum: float = Field(default=15.0, ge=5.0, le=50.0)
    fix_bottom: int = Field(default=2, ge=0, le=10)
    # Molecule (Method B — user-provided positioned XYZ)
    xyz: str | None = Field(default=None, max_length=100000, description="XYZ with molecule pre-positioned above surface")


class SurfaceResponse(BaseModel):
    """Result of building a slab."""
    metal: str
    surface: str
    n_slab_atoms: int
    n_molecule_atoms: int
    n_total: int
    poscar: str
    elements: list[str]
    counts: list[int]
    summary: str = ""


class SurfaceGenerateRequest(BaseModel):
    """Request to generate full VASP input set for a surface calculation."""
    metal: str = Field(min_length=1, max_length=3)
    surface: str = Field(min_length=1, max_length=10)
    layers: int = Field(default=4, ge=1, le=20)
    vacuum: float = Field(default=15.0, ge=5.0, le=50.0)
    fix_bottom: int = Field(default=2, ge=0, le=10)
    xyz: str | None = Field(default=None, max_length=100000)
    name: str = Field(default="slab", max_length=100)
    functional: str = Field(default="PBE", max_length=10, description="XC functional: PBE, LDA, PW91")
