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


class FileContent(BaseModel):
    filename: str
    content: str


class CalculationResponse(BaseModel):
    calc_type: CalcType
    name: str
    files: list[FileContent]
    warnings: list[str] = []
    summary: str = ""
