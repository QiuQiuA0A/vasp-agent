"""User-friendly error messages for non-expert VASP users.

Each entry maps a technical error keyword to a human-readable message + suggestion.
The `translate()` function converts raw error strings into friendly responses.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class UserMessage:
    message: str
    suggestion: str


_PATTERNS: dict[str, UserMessage] = {
    # -- SMILES / structure input --
    'Invalid SMILES string': UserMessage(
        '输入的 SMILES 结构式无法识别',
        '请检查输入是否有拼写错误。示例: 水=O, 乙醇=CCO, 苯=c1ccccc1, 甲酸=O=CO'
    ),
    'Cannot interpret': UserMessage(
        '无法解析输入内容',
        '请确认输入格式与选择的格式一致'
    ),
    'Invalid MOL block': UserMessage(
        'MOL 格式文件内容有误',
        '请检查 MOL 文件的格式是否完整，尤其是 V2000 或 V3000 块'
    ),
    'Could not parse any atoms': UserMessage(
        '未能从输入中解析到任何原子坐标',
        'XYZ 格式每行需包含元素符号和 x y z 坐标。示例: O  0.0  0.0  0.0'
    ),
    'Unrecognized chemical formula': UserMessage(
        '无法识别的化学式',
        '请使用标准化学式写法。示例: H2O, NaCl, Fe2O3, C6H6。元素首字母需大写 (如 Fe 不是 fe)'
    ),
    'Invalid element symbol': UserMessage(
        '化学式中含有无效的元素符号',
        '元素符号首字母必须大写，第二个字母小写。例如: Fe 不是 FE, Na 不是 NA'
    ),
    'Unsupported format': UserMessage(
        '不支持的输入格式',
        '支持的格式: SMILES, 分子式, XYZ, CIF, MOL'
    ),
    'Failed to generate 3D conformation': UserMessage(
        '无法生成分子的3D结构',
        '该分子可能结构过于复杂或存在异常的键合方式。可尝试提供 XYZ 或 MOL 格式的预优化结构'
    ),
    'too many for auto-generation': UserMessage(
        '分子太大，无法自动生成3D结构',
        '超过200个原子的分子请使用 XYZ 或 CIF 格式直接提供坐标'
    ),

    # -- Calc type --
    'Band structure calculations require a periodic system': UserMessage(
        '能带结构计算需要周期性体系 (晶体)',
        '请使用 CIF 格式输入晶体结构，或从结构优化、态密度等其他计算类型中选择'
    ),
    'Unknown calc_type': UserMessage(
        '未知的计算类型',
        '请从网页下拉菜单中选择一个有效的计算类型'
    ),

    # -- Surface / slab --
    'Unknown metal': UserMessage(
        '不支持的金属元素',
        '当前支持的金属: Fe, Cr, Cu, Al, Ni, Zn, Mg, Ti。如有需要可联系管理员添加'
    ),
    'No slabs generated': UserMessage(
        '无法生成该晶面的 slab',
        '可能是晶面指数与晶格类型不匹配。BCC 支持 100/110/111, HCP 支持 0001/10-10'
    ),
    'Unknown lattice type': UserMessage(
        '内部错误: 未知的晶格类型',
        '请联系管理员检查金属注册表配置'
    ),

    # -- POTCAR --
    'Cannot detect element': UserMessage(
        '无法识别 POTCAR 文件中的元素',
        '请确认上传的是标准的 VASP POTCAR 文件'
    ),
    'No POTCAR found for element': UserMessage(
        'POTCAR 库中未找到该元素的势文件',
        '请先在 POTCAR 库管理页面导入对应元素的 POTCAR 文件'
    ),

    # -- Parser / file upload --
    'File too small': UserMessage(
        '上传的文件太小，可能不是有效的 VASP 输出文件',
        '请确认上传了正确类型的文件。OUTCAR 应至少有几百行内容'
    ),
    'Not a valid VASP vasprun.xml': UserMessage(
        '不是有效的 VASP vasprun.xml 文件',
        '请确认上传的是 VASP 计算生成的 vasprun.xml 文件'
    ),
    'Not a valid POTCAR': UserMessage(
        '不是有效的 VASP POTCAR 文件',
        'POTCAR 文件应以元素符号和 PAW 信息开头'
    ),
}


def translate(error: str) -> UserMessage:
    """Convert a technical error string into a user-friendly message."""
    for keyword, msg in _PATTERNS.items():
        if keyword.lower() in error.lower():
            return msg
    return UserMessage(
        message=error,
        suggestion='如果此问题持续出现，请检查输入参数后重试，或联系管理员'
    )
