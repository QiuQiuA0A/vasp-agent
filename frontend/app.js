let currentFiles = [];
let currentTab = 0;
let lastPayload = null;

document.getElementById("calcType").addEventListener("change", function () {
  const isAIMD = this.value === "aimd";
  document.getElementById("tempGroup").style.display = isAIMD ? "" : "none";
  document.getElementById("nswGroup").style.display = isAIMD ? "none" : "";
});

document.getElementById("generateBtn").addEventListener("click", generateFiles);
document.getElementById("downloadZipBtn").addEventListener("click", downloadZip);
document.getElementById("copyBtn").addEventListener("click", copyCurrent);

async function generateFiles() {
  const btn = document.getElementById("generateBtn");
  btn.disabled = true;
  btn.textContent = "生成中...";
  hideMessages();

  const payload = buildPayload();
  lastPayload = payload;

  try {
    const resp = await fetch("/api/v1/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!resp.ok) {
      const err = await resp.json();
      showError(err.detail || "请求失败");
      return;
    }

    const data = await resp.json();
    displayResult(data);
  } catch (e) {
    showError("网络错误: " + e.message + "。后端是否在运行？");
  } finally {
    btn.disabled = false;
    btn.textContent = "生成 VASP 输入文件";
  }
}

function buildPayload() {
  const payload = {
    calc_type: document.getElementById("calcType").value,
    structure: {
      format: document.getElementById("inputFormat").value,
      data: document.getElementById("structureData").value.trim(),
    },
    charge: parseInt(document.getElementById("charge").value) || 0,
    multiplicity: parseInt(document.getElementById("multiplicity").value) || 1,
    name: document.getElementById("name").value || "molecule",
  };

  const encutVal = parseInt(document.getElementById("encut").value);
  if (encutVal) payload.encut = encutVal;

  const nswVal = parseInt(document.getElementById("nsw").value);
  if (nswVal) payload.nsw = nswVal;

  const tempVal = parseFloat(document.getElementById("temperature").value);
  if (tempVal) payload.temperature = tempVal;

  payload.functional = document.getElementById("functional").value || "PBE";

  return payload;
}

function displayResult(data) {
  document.getElementById("resultSection").style.display = "";
  document.getElementById("summaryBox").textContent = data.summary;

  if (data.warnings && data.warnings.length) {
    const ws = document.getElementById("warningSection");
    ws.style.display = "";
    ws.innerHTML = data.warnings.map(function (w) { return "<p>" + w + "</p>"; }).join("");
  }

  currentFiles = data.files;

  const tabsDiv = document.getElementById("fileTabs");
  tabsDiv.innerHTML = "";

  data.files.forEach(function (f, i) {
    const btn = document.createElement("button");
    btn.className = "tab-btn";
    btn.textContent = f.filename;
    btn.onclick = function () { showFile(i); };
    tabsDiv.appendChild(btn);
  });

  if (data.files.length > 0) showFile(0);

  // Show 3D structure viewer from POSCAR
  var poscarFile = data.files.find(function (f) { return f.filename.indexOf("POSCAR") !== -1; });
  if (poscarFile) showStructure(poscarFile.content);
}

function showStructure(poscarContent) {
  var viewerDiv = document.getElementById("structureViewer");
  viewerDiv.style.display = "";
  var viewerEl = document.getElementById("molViewer");

  // Parse POSCAR: extract lattice + atom positions
  var lines = poscarContent.split("\n").filter(function (l) { return l.trim() !== ""; });
  if (lines.length < 8) return;

  // Line 0: comment, Line 1: scale, Lines 2-4: lattice, Lines 5-6: elements + counts
  var scale = parseFloat(lines[1]) || 1.0;
  var latLines = lines.slice(2, 5).map(function (l) { return l.trim().split(/\s+/).map(Number); });
  var species = lines[5].trim().split(/\s+/);
  var counts = lines[6].trim().split(/\s+/).map(Number);
  var totalAtoms = counts.reduce(function (a, b) { return a + b; }, 0);

  // Find 'Cartesian' or 'Direct' marker
  var coordStart = 7;
  for (var k = 7; k < Math.min(lines.length, 12); k++) {
    if (lines[k].match(/^[Cc]artesian|^[Dd]irect|^Selective/i)) { coordStart = k + 1; break; }
  }

  // Build XYZ string for 3Dmol
  var xyz = totalAtoms + "\nstructure\n";
  var elList = [];
  species.forEach(function (s, i) { for (var j = 0; j < counts[i]; j++) elList.push(s); });

  for (var i = 0; i < totalAtoms && (coordStart + i) < lines.length; i++) {
    var parts = lines[coordStart + i].trim().split(/\s+/);
    var el = elList[i] || "X";
    var x = parseFloat(parts[0]) || 0;
    var y = parseFloat(parts[1]) || 0;
    var z = parseFloat(parts[2]) || 0;
    xyz += el + " " + x.toFixed(6) + " " + y.toFixed(6) + " " + z.toFixed(6) + "\n";
  }

  viewerEl.innerHTML = "";
  var viewer = $3Dmol.createViewer(viewerEl, { defaultcolors: $3Dmol.elementColors.Jmol });
  viewer.addModel(xyz, "xyz");
  viewer.setStyle({}, { stick: { radius: 0.15 }, sphere: { scale: 0.3 } });
  viewer.zoomTo();
  viewer.render();
}

function showFile(index) {
  currentTab = index;
  document.getElementById("fileContent").textContent = currentFiles[index].content;

  var btns = document.querySelectorAll(".tab-btn");
  btns.forEach(function (btn, i) {
    if (i === index) {
      btn.classList.add("active");
    } else {
      btn.classList.remove("active");
    }
  });
}

function copyCurrent() {
  if (!currentFiles.length) return;
  const content = currentFiles[currentTab].content;
  navigator.clipboard.writeText(content).then(function () {
    const btn = document.getElementById("copyBtn");
    const orig = btn.textContent;
    btn.textContent = "已复制!";
    setTimeout(function () { btn.textContent = orig; }, 1500);
  });
}

async function downloadZip() {
  if (!lastPayload) return;

  const btn = document.getElementById("downloadZipBtn");
  btn.disabled = true;
  btn.textContent = "下载中...";

  try {
    const resp = await fetch("/api/v1/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(lastPayload),
    });

    if (!resp.ok) {
      const err = await resp.json();
      showError(err.detail || "下载失败");
      return;
    }

    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = (lastPayload.name || "vasp") + "_inputs.zip";
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    showError("下载失败: " + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "下载全部文件 (.zip)";
  }
}

function showError(msg) {
  const el = document.getElementById("errorSection");
  el.style.display = "";
  el.innerHTML = "<p>" + msg + "</p>";
}

function hideMessages() {
  document.getElementById("resultSection").style.display = "none";
  document.getElementById("warningSection").style.display = "none";
  document.getElementById("errorSection").style.display = "none";
  currentFiles = [];
  currentTab = 0;
}

// -- Result Analysis --

document.getElementById("analyzeOutcarBtn").addEventListener("click", async function () {
  const fileInput = document.getElementById("outcarFile");
  const file = fileInput.files[0];
  if (!file) { showError("请先选择 OUTCAR 文件"); return; }
  await analyzeFile("/api/v1/analyze/outcar", file);
});

document.getElementById("analyzeEigenBtn").addEventListener("click", async function () {
  const fileInput = document.getElementById("eigenvalFile");
  const file = fileInput.files[0];
  if (!file) { showError("请先选择 EIGENVAL 文件"); return; }
  await analyzeFile("/api/v1/analyze/eigenval", file);
});

document.getElementById("analyzeOszicarBtn").addEventListener("click", async function () {
  const fileInput = document.getElementById("oszicarFile");
  const file = fileInput.files[0];
  if (!file) { showError("请先选择 OSZICAR 文件"); return; }
  await analyzeFile("/api/v1/analyze/oszicar", file);
});

document.getElementById("analyzeVasprunBtn").addEventListener("click", async function () {
  const fileInput = document.getElementById("vasprunFile");
  const file = fileInput.files[0];
  if (!file) { showError("请先选择 vasprun.xml 文件"); return; }
  await analyzeFile("/api/v1/analyze/vasprun", file);
});

document.getElementById("analyzeXdatcarBtn").addEventListener("click", async function () {
  const fileInput = document.getElementById("xdatcarFile");
  const file = fileInput.files[0];
  if (!file) { showError("请先选择 XDATCAR 文件"); return; }
  await analyzeFile("/api/v1/analyze/xdatcar", file);
});

document.getElementById("analyzeContcarBtn").addEventListener("click", async function () {
  const fileInput = document.getElementById("contcarFile");
  const file = fileInput.files[0];
  if (!file) { showError("请先选择 CONTCAR 文件"); return; }
  await analyzeFile("/api/v1/analyze/contcar", file);
});

async function analyzeFile(url, file) {
  const formData = new FormData();
  formData.append("file", file);

  try {
    const resp = await fetch(url, { method: "POST", body: formData });
    if (!resp.ok) {
      const err = await resp.json();
      showError(err.detail || "解析失败");
      return;
    }
    const data = await resp.json();
    displayAnalysis(data);
  } catch (e) {
    showError("网络错误: " + e.message);
  }
}

// -- POTCAR Library Management --

async function loadPotcarStatus(functional) {
  functional = functional || "PBE";
  try {
    const resp = await fetch("/api/v1/potcar/status?functional=" + encodeURIComponent(functional));
    const data = await resp.json();
    renderPotcarGrid(data);
    document.getElementById("potcarFunctional").value = functional;
  } catch (e) {
    document.getElementById("potcarSummary").textContent = "无法加载 POTCAR 库状态";
  }
}

function renderPotcarGrid(data) {
  var summary = document.getElementById("potcarSummary");
  var pct = data.total_elements > 0 ? Math.round(data.available / data.total_elements * 100) : 0;
  summary.innerHTML = "已安装 <strong>" + data.available + "</strong> / " + data.total_elements + " 种元素 (" + pct + "%)";

  var grid = document.getElementById("potcarGrid");
  var html = "";

  // Group by period for a periodic-table-like layout
  var periods = [
    ["H", "He"],
    ["Li", "Be", "B", "C", "N", "O", "F", "Ne"],
    ["Na", "Mg", "Al", "Si", "P", "S", "Cl", "Ar"],
    ["K", "Ca", "Sc", "Ti", "V", "Cr", "Mn", "Fe", "Co", "Ni", "Cu", "Zn", "Ga", "Ge", "As", "Se", "Br", "Kr"],
    ["Rb", "Sr", "Y", "Zr", "Nb", "Mo", "Tc", "Ru", "Rh", "Pd", "Ag", "Cd", "In", "Sn", "Sb", "Te", "I", "Xe"],
    ["Cs", "Ba", "La", "Ce", "Pr", "Nd", "Pm", "Sm", "Eu", "Gd", "Tb", "Dy", "Ho", "Er", "Tm", "Yb", "Lu", "Hf", "Ta", "W", "Re", "Os", "Ir", "Pt", "Au", "Hg", "Tl", "Pb", "Bi"],
    ["Po", "At", "Rn", "Fr", "Ra", "Ac", "Th", "Pa", "U", "Np", "Pu"],
  ];

  periods.forEach(function (row) {
    html += '<div class="potcar-period">';
    row.forEach(function (el) {
      var available = data.elements && data.elements[el];
      var cls = available ? "potcar-el available" : "potcar-el missing";
      html += '<span class="' + cls + '" title="' + el + (available ? ' — 已安装' : ' — 未安装') + '">' + el + '</span>';
    });
    html += '</div>';
  });

  grid.innerHTML = html;
}

document.getElementById("importPotcarBtn").addEventListener("click", async function () {
  var fileInput = document.getElementById("potcarFile");
  var files = fileInput.files;
  if (!files.length) { showError("请先选择 POTCAR 文件"); return; }

  var btn = document.getElementById("importPotcarBtn");
  btn.disabled = true;
  btn.textContent = "导入中...";

  var formData = new FormData();
  for (var i = 0; i < files.length; i++) {
    formData.append("files", files[i]);
  }

  try {
    var url = files.length === 1 ? "/api/v1/potcar/import" : "/api/v1/potcar/import-multi";
    var resp = await fetch(url, { method: "POST", body: formData });
    if (!resp.ok) {
      var err = await resp.json();
      showError(err.detail || "导入失败");
      return;
    }
    hideMessages();
    loadPotcarStatus();
  } catch (e) {
    showError("导入失败: " + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "导入";
    fileInput.value = "";
  }
});

// -- Surface Slab Building --

var surfaceMap = {
  bcc: ["110", "100", "111"],
  fcc: ["110", "100", "111"],
  hcp: ["0001", "10-10"],
};
var metalTypeMap = {
  Fe: "bcc", Cr: "bcc",
  Cu: "fcc", Al: "fcc", Ni: "fcc",
  Zn: "hcp", Mg: "hcp", Ti: "hcp",
};

document.getElementById("surfaceMetal").addEventListener("change", function () {
  var metal = this.value;
  var type = metalTypeMap[metal] || "bcc";
  var surfaces = surfaceMap[type] || ["110", "100", "111"];
  var select = document.getElementById("surfaceIndex");
  select.innerHTML = "";
  surfaces.forEach(function (s, i) {
    var opt = document.createElement("option");
    opt.value = s;
    opt.textContent = metal + "(" + s + ")";
    if (i === 0) opt.selected = true;
    select.appendChild(opt);
  });
});

document.getElementById("buildSlabBtn").addEventListener("click", buildSlab);
document.getElementById("generateSlabBtn").addEventListener("click", generateSlab);

async function buildSlab() {
  var btn = document.getElementById("buildSlabBtn");
  btn.disabled = true;
  btn.textContent = "构建中...";

  var xyzText = document.getElementById("surfaceXyz").value.trim();
  var payload = {
    metal: document.getElementById("surfaceMetal").value,
    surface: document.getElementById("surfaceIndex").value,
    layers: parseInt(document.getElementById("surfaceLayers").value) || 4,
    vacuum: parseFloat(document.getElementById("surfaceVacuum").value) || 15.0,
    fix_bottom: parseInt(document.getElementById("surfaceFixBottom").value) || 2,
  };
  if (xyzText) payload.xyz = xyzText;

  try {
    var resp = await fetch("/api/v1/surface/build", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!resp.ok) {
      var err = await resp.json();
      showError(err.detail || "Slab 构建失败");
      return;
    }

    var data = await resp.json();
    document.getElementById("slabResultSection").style.display = "";
    document.getElementById("slabSummaryBox").textContent = data.summary;
    document.getElementById("slabPoscarContent").textContent = data.poscar;
  } catch (e) {
    showError("网络错误: " + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "构建 Slab + 生成 POSCAR";
  }
}

async function generateSlab() {
  var btn = document.getElementById("generateSlabBtn");
  btn.disabled = true;
  btn.textContent = "生成中...";

  var xyzText = document.getElementById("surfaceXyz").value.trim();
  var payload = {
    metal: document.getElementById("surfaceMetal").value,
    surface: document.getElementById("surfaceIndex").value,
    layers: parseInt(document.getElementById("surfaceLayers").value) || 4,
    vacuum: parseFloat(document.getElementById("surfaceVacuum").value) || 15.0,
    fix_bottom: parseInt(document.getElementById("surfaceFixBottom").value) || 2,
    name: document.getElementById("name").value || "slab",
  };
  if (xyzText) payload.xyz = xyzText;
  payload.functional = document.getElementById("functional").value || "PBE";

  try {
    var resp = await fetch("/api/v1/surface/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!resp.ok) {
      var err = await resp.json();
      showError(err.detail || "生成失败");
      return;
    }

    var data = await resp.json();
    displaySlabResult(data);
  } catch (e) {
    showError("网络错误: " + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "生成完整 VASP 输入文件";
  }
}

function displaySlabResult(data) {
  document.getElementById("slabResultSection").style.display = "";
  document.getElementById("slabSummaryBox").textContent = data.summary || "";

  var files = data.files || [];
  var tabsDiv = document.getElementById("slabFileTabs");
  tabsDiv.innerHTML = "";

  files.forEach(function (f, i) {
    var btn = document.createElement("button");
    btn.className = "tab-btn";
    btn.textContent = f.filename;
    btn.onclick = function () { showSlabFile(i, files); };
    tabsDiv.appendChild(btn);
  });

  if (files.length > 0) showSlabFile(0, files);
}

var slabFiles = [];
function showSlabFile(index, files) {
  slabFiles = files;
  document.getElementById("slabPoscarContent").textContent = files[index].content;

  var btns = document.querySelectorAll("#slabFileTabs .tab-btn");
  btns.forEach(function (btn, i) {
    if (i === index) {
      btn.classList.add("active");
    } else {
      btn.classList.remove("active");
    }
  });
}

// Update copy button to work with slab files
document.getElementById("copySlabBtn").addEventListener("click", function () {
  var content = document.getElementById("slabPoscarContent").textContent;
  if (!content) return;
  navigator.clipboard.writeText(content).then(function () {
    var btn = document.getElementById("copySlabBtn");
    var orig = btn.textContent;
    btn.textContent = "已复制!";
    setTimeout(function () { btn.textContent = orig; }, 1500);
  });
});

// Load POTCAR status on page load
loadPotcarStatus();

function displayAnalysis(data) {
  var container = document.getElementById("analysisResult");
  container.style.display = "";

  var rows = [];
  var statusClass = "";

  if (data.converged !== undefined) {
    // OUTCAR result
    statusClass = data.converged ? "status-ok" : "status-fail";
    rows.push(["收敛状态", "<span class='" + statusClass + "'>" + (data.converged ? "已收敛" : "未收敛") + "</span>"]);
    if (data.total_energy_ev != null) {
      rows.push(["总能量", data.total_energy_ev.toFixed(6) + " eV"]);
    }
    if (data.fermi_energy_ev != null) {
      rows.push(["费米能级", data.fermi_energy_ev.toFixed(4) + " eV"]);
    }
    if (data.homo_ev != null) {
      rows.push(["HOMO", data.homo_ev.toFixed(4) + " eV"]);
    }
    if (data.lumo_ev != null) {
      rows.push(["LUMO", data.lumo_ev.toFixed(4) + " eV"]);
    }
    if (data.gap_ev != null) {
      rows.push(["HOMO-LUMO Gap", data.gap_ev.toFixed(4) + " eV"]);
    }
    if (data.max_force_ev_a != null) {
      rows.push(["最大残余力", data.max_force_ev_a.toFixed(6) + " eV/A"]);
    }
    if (data.dipole_total_e_ang != null) {
      rows.push(["偶极矩大小", data.dipole_total_e_ang.toFixed(4) + " e*A"]);
    }
    if (data.dipole_moment_e_ang) {
      var d = data.dipole_moment_e_ang;
      rows.push(["偶极矩 (x,y,z)", d[0].toFixed(4) + ", " + d[1].toFixed(4) + ", " + d[2].toFixed(4)]);
    }
    rows.push(["SCF 步数", data.n_scf_steps || 0]);
    rows.push(["离子步数", data.n_ionic_steps || 0]);
    if (data.warnings && data.warnings.length) {
      rows.push(["警告", data.warnings.join("; ")]);
    }
  }

  if (data.nbands !== undefined) {
    // EIGENVAL result
    rows.push(["能带数", data.nbands]);
    rows.push(["K 点数", data.nkpoints]);
    rows.push(["电子数", data.n_electrons]);
    if (data.homo_energy != null) {
      rows.push(["HOMO", data.homo_energy.toFixed(4) + " eV"]);
    }
    if (data.lumo_energy != null) {
      rows.push(["LUMO", data.lumo_energy.toFixed(4) + " eV"]);
    }
    if (data.gap != null) {
      rows.push(["带隙", data.gap.toFixed(4) + " eV"]);
    }
  }

  if (data.status && data.diagnostics) {
    // OSZICAR result
    var statusLabels = { ok: "正常", warning: "警告", error: "异常" };
    var statusClasses = { ok: "status-ok", warning: "status-warn", error: "status-fail" };
    var sc = statusClasses[data.status] || "";
    rows.push(["诊断结论", "<span class='" + sc + "'>" + (statusLabels[data.status] || data.status) + "</span>"]);
    rows.push(["离子步总数", data.total_ionic_steps]);
    rows.push(["SCF 总步数", data.total_scf_steps]);
    if (data.final_energy_ev != null) {
      rows.push(["最终能量", data.final_energy_ev.toFixed(6) + " eV"]);
    }
    if (data.diagnostics && data.diagnostics.length) {
      rows.push(["诊断详情", data.diagnostics.join("<br>")]);
    }
  }

  if (data.n_frames !== undefined && data.n_atoms !== undefined) {
    // XDATCAR result
    rows.push(["体系", data.formula]);
    rows.push(["原子数", data.n_atoms]);
    rows.push(["帧数", data.n_frames]);
    if (data.elements && data.elements.length) rows.push(["元素", data.elements.join(", ")]);
    if (data.lattice) rows.push(["晶格", "3×" + "3"]);
  }

  if (data.coordinate_type !== undefined) {
    // CONTCAR result
    rows.push(["体系", data.formula]);
    if (data.lattice) rows.push(["晶格", "3×" + "3"]);
    rows.push(["原子数", data.n_atoms]);
    if (data.elements && data.elements.length) rows.push(["元素", data.elements.join(", ")]);
    if (data.counts && data.counts.length) rows.push(["数量", data.counts.join(", ")]);
    rows.push(["坐标类型", data.coordinate_type]);
    if (data.selective) rows.push(["选择性动力学", "已启用"]);
    if (data.xyz) rows.push(["XYZ 导出", data.total_atoms + " 个原子 (可复制下方内容)"]);
  }

  if (data.system !== undefined) {
    // vasprun.xml result
    rows.push(["体系名称", data.system]);
    rows.push(["离子步数", data.n_ionic_steps]);
    if (data.homo_ev != null) rows.push(["HOMO", data.homo_ev.toFixed(4) + " eV"]);
    if (data.lumo_ev != null) rows.push(["LUMO", data.lumo_ev.toFixed(4) + " eV"]);
    if (data.gap_ev != null) rows.push(["带隙", data.gap_ev.toFixed(4) + " eV"]);
    if (data.fermi_from_dos_ev != null) rows.push(["费米能级 (DOS)", data.fermi_from_dos_ev.toFixed(4) + " eV"]);
    rows.push(["本征值数", data.n_eigenvalues || 0]);
    rows.push(["TDOS 数据点", data.n_dos_points || 0]);
    if (data.n_pdos_points) rows.push(["PDOS 数据点", data.n_pdos_points]);
    if (data.final_lattice) rows.push(["晶格维度", data.final_lattice.length + "x3"]);
    if (data.warnings && data.warnings.length) rows.push(["警告", data.warnings.join("; ")]);
  }

  if (rows.length === 0) {
    container.innerHTML = "<p>无法解析此文件。</p>";
    return;
  }

  var html = "<table>";
  rows.forEach(function (r) {
    html += "<tr><td>" + r[0] + "</td><td>" + r[1] + "</td></tr>";
  });
  html += "</table>";
  document.getElementById("analysisSummary").innerHTML = html;
}
