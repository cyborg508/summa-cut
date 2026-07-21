"use strict";
const $ = (id) => document.getElementById(id);
const uploads = {};          // name -> page_count
const uploadsInfo = {};      // name -> pełny obiekt z /api/upload (page_sizes_mm, ...)
let montage = [];            // [{label,print_upload,print_page,cut_upload,cut_page,quantity}]
let previewTimer = null;
let previewWhich = "print";  // który obraz pokazuje podgląd: "print" | "cut"
let rightView = "preview";   // co pokazuje prawy panel: "editor" | "preview"
// stan trybu specjalnego: po „Przygotuj" trzyma przycięte uploady i rozmiar kafla
const special = { printUpload: null, cutUpload: null, pageW: 0, pageH: 0, ready: false };
const manualState = { enabled: false, items: [], placements: [], selected: null };
// items: [{ upload }]   placements: [{ itemIndex, xMm, yMm, rot, wMm, hMm }]

// --- Edytor 3×3 trybu specjalnego -------------------------------------------
let selectedTile = [1, 1];     // [row, col] aktywnego kafla (domyślnie środek)
let tileImgUrl = null;          // URL obrazka pojedynczego kafla (po prepare)
let editorDrag = null;          // {row, col, startX, startY, off, pxPerMmX, pxPerMmY} podczas drag

// rząd/kol 0 i 2 mapują się na bazę 0 (zewnętrzne), 1 na bazę 1 (środkowa) — jak desktop
function baseRow(row) { return (row === 0 || row === 2) ? 0 : 1; }
function baseCol(col) { return (col === 0 || col === 2) ? 0 : 1; }

// off = {row:[a,b], col:[a,b], colx:[a,b], rowy:[a,b]} w mm. Port _preview_tile_origin_pt.
function tileOrigin(row, col, off, pageW, pageH) {
  const firstX = off.row[baseRow(row)] + off.colx[0];
  const secondX = pageW + off.row[baseRow(row)] + off.colx[1];
  const x = col === 0 ? firstX : (col === 1 ? secondX : secondX + (secondX - firstX));
  const firstY = off.col[baseCol(col)] + off.rowy[0];
  const secondY = pageH + off.col[baseCol(col)] + off.rowy[1];
  const y = row === 0 ? firstY : (row === 1 ? secondY : secondY + (secondY - firstY));
  return { x, y };
}

// Przeciąganie kafla (row,col) o (dxMm,dyMm). Bez Shift: przesuw rzędu/kolumny;
// z Shift: odstęp kolumn/rzędów. Mutuje i zwraca off. Port mouseMoveEvent z desktopu.
function applyDrag(off, shift, row, col, dxMm, dyMm) {
  const br = baseRow(row), bc = baseCol(col);
  if (shift) { off.colx[bc] += dxMm; off.rowy[br] += dyMm; }
  else { off.row[br] += dxMm; off.col[bc] += dyMm; }
  return off;
}
// eksport do testów (Playwright page.evaluate)
window.tileOrigin = tileOrigin;
window.applyDrag = applyDrag;
window.baseRow = baseRow;
window.baseCol = baseCol;

function readOffsets() {
  const v = (id) => parseFloat($(id).value) || 0;
  return {
    row: [v("special-row0"), v("special-row1")],
    col: [v("special-col0"), v("special-col1")],
    colx: [v("special-colx0"), v("special-colx1")],
    rowy: [v("special-rowy0"), v("special-rowy1")],
  };
}
function writeOffsets(off) {
  const r = (n) => Math.round(n * 1000) / 1000;
  $("special-row0").value = r(off.row[0]);  $("special-row1").value = r(off.row[1]);
  $("special-col0").value = r(off.col[0]);  $("special-col1").value = r(off.col[1]);
  $("special-colx0").value = r(off.colx[0]); $("special-colx1").value = r(off.colx[1]);
  $("special-rowy0").value = r(off.rowy[0]); $("special-rowy1").value = r(off.rowy[1]);
}

function renderSpecialEditor() {
  const svg = $("special-editor");
  if (!svg) return;
  if (!(special.ready && tileImgUrl)) { svg.innerHTML = ""; return; }
  const off = readOffsets();
  const pw = special.pageW, ph = special.pageH;
  const tiles = [];
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (let row = 0; row < 3; row++) {
    for (let col = 0; col < 3; col++) {
      const o = tileOrigin(row, col, off, pw, ph);
      tiles.push({ row, col, x: o.x, y: o.y });
      minX = Math.min(minX, o.x); minY = Math.min(minY, o.y);
      maxX = Math.max(maxX, o.x + pw); maxY = Math.max(maxY, o.y + ph);
    }
  }
  const W = 300, H = 260, M = 18;
  const bw = Math.max(maxX - minX, 1), bh = Math.max(maxY - minY, 1);
  const scale = Math.min((W - 2 * M) / bw, (H - 2 * M) / bh);
  const ox = (W - bw * scale) / 2 - minX * scale;
  const oy = (H - bh * scale) / 2 - minY * scale;
  svg.dataset.scale = scale;   // px-na-mm dla draga
  const parts = [];
  for (const t of tiles) {
    const x = ox + t.x * scale, y = oy + t.y * scale, w = pw * scale, h = ph * scale;
    const isCenter = (t.row === 1 && t.col === 1);
    const isSel = (t.row === selectedTile[0] && t.col === selectedTile[1]);
    const op = isCenter ? 1 : 0.4;
    parts.push(`<image href="${tileImgUrl}" x="${x}" y="${y}" width="${w}" height="${h}" opacity="${op}" preserveAspectRatio="none"/>`);
    const stroke = isSel ? "#111" : (isCenter ? "#2f80ed" : "#bbb");
    const sw = isSel ? 2 : 1;
    const dash = isSel ? ' stroke-dasharray="4 3"' : "";
    parts.push(`<rect class="tile" data-row="${t.row}" data-col="${t.col}" x="${x}" y="${y}" width="${w}" height="${h}" fill="transparent" stroke="${stroke}" stroke-width="${sw}"${dash}/>`);
  }
  svg.innerHTML = parts.join("");
}

function editorPointerDown(e) {
  const target = e.target.closest(".tile");
  if (!target) return;
  const row = parseInt(target.dataset.row, 10), col = parseInt(target.dataset.col, 10);
  selectedTile = [row, col];
  const svg = $("special-editor");
  const scale = parseFloat(svg.dataset.scale) || 1;   // viewBox-units per mm
  const rect = svg.getBoundingClientRect();
  const vb = svg.viewBox.baseVal;                       // {width:300, height:260}
  // CSS px per mm, osobno dla X i Y (viewBox NIE jest pokazany z zachowaniem proporcji)
  const pxPerMmX = (scale * rect.width / (vb.width || 1)) || scale;
  const pxPerMmY = (scale * rect.height / (vb.height || 1)) || scale;
  editorDrag = { row, col, startX: e.clientX, startY: e.clientY, off: readOffsets(), pxPerMmX, pxPerMmY };
  try { svg.setPointerCapture(e.pointerId); } catch (_) {}
  renderSpecialEditor();
}
function editorPointerMove(e) {
  if (!editorDrag) return;
  const dxMm = (e.clientX - editorDrag.startX) / editorDrag.pxPerMmX;
  const dyMm = (e.clientY - editorDrag.startY) / editorDrag.pxPerMmY;
  const off = JSON.parse(JSON.stringify(editorDrag.off));  // od świeżego snapshotu, bez kumulacji
  applyDrag(off, e.shiftKey, editorDrag.row, editorDrag.col, dxMm, dyMm);
  writeOffsets(off);
  renderSpecialEditor();
}
function editorPointerUp() {
  if (!editorDrag) return;
  editorDrag = null;
  schedulePreview();
}
function editorKey(e) {
  if (!special.ready) return;
  const step = 0.1;
  let dx = 0, dy = 0;
  if (e.key === "ArrowLeft") dx = -step;
  else if (e.key === "ArrowRight") dx = step;
  else if (e.key === "ArrowUp") dy = -step;
  else if (e.key === "ArrowDown") dy = step;
  else return;
  e.preventDefault();
  const off = readOffsets();
  applyDrag(off, e.shiftKey, selectedTile[0], selectedTile[1], dx, dy);
  writeOffsets(off);
  renderSpecialEditor();
  schedulePreview();
}

function specialOffsets() {
  const v = (id) => parseFloat($(id).value) || 0;
  return {
    special_row_offsets_mm: [v("special-row0"), v("special-row1")],
    special_col_offsets_mm: [v("special-col0"), v("special-col1")],
    special_col_x_offsets_mm: [v("special-colx0"), v("special-colx1")],
    special_row_y_offsets_mm: [v("special-rowy0"), v("special-rowy1")],
  };
}

async function init() {
  await fetch("/api/session", { method: "POST" });
  wireEvents();
}

function wireEvents() {
  $("upload-btn").addEventListener("click", doUpload);
  $("generate-btn").addEventListener("click", doGenerate);
  $("preview-print-btn").addEventListener("click", () => setPreviewWhich("print"));
  $("preview-cut-btn").addEventListener("click", () => setPreviewWhich("cut"));
  $("view-editor-btn").addEventListener("click", () => setRightView("editor"));
  $("view-preview-btn").addEventListener("click", () => setRightView("preview"));
  for (const id of ["special-row0","special-row1","special-col0","special-col1",
                    "special-colx0","special-colx1","special-rowy0","special-rowy1"]) {
    $(id).addEventListener("input", () => { renderSpecialEditor(); schedulePreview(); });
  }
  $("montage-add").addEventListener("click", () => { addMontageRow(); schedulePreview(); });
  $("montage-enable").addEventListener("change", onMontageToggle);
  $("special-enable").addEventListener("change", onSpecialToggle);
  $("special-prepare-btn").addEventListener("click", doSpecialPrepare);
  $("manual-free").addEventListener("change", onManualToggle);
  document.addEventListener("keydown", mcKey);
  // każda zmiana kontrolki → przeliczenie podglądu (debounce)
  $("controls").addEventListener("input", schedulePreview);
  $("controls").addEventListener("change", schedulePreview);
  // zmiana pliku → odśwież listę stron
  $("print-file").addEventListener("change", () => fillPages("print-file", "print-page"));
  $("cut-file").addEventListener("change", () => fillPages("cut-file", "cut-page"));
  // Zmiana źródła/strony druku lub wykrojnika albo spadu unieważnia przygotowany
  // wykrojnik trybu specjalnego (przycięcie przestaje pasować). Robimy to PRZED
  // (debounce'owanym) podglądem przez #controls, więc kolejny podgląd widzi już
  // stan „niegotowy" i wraca do zwykłego zadania zamiast starego przycięcia.
  $("print-file").addEventListener("change", invalidateSpecial);
  $("print-page").addEventListener("change", invalidateSpecial);
  $("cut-file").addEventListener("change", invalidateSpecial);
  $("cut-page").addEventListener("change", invalidateSpecial);
  $("special-bleed").addEventListener("input", invalidateSpecial);
  const ed = $("special-editor");
  ed.addEventListener("pointerdown", editorPointerDown);
  ed.addEventListener("pointermove", editorPointerMove);
  ed.addEventListener("pointerup", editorPointerUp);
  ed.addEventListener("keydown", editorKey);
  $("controls").addEventListener("input", renderSpecialEditor);
  $("manual-canvas").addEventListener("pointermove", mcPointerMove);
  $("manual-canvas").addEventListener("pointerup", mcPointerUp);
  $("manual-canvas").addEventListener("pointerleave", mcPointerUp);
}

async function doUpload() {
  const files = $("upload-input").files;
  if (!files.length) return;
  const newNames = [];
  for (const f of files) {
    const fd = new FormData();
    fd.append("file", f);
    const r = await fetch("/api/upload", { method: "POST", body: fd });
    if (r.ok) {
      const info = await r.json();
      uploads[info.name] = info.page_count;
      uploadsInfo[info.name] = info;   // pełne info (page_sizes_mm itd.)
      newNames.push(info.name);
    } else {
      showError((await r.json()).detail || "Błąd wgrywania.");
    }
  }
  renderUploads();
  refreshFileSelectors();
  autoAssignSources(newNames);
  if (manualState.enabled) renderPalette();
  schedulePreview();
}

// Po wgraniu ustawia DOMYŚLNE źródła, ale TYLKO gdy pole jest puste (nigdy nie nadpisuje
// ręcznego wyboru). Reguła: 1. plik → druk (str.1); jeśli ten plik ma ≥2 strony →
// wykrojnik = ten sam plik, str.2; jeśli druk już ustawiony, a wykrojnik pusty →
// kolejny wgrany plik = wykrojnik (str.1). Przetwarza nowe pliki w kolejności wgrania.
function autoAssignSources(names) {
  for (const name of names) {
    const pages = uploads[name] || 0;
    if (!$("print-file").value) {
      assignSource("print-file", "print-page", name, 0);
      if (pages >= 2 && !$("cut-file").value) {
        assignSource("cut-file", "cut-page", name, 1);
      }
    } else if (!$("cut-file").value) {
      assignSource("cut-file", "cut-page", name, 0);
    }
  }
}

// Ustawia plik + stronę w parze selektów (opcje już wypełnione przez refreshFileSelectors).
function assignSource(fileId, pageId, name, page) {
  $(fileId).value = name;
  fillPages(fileId, pageId);               // odśwież listę stron dla wybranego pliku
  const pages = uploads[name] || 0;
  $(pageId).value = String(page < pages ? page : 0);
}

function renderUploads() {
  $("uploads-list").innerHTML = Object.entries(uploads)
    .map(([n, pc]) => `<li>${n} <span class="muted">(${pc} str.)</span></li>`).join("");
}

function fileOptionsHtml(selected) {
  const names = Object.keys(uploads);
  return ['<option value="">—</option>']
    .concat(names.map((n) => `<option value="${n}" ${n === selected ? "selected" : ""}>${n}</option>`))
    .join("");
}

function pageOptionsHtml(name, selected) {
  const n = uploads[name] || 0;
  let o = "";
  for (let i = 0; i < n; i++) o += `<option value="${i}" ${i === selected ? "selected" : ""}>${i + 1}</option>`;
  return o || '<option value="0">1</option>';
}

function refreshFileSelectors() {
  for (const id of ["print-file", "cut-file"]) {
    const sel = $(id);
    const cur = sel.value;
    sel.innerHTML = fileOptionsHtml(cur);
  }
  fillPages("print-file", "print-page");
  fillPages("cut-file", "cut-page");
  renderMontage();
}

function fillPages(fileId, pageId) {
  const name = $(fileId).value;
  const sel = $(pageId);
  const cur = parseInt(sel.value || "0", 10);
  sel.innerHTML = pageOptionsHtml(name, cur);
}

// Wspólna blokada trybu odstępów: montaż ORAZ tryb specjalny wymagają układu
// „z odstępami". Liczymy stan z OBU przełączników, żeby się nie nadpisywały
// (gdy jeden się wyłącza, a drugi wciąż chce blokady).
function updateGapLock() {
  const lock = $("montage-enable").checked || $("special-enable").checked;
  if (lock) {
    $("gap-on").checked = true;
    $("gap-off").disabled = true;
  } else {
    $("gap-off").disabled = false;
  }
}

function onMontageToggle() {
  const on = $("montage-enable").checked;
  if (on && montage.length === 0) addMontageRow();
  updateGapLock();
  schedulePreview();
}

function onSpecialToggle() {
  const on = $("special-enable").checked;
  $("special-body").hidden = !on;
  $("view-switch").hidden = !on;
  updateGapLock();
  setRightView(on ? "editor" : "preview");
  schedulePreview();
}

// Unieważnia gotowość trybu specjalnego: po przygotowaniu wykrojnika special.*
// trzyma PRZYCIĘTE uploady i rozmiar kafla dla KONKRETNEGO źródła/spadu. Gdy
// użytkownik zmieni plik/stronę druku lub wykrojnika albo spad, te dane są
// nieaktualne — kasujemy je, żeby collectParams() nie wysłał starego przycięcia
// (inaczej podgląd/generowanie pokazałyby grafikę, która już nie pasuje).
function invalidateSpecial() {
  special.ready = false;
  special.printUpload = null;
  special.cutUpload = null;
  special.pageW = 0;
  special.pageH = 0;
  tileImgUrl = null;
  renderSpecialEditor();
  const status = $("special-status");
  if ($("special-enable").checked) {
    status.classList.remove("err");
    status.textContent = "Zmieniono źródło/spad — kliknij „Przygotuj wykrojnik” ponownie.";
  } else {
    status.classList.remove("err");
    status.textContent = "";
  }
}

async function doSpecialPrepare() {
  const status = $("special-status");
  const payload = {
    print_upload: $("print-file").value,
    print_page: parseInt($("print-page").value || "0", 10),
    cut_upload: $("cut-file").value,
    cut_page: parseInt($("cut-page").value || "0", 10),
    bleed_mm: parseFloat($("special-bleed").value) || 0,
  };
  status.classList.remove("err");
  status.textContent = "Przygotowuję…";
  special.ready = false;
  let res;
  try {
    res = await fetch("/api/special/prepare", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch (e) {
    status.classList.add("err");
    status.textContent = "Błąd sieci: " + ((e && e.message) || e);
    return;
  }
  if (!res.ok) {
    let detail;
    try { detail = (await res.json()).detail; } catch (e) { detail = await res.text(); }
    status.classList.add("err");
    status.textContent = "Błąd: " + (detail || res.status);
    return;
  }
  const b = await res.json();
  special.printUpload = b.print_upload;
  special.cutUpload = b.cut_upload;
  special.pageW = b.page_width_mm;
  special.pageH = b.page_height_mm;
  special.ready = true;
  tileImgUrl = `/api/special/tile.png?t=${Date.now()}`;
  selectedTile = [1, 1];
  renderSpecialEditor();
  setRightView("editor");
  status.textContent = `Gotowe: kafel ${b.page_width_mm.toFixed(1)}×${b.page_height_mm.toFixed(1)} mm`;
  schedulePreview();
}

// --- Tryb manualny (montaż wolny) -------------------------------------------

// Fieldsety auto-układu chowane w trybie manualnym (po legendach).
function autoLayoutFieldsets() {
  const legends = ["Źródło (gdy bez montażu)", "Użytek (mm)", "Tryb", "Montaż wielu użytków"];
  return Array.from(document.querySelectorAll("#controls fieldset")).filter((fs) => {
    const lg = fs.querySelector("legend");
    return lg && legends.includes(lg.textContent.trim());
  });
}

function onManualToggle() {
  manualState.enabled = $("manual-free").checked;
  $("manual-panel").style.display = manualState.enabled ? "" : "none";
  for (const fs of autoLayoutFieldsets()) {
    // „Tryb" zostawiamy widoczny (jest w nim przełącznik manualny); reszta znika.
    const isModeFs = fs.querySelector("legend").textContent.trim() === "Tryb";
    if (!isModeFs) fs.style.display = manualState.enabled ? "none" : "";
  }
  if (manualState.enabled) { renderPalette(); renderCanvas(); }
}

// Paleta = wgrane PDF-y mające >= 2 strony (str.0=druk, str.1=wykrojnik).
function renderPalette() {
  const box = $("manual-palette");
  box.innerHTML = "";
  const names = Object.keys(uploads).filter((n) => (uploads[n] || 0) >= 2);
  if (names.length === 0) {
    box.innerHTML = '<span class="muted">Wgraj PDF 2-stronicowy (str.1 druk, str.2 wykrojnik).</span>';
    return;
  }
  names.forEach((name) => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "palette-chip";
    chip.textContent = name;
    chip.addEventListener("click", () => addInstance(name));
    box.appendChild(chip);
  });
}

function itemIndexForUpload(name) {
  let idx = manualState.items.findIndex((it) => it.upload === name);
  if (idx === -1) { manualState.items.push({ upload: name }); idx = manualState.items.length - 1; }
  return idx;
}

function addInstance(name) {
  const info = uploadsInfo[name];
  if (!info) return;
  const [wMm, hMm] = info.page_sizes_mm[0];
  const itemIndex = itemIndexForUpload(name);
  // domyślnie w środku obszaru roboczego OPOS
  const wa = workAreaMm();
  const xMm = wa.x + Math.max((wa.w - wMm) / 2, 0);
  const yMm = wa.y + Math.max((wa.h - hMm) / 2, 0);
  manualState.placements.push({ itemIndex, xMm, yMm, rot: 0, wMm, hMm });
  manualState.selected = manualState.placements.length - 1;
  renderCanvas();
}

function workAreaMm() {
  const sw = parseFloat($("sheet-w").value) || 0;
  const sh = parseFloat($("sheet-h").value) || 0;
  const side = parseFloat($("opos-side").value) || 0;
  const top = parseFloat($("opos-top").value) || 0;
  const bottom = parseFloat($("opos-bottom").value) || 0;
  return { x: side, y: top, w: Math.max(sw - 2 * side, 0), h: Math.max(sh - top - bottom, 0) };
}

const MC_SCALE = 2.2;   // px na mm (podgląd)
const SVGNS = "http://www.w3.org/2000/svg";

function mcRectBad(p, others, wa) {
  const outside = p.xMm < wa.x - 0.01 || p.yMm < wa.y - 0.01
    || p.xMm + p.wMm > wa.x + wa.w + 0.01 || p.yMm + p.hMm > wa.y + wa.h + 0.01;
  if (outside) return true;
  return others.some((o) => o !== p
    && p.xMm < o.xMm + o.wMm - 0.01 && o.xMm < p.xMm + p.wMm - 0.01
    && p.yMm < o.yMm + o.hMm - 0.01 && o.yMm < p.yMm + p.hMm - 0.01);
}

function renderCanvas() {
  const svg = $("manual-canvas");
  if (!svg) return;
  svg.innerHTML = "";
  const sw = parseFloat($("sheet-w").value) || 0;
  const sh = parseFloat($("sheet-h").value) || 0;
  svg.setAttribute("width", sw * MC_SCALE);
  svg.setAttribute("height", sh * MC_SCALE);
  const add = (tag, attrs, cls) => {
    const el = document.createElementNS(SVGNS, tag);
    for (const k in attrs) el.setAttribute(k, attrs[k]);
    if (cls) el.setAttribute("class", cls);
    svg.appendChild(el);
    return el;
  };
  add("rect", { x: 0, y: 0, width: sw * MC_SCALE, height: sh * MC_SCALE }, "mc-sheet");
  const wa = workAreaMm();
  add("rect", { x: wa.x * MC_SCALE, y: wa.y * MC_SCALE, width: wa.w * MC_SCALE, height: wa.h * MC_SCALE }, "mc-work");

  manualState.placements.forEach((p, i) => {
    const bad = mcRectBad(p, manualState.placements, wa);
    let cls = "mc-item";
    if (i === manualState.selected) cls += " sel";
    if (bad) cls += " bad";
    const rect = add("rect", {
      x: p.xMm * MC_SCALE, y: p.yMm * MC_SCALE,
      width: p.wMm * MC_SCALE, height: p.hMm * MC_SCALE,
      "data-idx": i,
    }, cls);
    rect.addEventListener("pointerdown", (e) => mcPointerDown(e, i));
    add("text", { x: (p.xMm + 2) * MC_SCALE, y: (p.yMm + 4) * MC_SCALE }, "mc-label")
      .textContent = `#${i + 1}${p.rot ? " " + p.rot + "°" : ""}`;
  });
}

function mcRotateSelected() {
  const p = manualState.placements[manualState.selected];
  if (!p) return;
  p.rot = (p.rot + 90) % 360;
  [p.wMm, p.hMm] = [p.hMm, p.wMm];
  renderCanvas();
}

function mcDuplicateSelected() {
  const p = manualState.placements[manualState.selected];
  if (!p) return;
  manualState.placements.push({ ...p, xMm: Math.round((p.xMm + 5) * 10) / 10, yMm: Math.round((p.yMm + 5) * 10) / 10 });
  manualState.selected = manualState.placements.length - 1;
  renderCanvas();
}

function mcDeleteSelected() {
  if (manualState.selected == null) return;
  manualState.placements.splice(manualState.selected, 1);
  manualState.selected = null;
  renderCanvas();
}

function mcNudge(dx, dy) {
  const p = manualState.placements[manualState.selected];
  if (!p) return;
  p.xMm = Math.round((p.xMm + dx) * 10) / 10;
  p.yMm = Math.round((p.yMm + dy) * 10) / 10;
  renderCanvas();
}

function mcKey(e) {
  if (!manualState.enabled || manualState.selected == null) return;
  const tag = e.target && e.target.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || (e.target && e.target.isContentEditable)) return;
  const step = e.shiftKey ? 10 : 1;
  const map = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] };
  if (map[e.key]) { e.preventDefault(); mcNudge(...map[e.key]); return; }
  if (e.key === "r" || e.key === "R") { e.preventDefault(); mcRotateSelected(); }
  else if (e.key === "d" || e.key === "D") { e.preventDefault(); mcDuplicateSelected(); }
  else if (e.key === "Delete" || e.key === "Backspace") { e.preventDefault(); mcDeleteSelected(); }
}

let mcDrag = null;   // { idx, startX, startY, origX, origY }

function mcPointerDown(e, idx) {
  e.preventDefault();
  manualState.selected = idx;
  const p = manualState.placements[idx];
  mcDrag = { idx, startX: e.clientX, startY: e.clientY, origX: p.xMm, origY: p.yMm };
  $("manual-canvas").setPointerCapture?.(e.pointerId);
  renderCanvas();
}

function mcPointerMove(e) {
  if (!mcDrag) return;
  const p = manualState.placements[mcDrag.idx];
  p.xMm = Math.round((mcDrag.origX + (e.clientX - mcDrag.startX) / MC_SCALE) * 10) / 10;
  p.yMm = Math.round((mcDrag.origY + (e.clientY - mcDrag.startY) / MC_SCALE) * 10) / 10;
  renderCanvas();
}

function mcPointerUp() { mcDrag = null; }

function addMontageRow() {
  montage.push({ label: "", print_upload: "", print_page: 0, cut_upload: "", cut_page: 0, quantity: 1 });
  renderMontage();
}

function renderMontage() {
  const box = $("montage-rows");
  const names = Object.keys(uploads);
  box.innerHTML = montage.map((m, i) => `
    <div class="montage-row" data-i="${i}">
      <input type="text" placeholder="etykieta" value="${m.label}" data-k="label">
      <select data-k="print_upload">${optList(names, m.print_upload)}</select>
      <input type="number" min="0" value="${m.print_page}" data-k="print_page" title="strona druku (od 0)">
      <select data-k="cut_upload">${optList(names, m.cut_upload)}</select>
      <input type="number" min="0" value="${m.cut_page}" data-k="cut_page" title="strona wykrojnika (od 0)">
      <input type="number" min="1" value="${m.quantity}" data-k="quantity" title="ilość">
      <button type="button" data-rm="${i}">usuń</button>
    </div>`).join("");
  box.querySelectorAll("[data-k]").forEach((el) => {
    el.addEventListener("input", () => {
      const row = el.closest(".montage-row");
      const i = parseInt(row.dataset.i, 10);
      const k = el.dataset.k;
      montage[i][k] = (k === "print_page" || k === "cut_page" || k === "quantity") ? parseInt(el.value || "0", 10) : el.value;
      schedulePreview();
    });
  });
  box.querySelectorAll("[data-rm]").forEach((b) => {
    b.addEventListener("click", () => {
      montage.splice(parseInt(b.dataset.rm, 10), 1);
      renderMontage();
      schedulePreview();
    });
  });
}

function optList(names, selected) {
  return ['<option value="">—</option>']
    .concat(names.map((n) => `<option value="${n}" ${n === selected ? "selected" : ""}>${n}</option>`))
    .join("");
}

function collectParams() {
  const gap = document.querySelector("input[name=gapmode]:checked").value === "gap";
  const params = {
    print_upload: $("print-file").value,
    print_page: parseInt($("print-page").value || "0", 10),
    cut_upload: $("cut-file").value || null,
    cut_page: parseInt($("cut-page").value || "0", 10),
    sheet_w_mm: parseFloat($("sheet-w").value),
    sheet_h_mm: parseFloat($("sheet-h").value),
    item_w_mm: parseFloat($("item-w").value),
    item_h_mm: parseFloat($("item-h").value),
    rotation_allowed: $("rotation").checked,
    gap_enabled: gap,
    gap_mm: parseFloat($("gap-mm").value),
    split_horizontal_groups: $("split").checked,
    split_max_spread: $("split-spread").checked,
    manual_grid_enabled: $("manual").checked,
    manual_columns: parseInt($("manual-cols").value || "0", 10),
    manual_rows: parseInt($("manual-rows").value || "0", 10),
    opos_side_offset_mm: parseFloat($("opos-side").value),
    opos_bottom_offset_mm: parseFloat($("opos-bottom").value),
    opos_top_offset_mm: parseFloat($("opos-top").value),
    montage: $("montage-enable").checked ? montage : [],
  };
  // Tryb specjalny: tylko gdy włączony I przygotowany (mamy przycięte uploady
  // i rozmiar kafla). Gdy zaznaczony, ale jeszcze nie przygotowany — nie wysyłamy
  // special_enabled, żeby podgląd/układ nie wybuchał (backend wymaga przygotowania).
  if ($("special-enable").checked && special.ready) {
    Object.assign(params, {
      print_upload: special.printUpload,
      cut_upload: special.cutUpload,
      print_page: 0,
      cut_page: 0,
      item_w_mm: special.pageW,
      item_h_mm: special.pageH,
      special_enabled: true,
      ...specialOffsets(),
    });
  }
  return params;
}

function schedulePreview() {
  clearTimeout(previewTimer);
  previewTimer = setTimeout(updatePreview, 300);
}

async function applyJob() {
  const r = await fetch("/api/job", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(collectParams()),
  });
  if (r.ok) {
    const s = await r.json();
    clearError();
    $("summary").textContent =
      `Użytków: ${s.count} (pojemność ${s.capacity_count}` +
      (s.requested_count ? `, zamówiono ${s.requested_count}` : "") +
      `) · ${s.rows}×${s.columns}` + (s.used_rotation ? " · obrót 90°" : "");
    return true;
  }
  showError((await r.json()).detail || "Błąd układu.");
  return false;
}

function setRightView(view) {
  rightView = view;
  const editorOn = view === "editor";
  $("view-editor").hidden = !editorOn;
  $("view-preview").hidden = editorOn;
  $("view-editor-btn").classList.toggle("active", editorOn);
  $("view-preview-btn").classList.toggle("active", !editorOn);
  if (editorOn) renderSpecialEditor();
}

function setPreviewWhich(which) {
  previewWhich = which;
  $("preview-print-btn").classList.toggle("active", which === "print");
  $("preview-cut-btn").classList.toggle("active", which === "cut");
  $("preview-img").src = `/api/preview/${which}.png?t=${Date.now()}`;
}

async function updatePreview() {
  const specialReady = $("special-enable").checked && special.ready;
  if (!$("print-file").value && !$("montage-enable").checked && !specialReady) return;
  if (await applyJob()) {
    $("preview-img").src = `/api/preview/${previewWhich}.png?t=${Date.now()}`;
  }
}

// Nazwa bazowa proponowana z pliku DRUKU (montaż: pierwszy użytek), bez .pdf.
// Gdy nie wybrano jawnie pliku druku, bierze pierwszy wgrany plik — żeby nazwa
// NIE spadała do "wynik", dopóki cokolwiek jest wgrane.
function computeBase() {
  let name = "";
  if ($("montage-enable").checked && montage.length && montage[0].print_upload) {
    name = montage[0].print_upload;
  } else {
    name = $("print-file").value;
  }
  if (!name) {
    const keys = Object.keys(uploads);
    if (keys.length) name = keys[0];
  }
  name = (name || "wynik").replace(/\.pdf$/i, "").trim();
  return name || "wynik";
}

async function doGenerate() {
  // Najpierw upewnij się, że bieżący układ jest poprawny i zapisany w sesji.
  if (!(await applyJob())) return;
  const base = computeBase();
  const r = await fetch("/api/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ base_name: base }),
  });
  if (!r.ok) {
    showError((await r.json()).detail || "Błąd generowania (najpierw ustaw poprawny układ).");
    return;
  }
  // Nazwy bierzemy z JEDNEJ odpowiedzi serwera — druk i wykrojnik mają zawsze
  // ten sam rdzeń, więc nie mogą się rozjechać.
  const names = await r.json();   // { print_name, cut_name }
  clearError();
  try {
    await saveOne("print", names.print_name);
    await saveOne("cut", names.cut_name);
    $("summary").textContent = `Zapisano: ${names.print_name} + ${names.cut_name}`;
  } catch (e) {
    if (e && e.name === "AbortError") { $("summary").textContent = "Zapis anulowany."; return; }
    showError("Błąd zapisu plików: " + ((e && e.message) || e));
  }
}

// Pobiera wygenerowany plik i zapisuje go. Gdy dostępne (HTTPS/localhost) —
// prawdziwe okno „Zapisz jako" z proponowaną nazwą i wyborem lokalizacji;
// w przeciwnym razie (lub gdy okno zawiedzie, np. utrata user-gesture przy
// drugim pliku) zwykłe pobranie z poprawną nazwą.
async function saveOne(which, filename) {
  const resp = await fetch(`/api/download/${which}?t=${Date.now()}`);
  if (!resp.ok) throw new Error(`pobranie „${which}" nieudane`);
  const blob = await resp.blob();
  if (window.showSaveFilePicker) {
    try {
      const handle = await window.showSaveFilePicker({
        suggestedName: filename,
        types: [{ description: "PDF", accept: { "application/pdf": [".pdf"] } }],
      });
      const w = await handle.createWritable();
      await w.write(blob);
      await w.close();
      return;
    } catch (e) {
      if (e && e.name === "AbortError") throw e;   // użytkownik anulował → przerwij
      // inny błąd (np. utrata aktywacji przy 2. pliku) → fallback na zwykłe pobranie
    }
  }
  downloadBlob(blob, filename);
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function showError(msg) { const e = $("error"); e.textContent = msg; e.hidden = false; }
function clearError() { $("error").hidden = true; }

init();
