"use strict";
const $ = (id) => document.getElementById(id);
const uploads = {};          // name -> page_count
let montage = [];            // [{label,print_upload,print_page,cut_upload,cut_page,quantity}]
let previewTimer = null;
let generated = false;

async function init() {
  await fetch("/api/session", { method: "POST" });
  wireEvents();
}

function wireEvents() {
  $("upload-btn").addEventListener("click", doUpload);
  $("generate-btn").addEventListener("click", doGenerate);
  $("montage-add").addEventListener("click", () => { addMontageRow(); schedulePreview(); });
  $("montage-enable").addEventListener("change", onMontageToggle);
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
  return {
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
}

function schedulePreview() {
  clearTimeout(previewTimer);
  previewTimer = setTimeout(updatePreview, 300);
}

async function updatePreview() {
  if (!$("print-file").value && !$("montage-enable").checked) return;
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
    const t = Date.now();
    $("preview-print").src = `/api/preview/print.png?t=${t}`;
    $("preview-cut").src = `/api/preview/cut.png?t=${t}`;
  } else {
    showError((await r.json()).detail || "Błąd układu.");
  }
}

async function doGenerate() {
  const r = await fetch("/api/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ base_name: $("base-name").value || "wynik" }),
  });
  if (r.ok) {
    clearError();
    generated = true;
    const t = Date.now();
    const dp = $("download-print"), dc = $("download-cut");
    dp.href = `/api/download/print?t=${t}`; dp.hidden = false;
    dc.href = `/api/download/cut?t=${t}`; dc.hidden = false;
    $("summary").textContent = "Wygenerowano. Pobierz pliki po prawej.";
  } else {
    showError((await r.json()).detail || "Błąd generowania (najpierw ustaw poprawny układ).");
  }
}

function showError(msg) { const e = $("error"); e.textContent = msg; e.hidden = false; }
function clearError() { $("error").hidden = true; }

init();
