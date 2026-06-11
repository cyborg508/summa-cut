"use strict";
const $ = (id) => document.getElementById(id);
const uploads = {};          // name -> page_count
let montage = [];            // [{label,print_upload,print_page,cut_upload,cut_page,quantity}]
let previewTimer = null;
// stan trybu specjalnego: po „Przygotuj" trzyma przycięte uploady i rozmiar kafla
const special = { printUpload: null, cutUpload: null, pageW: 0, pageH: 0, ready: false };

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
  $("montage-add").addEventListener("click", () => { addMontageRow(); schedulePreview(); });
  $("montage-enable").addEventListener("change", onMontageToggle);
  $("special-enable").addEventListener("change", onSpecialToggle);
  $("special-prepare-btn").addEventListener("click", doSpecialPrepare);
  // każda zmiana kontrolki → przeliczenie podglądu (debounce)
  $("controls").addEventListener("input", schedulePreview);
  $("controls").addEventListener("change", schedulePreview);
  // zmiana pliku → odśwież listę stron
  $("print-file").addEventListener("change", () => fillPages("print-file", "print-page"));
  $("cut-file").addEventListener("change", () => fillPages("cut-file", "cut-page"));
}

async function doUpload() {
  const files = $("upload-input").files;
  if (!files.length) return;
  for (const f of files) {
    const fd = new FormData();
    fd.append("file", f);
    const r = await fetch("/api/upload", { method: "POST", body: fd });
    if (r.ok) {
      const info = await r.json();
      uploads[info.name] = info.page_count;
    } else {
      showError((await r.json()).detail || "Błąd wgrywania.");
    }
  }
  renderUploads();
  refreshFileSelectors();
  schedulePreview();
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

function onMontageToggle() {
  const on = $("montage-enable").checked;
  if (on) {
    $("gap-on").checked = true;     // montaż wymaga trybu z odstępami
    $("gap-off").disabled = true;
    if (montage.length === 0) addMontageRow();
  } else {
    $("gap-off").disabled = false;
  }
  schedulePreview();
}

function onSpecialToggle() {
  const on = $("special-enable").checked;
  $("special-body").hidden = !on;
  if (on) {
    // tryb specjalny wymusza układ z odstępami (backend wymusza gap_enabled=True)
    $("gap-on").checked = true;
    $("gap-off").disabled = true;
  } else {
    $("gap-off").disabled = false;
  }
  schedulePreview();
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
  status.textContent = `Gotowe: kafel ${b.page_width_mm.toFixed(1)}×${b.page_height_mm.toFixed(1)} mm`;
  schedulePreview();
}

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

async function updatePreview() {
  const specialReady = $("special-enable").checked && special.ready;
  if (!$("print-file").value && !$("montage-enable").checked && !specialReady) return;
  if (await applyJob()) {
    const t = Date.now();
    $("preview-print").src = `/api/preview/print.png?t=${t}`;
    $("preview-cut").src = `/api/preview/cut.png?t=${t}`;
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
