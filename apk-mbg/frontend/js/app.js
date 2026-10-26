(() => {
  "use strict";

  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));

  const statusDot = $("#statusDot");
  const statusText = $("#statusText");

  const ICONS = {
    pokok: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none"><path d="M3 12C3 12 4 20 12 20C20 20 21 12 21 12H3Z" fill="currentColor"/><path d="M12 4C7 4 4 8 4 8H20C20 8 17 4 12 4Z" fill="currentColor" opacity="0.55"/></svg>',
    lauk: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none"><path d="M8 3C8 3 6 6 6 9C6 11.5 7.5 13 9.5 13C9.5 13 7 17 5 21" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M13 3C13 3 20 6 20 12C20 16 16.5 18 13.5 17C11 16.2 10 13.5 11 11C11.8 9 13.5 8 13.5 8" fill="currentColor" opacity="0.5"/></svg>',
    sayur: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none"><path d="M12 22C12 22 4 18 4 10C4 5 8 3 12 6C16 3 20 5 20 10C20 18 12 22 12 22Z" fill="currentColor" opacity="0.55"/><path d="M12 6V2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
    buah: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="14" r="7" fill="currentColor" opacity="0.55"/><path d="M12 7C12 7 12 3 16 2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
    susu: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none"><path d="M9 2H15V5.2L17 8V21C17 21.55 16.55 22 16 22H8C7.45 22 7 21.55 7 21V8L9 5.2V2Z" fill="currentColor" opacity="0.6"/></svg>',
  };

  const NUT_LABEL = { energi: "Energi", protein: "Protein", lemak: "Lemak", karbo: "Karbo" };
  const NUT_UNIT = { energi: "kkal", protein: "g", lemak: "g", karbo: "g" };

  let datasetInfo = null;

  // ---------------------------------------------------------------- init --
  async function init() {
    bindSliders();
    bindSeedToggle();
    bindTabs();
    bindNav();
    bindMakananView();
    bindMenuTetapView();
    bindTargetView();
    bindRiwayatView();
    $("#runBtn").addEventListener("click", runOptimization);

    try {
      const res = await fetch("/api/info");
      if (!res.ok) throw new Error("info fetch failed");
      datasetInfo = await res.json();
      renderKategoriSizeTable(datasetInfo);
      renderAkgTable(datasetInfo);
      renderSusuNote(datasetInfo);
      applyDefaultPenalty(datasetInfo);
      setStatus("ready", "Dataset siap (MySQL)");
    } catch (err) {
      setStatus("busy", "Gagal memuat info dataset dari server");
      console.error(err);
    }
  }

  function renderSusuNote(info) {
    const susu = info && info.susu;
    const label = $("#susuNoteLabel");
    if (!label) return;
    if (susu && susu.nama) {
      const berat = susu.berat != null ? `${Number(susu.berat).toFixed(0)} ml` : "";
      label.textContent = `${susu.nama}${berat ? " " + berat : ""} · komponen gizi tetap`;
    } else {
      label.textContent = "Menu tetap · komponen gizi tetap";
    }
  }

  // ------------------------------------------------------------ nav view --
  function bindNav() {
    $$(".mainnav__link").forEach((btn) => {
      btn.addEventListener("click", () => {
        $$(".mainnav__link").forEach((b) => b.classList.remove("is-active"));
        $$(".view").forEach((v) => { v.classList.remove("is-active"); v.hidden = true; });
        btn.classList.add("is-active");
        const view = document.getElementById("view-" + btn.dataset.view);
        view.classList.add("is-active");
        view.hidden = false;
        if (btn.dataset.view === "makanan") {
          loadMenuTetapList();
          loadMakananList();
        }
        if (btn.dataset.view === "target") loadTargetGizi();
        if (btn.dataset.view === "riwayat") loadRiwayatList();
      });
    });
  }

  function setStatus(mode, text) {
    statusDot.classList.remove("is-ready", "is-busy");
    if (mode === "ready") statusDot.classList.add("is-ready");
    if (mode === "busy") statusDot.classList.add("is-busy");
    statusText.textContent = text;
  }

  // ------------------------------------------------------------- seed -----
  function bindSeedToggle() {
    const checkbox = $("#seedAktifInput");
    const input = $("#seedInput");
    const noteOn = $("#seedNote");
    const noteOff = $("#seedNoteOff");
    const update = () => {
      const aktif = checkbox.checked;
      input.disabled = !aktif;
      input.required = aktif;
      noteOn.hidden = !aktif;
      noteOff.hidden = aktif;
    };
    checkbox.addEventListener("change", update);
    update();
  }

  // ------------------------------------------------------------- sliders --
  function bindSliders() {
    const pairs = [
      ["popSize", "popSizeVal", (v) => v],
      ["maxGen", "maxGenVal", (v) => v],
      ["pc", "pcVal", (v) => Number(v).toFixed(2)],
      ["pm", "pmVal", (v) => Number(v).toFixed(2)],
      ["jarakMinimum", "jarakMinimumVal", (v) => `${v} hari`],
      ["penaltiPokok", "penaltiPokokVal", (v) => Number(v).toFixed(1)],
      ["penaltiLauk", "penaltiLaukVal", (v) => Number(v).toFixed(1)],
      ["penaltiSayur", "penaltiSayurVal", (v) => Number(v).toFixed(1)],
      ["penaltiBuah", "penaltiBuahVal", (v) => Number(v).toFixed(1)],
    ];
    pairs.forEach(([inputId, outId, fmt]) => {
      const input = document.getElementById(inputId);
      const out = document.getElementById(outId);
      const update = () => {
        out.textContent = fmt(input.value);
        const pct = ((input.value - input.min) / (input.max - input.min)) * 100;
        input.style.setProperty("--fill", pct + "%");
      };
      input.addEventListener("input", update);
      update();
    });
  }

  function applyDefaultPenalty(info) {
    if (!info || !info.defaults) return;
    const d = info.defaults;
    const setSlider = (id, val) => {
      const el = document.getElementById(id);
      if (el == null || val == null) return;
      el.value = val;
      el.dispatchEvent(new Event("input"));
    };
    setSlider("jarakMinimum", d.jarak_minimum);
    setSlider("penaltiPokok", d.penalti_kategori.pokok);
    setSlider("penaltiLauk", d.penalti_kategori.lauk);
    setSlider("penaltiSayur", d.penalti_kategori.sayur);
    setSlider("penaltiBuah", d.penalti_kategori.buah);
  }

  // ---------------------------------------------------------------- tabs --
  function bindTabs() {
    $$(".tab").forEach((tab) => {
      tab.addEventListener("click", () => {
        $$(".tab").forEach((t) => t.classList.remove("is-active"));
        $$(".tab-panel").forEach((p) => p.classList.remove("is-active"));
        tab.classList.add("is-active");
        $("#tab-" + tab.dataset.tab).classList.add("is-active");
        if (tab.dataset.tab === "pareto" && window.__lastResult) {
          drawParetoChart(window.__lastResult);
        }
        if (tab.dataset.tab === "konvergensi" && window.__lastResult) {
          drawConvergenceChart(window.__lastResult);
        }
      });
    });
  }

  // ------------------------------------------------- render: kategori size --
  function renderKategoriSizeTable(info) {
    const tbody = $("#kategoriSizeTable tbody");
    tbody.innerHTML = "";
    Object.entries(info.category_sizes).forEach(([cat, size]) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td class="t-cat">${cat}</td>
        <td class="t-size">${size} item</td>`;
      tbody.appendChild(tr);
    });
  }

  function renderAkgTable(info) {
    const tbody = $("#akgTable tbody");
    tbody.innerHTML = "";
    const order = ["energi", "protein", "lemak", "karbo"];
    order.forEach((k) => {
      const bb = info.target_akg.batas_bawah[k];
      const ba = info.target_akg.batas_atas[k];
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td class="t-nutrient">${NUT_LABEL[k]}</td>
        <td class="t-range">${bb}&ndash;${ba} ${NUT_UNIT[k]}</td>`;
      tbody.appendChild(tr);
    });
  }

  // ------------------------------------------------------------- run ------
  async function runOptimization() {
    const btn = $("#runBtn");
    const label = $("#runBtnLabel");
    const progressWrap = $("#progressWrap");

    const seedAktif = $("#seedAktifInput").checked;
    const seedRaw = $("#seedInput").value.trim();
    const payload = {
      pop_size: Number($("#popSize").value),
      max_gen: Number($("#maxGen").value),
      pc: Number($("#pc").value),
      pm: Number($("#pm").value),
      seed_aktif: seedAktif,
      seed: seedAktif ? (seedRaw === "" ? 42 : Number(seedRaw)) : null,
      jarak_minimum: Number($("#jarakMinimum").value),
      penalti_pokok: Number($("#penaltiPokok").value),
      penalti_lauk: Number($("#penaltiLauk").value),
      penalti_sayur: Number($("#penaltiSayur").value),
      penalti_buah: Number($("#penaltiBuah").value),
    };

    btn.disabled = true;
    label.textContent = "Mengoptimasi...";
    progressWrap.hidden = false;
    $("#progressFill").style.width = "12%";
    $("#progressLabel").textContent = `Menjalankan ${payload.max_gen} generasi \u00d7 ${payload.pop_size} individu\u2026`;
    setStatus("busy", "NSGA-II sedang berjalan\u2026");

    // indeterminate progress animation while waiting for the (synchronous) response
    let pct = 12;
    const ticker = setInterval(() => {
      pct = Math.min(pct + Math.random() * 9, 92);
      $("#progressFill").style.width = pct + "%";
    }, 220);

    try {
      const res = await fetch("/api/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error("Permintaan optimasi gagal (" + res.status + ")");
      const result = await res.json();
      clearInterval(ticker);
      $("#progressFill").style.width = "100%";
      $("#progressLabel").textContent = `Selesai dalam ${result.elapsed_seconds}s`;
      window.__lastResult = result;
      renderResults(result);
      setStatus("ready", "Optimasi selesai");
    } catch (err) {
      clearInterval(ticker);
      $("#progressLabel").textContent = "Terjadi kesalahan. Coba lagi.";
      setStatus("busy", "Gagal menjalankan optimasi");
      console.error(err);
    } finally {
      btn.disabled = false;
      label.textContent = "Jalankan Optimasi";
      setTimeout(() => { progressWrap.hidden = true; }, 1800);
    }
  }

  // --------------------------------------------------------- render all --
  function renderResults(result) {
    $("#emptyState").hidden = true;
    $("#resultsArea").hidden = false;

    const banner = $("#kontinuitasBanner");
    if (result.kontinuitas_periode) {
      const kp = result.kontinuitas_periode;
      let teks = kp.keterangan;
      if (kp.hari_dilewati) {
        teks += ` (${kp.hari_dilewati} hari riwayat dilewati karena data makanannya sudah berubah/dihapus.)`;
      }
      banner.textContent = teks;
      banner.hidden = false;
    } else {
      banner.hidden = true;
    }

    $("#statElapsed").textContent = result.elapsed_seconds;
    const popN = result.population_points.length;
    const feasibleN = result.population_points.filter((p) => p.feasible).length;
    $("#statFeasible").textContent = `${feasibleN}/${popN}`;
    $("#statFront1").textContent = result.front1_size;
    $("#statBestF2").textContent = result.best.f2;
    $("#statBestF1").textContent = result.best.f1;

    drawParetoChart(result);
    drawConvergenceChart(result);
    renderMenu(result.best, result.pengulangan_tersisa);
  }

  // ----------------------------------------------------- pareto chart -----
  function drawParetoChart(result) {
    const canvas = $("#paretoCanvas");
    const wrap = canvas.parentElement;
    const dpr = window.devicePixelRatio || 1;
    const cssW = wrap.clientWidth;
    const cssH = wrap.clientHeight;
    canvas.width = cssW * dpr;
    canvas.height = cssH * dpr;
    canvas.style.width = cssW + "px";
    canvas.style.height = cssH + "px";
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, cssW, cssH);

    const pad = { top: 16, right: 20, bottom: 34, left: 46 };
    const plotW = cssW - pad.left - pad.right;
    const plotH = cssH - pad.top - pad.bottom;

    const pts = result.population_points;
    const front1Set = new Set(result.front1_points.map((p) => p.f1 + "|" + p.f2));

    const f1s = pts.map((p) => p.f1);
    const f2s = pts.map((p) => p.f2);
    const f1min = Math.min(...f1s, 0), f1max = Math.max(...f1s, 1);
    const f2min = Math.min(...f2s, 0), f2max = Math.max(...f2s, 1);
    const padRatio = 0.08;
    const f1span = (f1max - f1min) || 1, f2span = (f2max - f2min) || 1;
    const xlo = f1min - f1span * padRatio, xhi = f1max + f1span * padRatio;
    const ylo = f2min - f2span * padRatio, yhi = f2max + f2span * padRatio;

    const X = (v) => pad.left + ((v - xlo) / (xhi - xlo)) * plotW;
    const Y = (v) => pad.top + plotH - ((v - ylo) / (yhi - ylo)) * plotH;

    // gridlines
    ctx.strokeStyle = "#E3D9C2";
    ctx.lineWidth = 1;
    const GRID_N = 5;
    ctx.font = "11px 'JetBrains Mono', monospace";
    ctx.fillStyle = "#9A9C8E";
    for (let i = 0; i <= GRID_N; i++) {
      const gx = pad.left + (plotW / GRID_N) * i;
      ctx.beginPath(); ctx.moveTo(gx, pad.top); ctx.lineTo(gx, pad.top + plotH); ctx.stroke();
      const vx = xlo + ((xhi - xlo) / GRID_N) * i;
      ctx.fillText(vx.toFixed(1), gx - 10, pad.top + plotH + 18);

      const gy = pad.top + (plotH / GRID_N) * i;
      ctx.beginPath(); ctx.moveTo(pad.left, gy); ctx.lineTo(pad.left + plotW, gy); ctx.stroke();
      const vy = yhi - ((yhi - ylo) / GRID_N) * i;
      ctx.fillText(vy.toFixed(1), 6, gy + 4);
    }

    // axes
    ctx.strokeStyle = "#23281F";
    ctx.lineWidth = 1.4;
    ctx.beginPath();
    ctx.moveTo(pad.left, pad.top); ctx.lineTo(pad.left, pad.top + plotH); ctx.lineTo(pad.left + plotW, pad.top + plotH);
    ctx.stroke();

    // points: infeasible -> feasible -> front1 (draw order = z-order)
    const screenPts = pts.map((p) => ({
      ...p,
      x: X(p.f1), y: Y(p.f2),
      isFront1: front1Set.has(p.f1 + "|" + p.f2),
    }));

    const drawDot = (p, color, r) => {
      ctx.beginPath();
      ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.fill();
    };

    screenPts.filter((p) => !p.feasible).forEach((p) => drawDot(p, "#C9C6BA", 4));
    screenPts.filter((p) => p.feasible && !p.isFront1).forEach((p) => drawDot(p, "#3E7CB1", 4.5));
    screenPts.filter((p) => p.isFront1).forEach((p) => {
      drawDot(p, "#C1442D", 5.5);
      ctx.beginPath(); ctx.arc(p.x, p.y, 5.5, 0, Math.PI * 2);
      ctx.strokeStyle = "#fff"; ctx.lineWidth = 1.2; ctx.stroke();
    });

    // hover tooltip
    const tooltip = $("#chartTooltip");
    canvas.onmousemove = (ev) => {
      const rect = canvas.getBoundingClientRect();
      const mx = ev.clientX - rect.left, my = ev.clientY - rect.top;
      let nearest = null, bestDist = 14;
      screenPts.forEach((p) => {
        const d = Math.hypot(p.x - mx, p.y - my);
        if (d < bestDist) { bestDist = d; nearest = p; }
      });
      if (nearest) {
        tooltip.hidden = false;
        tooltip.style.left = nearest.x + "px";
        tooltip.style.top = nearest.y + "px";
        tooltip.textContent = `f1=${nearest.f1.toFixed(2)}  f2=${nearest.f2.toFixed(2)}  ${nearest.feasible ? "feasible" : "infeasible"}`;
      } else {
        tooltip.hidden = true;
      }
    };
    canvas.onmouseleave = () => { tooltip.hidden = true; };
  }

  // ------------------------------------------------- konvergensi chart -----
  function drawConvergenceChart(result) {
    const canvas = $("#convergenceCanvas");
    if (!canvas) return;
    const log = result.generations_log || [];
    if (log.length === 0) return;

    const wrap = canvas.parentElement;
    const dpr = window.devicePixelRatio || 1;
    const cssW = wrap.clientWidth;
    const cssH = wrap.clientHeight;
    canvas.width = cssW * dpr;
    canvas.height = cssH * dpr;
    canvas.style.width = cssW + "px";
    canvas.style.height = cssH + "px";
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, cssW, cssH);

    const pad = { top: 16, right: 20, bottom: 34, left: 46 };
    const plotW = cssW - pad.left - pad.right;
    const plotH = cssH - pad.top - pad.bottom;

    const gens = log.map((g) => g.generasi);
    const f1s = log.map((g) => g.best_f1);
    const f2s = log.map((g) => (g.best_f2 !== undefined ? g.best_f2 : null));
    const hasF2 = f2s.every((v) => v !== null);

    const xmin = Math.min(...gens), xmax = Math.max(...gens, 1);
    const allVals = hasF2 ? f1s.concat(f2s) : f1s;
    const ymin = Math.min(...allVals, 0), ymax = Math.max(...allVals, 1);
    const yspan = (ymax - ymin) || 1;
    const padRatio = 0.08;
    const ylo = ymin - yspan * padRatio, yhi = ymax + yspan * padRatio;

    const X = (v) => pad.left + ((v - xmin) / ((xmax - xmin) || 1)) * plotW;
    const Y = (v) => pad.top + plotH - ((v - ylo) / (yhi - ylo)) * plotH;

    // gridlines
    ctx.strokeStyle = "#E3D9C2";
    ctx.lineWidth = 1;
    const GRID_N = 5;
    ctx.font = "11px 'JetBrains Mono', monospace";
    ctx.fillStyle = "#9A9C8E";
    for (let i = 0; i <= GRID_N; i++) {
      const gx = pad.left + (plotW / GRID_N) * i;
      ctx.beginPath(); ctx.moveTo(gx, pad.top); ctx.lineTo(gx, pad.top + plotH); ctx.stroke();
      const vx = xmin + ((xmax - xmin) / GRID_N) * i;
      ctx.fillText(Math.round(vx), gx - 6, pad.top + plotH + 18);

      const gy = pad.top + (plotH / GRID_N) * i;
      ctx.beginPath(); ctx.moveTo(pad.left, gy); ctx.lineTo(pad.left + plotW, gy); ctx.stroke();
      const vy = yhi - ((yhi - ylo) / GRID_N) * i;
      ctx.fillText(vy.toFixed(1), 6, gy + 4);
    }

    // axes
    ctx.strokeStyle = "#23281F";
    ctx.lineWidth = 1.4;
    ctx.beginPath();
    ctx.moveTo(pad.left, pad.top); ctx.lineTo(pad.left, pad.top + plotH); ctx.lineTo(pad.left + plotW, pad.top + plotH);
    ctx.stroke();

    const drawLine = (values, color) => {
      ctx.beginPath();
      values.forEach((v, i) => {
        const x = X(gens[i]), y = Y(v);
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      });
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.stroke();
    };

    // f2 (variasi menu / prioritas seleksi) digambar dengan warna aksen, f1 sebagai pembanding
    if (hasF2) drawLine(f2s, "#D98324");
    drawLine(f1s, "#3E7CB1");
  }

  window.addEventListener("resize", () => {
    if (window.__lastResult && $("#tab-pareto").classList.contains("is-active")) {
      drawParetoChart(window.__lastResult);
    }
    if (window.__lastResult && $("#tab-konvergensi").classList.contains("is-active")) {
      drawConvergenceChart(window.__lastResult);
    }
  });

  // ------------------------------------------------------------- menu -----
  function renderMenu(best, pengulanganTersisa) {
    const banner = $("#menuBanner");
    const badge = best.feasible
      ? `<span class="badge badge--ok">FEASIBLE</span>`
      : `<span class="badge badge--warn">BELUM FEASIBLE</span>`;
    const pt = pengulanganTersisa || {};
    const pokokRep = pt.pokok ?? 0;
    const laukRep = pt.lauk ?? 0;
    const repBadge = (n, label) => n > 0
      ? `<span class="badge badge--warn">${label}: ${n} pasang hari sama</span>`
      : `<span class="badge badge--ok">${label}: tidak ada pengulangan</span>`;

    const idHasil = window.__lastResult && window.__lastResult.id_hasil;
    const exportBtn = idHasil
      ? `<a class="btn-secondary btn-secondary--sm" href="/api/riwayat/${idHasil}/export" download style="margin-left:auto;">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" style="vertical-align:-2px; margin-right:4px;"><path d="M12 4V15M12 15L8 11M12 15L16 11M5 19H19" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
          Export Excel
        </a>`
      : "";

    banner.innerHTML = `
      ${badge}
      <span>f1 (deviasi gizi): <b>${best.f1}</b></span>
      <span>f2 (pengulangan): <b>${best.f2}</b></span>
      ${repBadge(pokokRep, "Pokok")}
      ${repBadge(laukRep, "Lauk")}
      ${best.fallback ? '<span style="color:#C1442D">Populasi akhir belum sepenuhnya feasible &mdash; tampilkan individu pelanggaran terkecil. Perbesar generasi/populasi untuk hasil lebih baik.</span>' : ""}
      ${(pokokRep > 0 || laukRep > 0) ? '<span style="color:#9C5F16">Masih ada pengulangan? Naikkan jarak minimum &amp; bobot penalti di panel kiri, lalu jalankan ulang.</span>' : ""}
      ${exportBtn}
    `;
  

    // Hitung frekuensi kemunculan tiap nama item di seluruh 10 hari, untuk
    // seluruh kategori kandidat (pokok, lauk, sayur, buah) — susu tidak
    // ikut ditandai karena komponennya tetap/fixed, bukan kandidat rotasi.
    const freq = { pokok: {}, lauk: {}, sayur: {}, buah: {} };
    best.menu.forEach((day) => {
      ["pokok", "lauk", "sayur", "buah"].forEach((cat) => {
        const nama = day[cat].nama;
        freq[cat][nama] = (freq[cat][nama] || 0) + 1;
      });
    });

    const grid = $("#trayGrid");
    grid.innerHTML = "";
    best.menu.forEach((day) => {
      const allOk = Object.values(day.gizi).every((g) => g.status === "terpenuhi");
      const tray = document.createElement("div");
      tray.className = "tray";
      tray.innerHTML = `
        <div class="tray__head">
          <span class="tray__day">Hari ${day.hari}</span>
          <span class="tray__status ${allOk ? "ok" : "warn"}">${allOk ? "Gizi Terpenuhi" : "Perlu Ditinjau"}</span>
        </div>
        <div class="tray__compartments">
          ${compartment("pokok", day.pokok, freq.pokok[day.pokok.nama] > 1)}
          ${compartment("lauk", day.lauk, freq.lauk[day.lauk.nama] > 1)}
          ${compartment("sayur", day.sayur, freq.sayur[day.sayur.nama] > 1)}
          ${compartment("buah", day.buah, freq.buah[day.buah.nama] > 1)}
        </div>
        <div class="tray__milk">
          <span class="compartment__icon">${ICONS.susu}</span>
          <span>${day.minuman.nama}${day.minuman.berat != null ? ` ${Number(day.minuman.berat).toFixed(0)}&nbsp;ml` : ""} <em style="color:var(--ink-faint); font-style:normal;">(tetap)</em></span>
        </div>
        <div class="tray__nutrients">
          ${nutCell("energi", day.gizi.energi)}
          ${nutCell("protein", day.gizi.protein)}
          ${nutCell("lemak", day.gizi.lemak)}
          ${nutCell("karbo", day.gizi.karbo)}
        </div>
      `;
      grid.appendChild(tray);
    });
  }

  function compartment(cat, item, isRepeated) {
    const beratHtml = item.berat != null
      ? `<span class="compartment__meta">${Number(item.berat).toFixed(0)}&nbsp;g</span>`
      : "";
    return `
      <div class="compartment compartment--${cat}${isRepeated ? " compartment--dup" : ""}">
        <span class="compartment__icon">${ICONS[cat]}</span>
        <span class="compartment__body">
          <span class="compartment__label">${cat}${isRepeated ? ' <span class="dup-flag">terulang</span>' : ""}</span>
          <span class="compartment__name">${item.nama}</span>
          ${beratHtml}
        </span>
      </div>`;
  }

  function nutCell(key, g) {
    const ok = g.status === "terpenuhi";
    return `
      <div class="nut-cell ${ok ? "ok" : "warn"}">
        <div class="nut-cell__label">${NUT_LABEL[key]}</div>
        <div class="nut-cell__value">${g.nilai}</div>
      </div>`;
  }

  // ======================================================================
  // DATA MAKANAN (CRUD)
  // ======================================================================
  function bindMakananView() {
    $("#makananFilterKategori").addEventListener("change", loadMakananList);
    let searchTimer;
    $("#makananSearch").addEventListener("input", () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(loadMakananList, 300);
    });

    $("#btnTambahMakanan").addEventListener("click", () => openMakananModal());
    $("#btnCloseMakananModal").addEventListener("click", closeMakananModal);
    $("#btnCancelMakananModal").addEventListener("click", closeMakananModal);
    $("#makananModalOverlay").addEventListener("click", (e) => {
      if (e.target.id === "makananModalOverlay") closeMakananModal();
    });
    $("#makananForm").addEventListener("submit", submitMakananForm);

    $("#btnImportCsv").addEventListener("click", () => {
      $("#importResult").hidden = true;
      $("#importForm").reset();
      $("#importModalOverlay").hidden = false;
    });
    $("#btnCloseImportModal").addEventListener("click", closeImportModal);
    $("#btnCancelImportModal").addEventListener("click", closeImportModal);
    $("#importModalOverlay").addEventListener("click", (e) => {
      if (e.target.id === "importModalOverlay") closeImportModal();
    });
    $("#importForm").addEventListener("submit", submitImportForm);
  }

  function closeImportModal() {
    $("#importModalOverlay").hidden = true;
  }

  async function submitImportForm(e) {
    e.preventDefault();
    const fileInput = $("#importFile");
    if (!fileInput.files.length) return;
    const fd = new FormData();
    fd.append("file_csv", fileInput.files[0]);
    const resultBox = $("#importResult");
    try {
      const res = await fetch("/api/makanan/import", { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error((data.errors || [data.error]).join(", "));
      resultBox.hidden = false;
      resultBox.textContent = `${data.sukses} data berhasil diimpor.` +
        (data.gagal.length ? `\n${data.gagal.length} baris gagal:\n` + data.gagal.slice(0, 8).join("\n") : "");
      loadMakananList();
    } catch (err) {
      resultBox.hidden = false;
      resultBox.className = "form-error";
      resultBox.textContent = "Gagal import: " + err.message;
    }
  }

  async function loadMakananList() {
    const kategori = $("#makananFilterKategori").value;
    const q = $("#makananSearch").value.trim();
    const params = new URLSearchParams();
    if (kategori) params.set("kategori", kategori);
    if (q) params.set("q", q);
    try {
      const res = await fetch("/api/makanan?" + params.toString());
      const data = await res.json();
      renderMakananTable(data);
    } catch (err) {
      console.error(err);
    }
  }

  function renderMakananTable(rows) {
    const tbody = $("#makananTableBody");
    if (!rows.length) {
      tbody.innerHTML = `<tr class="empty-row"><td colspan="8">Belum ada data.</td></tr>`;
      return;
    }
    tbody.innerHTML = rows.map((m) => `
      <tr>
        <td style="font-weight:600;">${m.nama}</td>
        <td><span class="kategori-chip ${m.kategori}">${m.kategori}</span></td>
        <td class="num">${Number(m.berat).toFixed(0)}</td>
        <td class="num">${Number(m.energi).toFixed(1)}</td>
        <td class="num">${Number(m.protein).toFixed(1)}</td>
        <td class="num">${Number(m.lemak).toFixed(1)}</td>
        <td class="num">${Number(m.karbo).toFixed(1)}</td>
        <td>
          <div class="row-actions">
            <button class="icon-btn" title="Edit" onclick="window.__editMakanan(${m.id_makanan})">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M4 20L4.5 16.5L16 5L19 8L7.5 19.5L4 20Z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>
            </button>
            <button class="icon-btn danger" title="Hapus" onclick="window.__deleteMakanan(${m.id_makanan}, '${m.nama.replace(/'/g, "\\'")}')">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M5 7H19M9 7V5C9 4 9.8 3 11 3H13C14.2 3 15 4 15 5V7M17 7L16.3 19C16.2 20.1 15.3 21 14.2 21H9.8C8.7 21 7.8 20.1 7.7 19L7 7" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </button>
          </div>
        </td>
      </tr>
    `).join("");
  }

  function openMakananModal(data) {
    $("#makananModalTitle").textContent = data ? "Edit Makanan" : "Tambah Makanan";
    $("#makananId").value = data ? data.id_makanan : "";
    $("#makananNama").value = data ? data.nama : "";
    $("#makananKategori").value = data ? data.kategori : "pokok";
    $("#makananBerat").value = data ? data.berat : "";
    $("#makananEnergi").value = data ? data.energi : "";
    $("#makananProtein").value = data ? data.protein : "";
    $("#makananLemak").value = data ? data.lemak : "";
    $("#makananKarbo").value = data ? data.karbo : "";
    $("#makananFormError").hidden = true;
    $("#makananModalOverlay").hidden = false;
  }

  function closeMakananModal() {
    $("#makananModalOverlay").hidden = true;
  }

  async function submitMakananForm(e) {
    e.preventDefault();
    const id = $("#makananId").value;
    const payload = {
      nama: $("#makananNama").value.trim(),
      kategori: $("#makananKategori").value,
      berat: Number($("#makananBerat").value),
      energi: Number($("#makananEnergi").value),
      protein: Number($("#makananProtein").value),
      lemak: Number($("#makananLemak").value),
      karbo: Number($("#makananKarbo").value),
    };
    const errBox = $("#makananFormError");
    try {
      const url = id ? `/api/makanan/${id}` : "/api/makanan";
      const res = await fetch(url, {
        method: id ? "PUT" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) throw new Error((data.errors || ["Gagal menyimpan"]).join("\n"));
      closeMakananModal();
      loadMakananList();
    } catch (err) {
      errBox.hidden = false;
      errBox.textContent = err.message;
    }
  }

  window.__editMakanan = async (id) => {
    const res = await fetch(`/api/makanan?q=`);
    const all = await res.json();
    const item = all.find((m) => m.id_makanan === id);
    if (item) openMakananModal(item);
  };

  window.__deleteMakanan = async (id, nama) => {
    if (!confirm(`Hapus "${nama}"?`)) return;
    try {
      const res = await fetch(`/api/makanan/${id}`, { method: "DELETE" });
      const data = await res.json();
      if (!res.ok) throw new Error((data.errors || ["Gagal menghapus"]).join("\n"));
      loadMakananList();
    } catch (err) {
      alert(err.message);
    }
  };

  // ======================================================================
  // MENU TETAP (SUSU)
  // ======================================================================
  function bindMenuTetapView() {
    let searchTimer;
    $("#menuTetapSearch").addEventListener("input", () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(loadMenuTetapList, 300);
    });

    $("#btnTambahMenuTetap").addEventListener("click", () => openMenuTetapModal());
    $("#btnCloseMenuTetapModal").addEventListener("click", closeMenuTetapModal);
    $("#btnCancelMenuTetapModal").addEventListener("click", closeMenuTetapModal);
    $("#menuTetapModalOverlay").addEventListener("click", (e) => {
      if (e.target.id === "menuTetapModalOverlay") closeMenuTetapModal();
    });
    $("#menuTetapForm").addEventListener("submit", submitMenuTetapForm);

    $("#btnImportMenuTetapCsv").addEventListener("click", () => {
      $("#importMenuTetapResult").hidden = true;
      $("#importMenuTetapForm").reset();
      $("#importMenuTetapModalOverlay").hidden = false;
    });
    $("#btnCloseImportMenuTetapModal").addEventListener("click", closeImportMenuTetapModal);
    $("#btnCancelImportMenuTetapModal").addEventListener("click", closeImportMenuTetapModal);
    $("#importMenuTetapModalOverlay").addEventListener("click", (e) => {
      if (e.target.id === "importMenuTetapModalOverlay") closeImportMenuTetapModal();
    });
    $("#importMenuTetapForm").addEventListener("submit", submitImportMenuTetapForm);
  }

  function closeImportMenuTetapModal() {
    $("#importMenuTetapModalOverlay").hidden = true;
  }

  async function submitImportMenuTetapForm(e) {
    e.preventDefault();
    const fileInput = $("#importMenuTetapFile");
    if (!fileInput.files.length) return;
    const fd = new FormData();
    fd.append("file_csv", fileInput.files[0]);
    const resultBox = $("#importMenuTetapResult");
    try {
      const res = await fetch("/api/menu-tetap/import", { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error((data.errors || [data.error]).join(", "));
      resultBox.hidden = false;
      resultBox.className = "form-note";
      resultBox.textContent = `${data.sukses} data berhasil diimpor.` +
        (data.gagal.length ? `\n${data.gagal.length} baris gagal:\n` + data.gagal.slice(0, 8).join("\n") : "");
      loadMenuTetapList();
    } catch (err) {
      resultBox.hidden = false;
      resultBox.className = "form-error";
      resultBox.textContent = "Gagal import: " + err.message;
    }
  }

  let menuTetapCache = [];

  async function loadMenuTetapList() {
    const q = $("#menuTetapSearch").value.trim();
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    try {
      const res = await fetch("/api/menu-tetap?" + params.toString());
      const data = await res.json();
      menuTetapCache = data;
      renderMenuTetapTable(data);
    } catch (err) {
      console.error(err);
    }
  }

  function renderMenuTetapTable(rows) {
    const tbody = $("#menuTetapTableBody");
    if (!rows.length) {
      tbody.innerHTML = `<tr class="empty-row"><td colspan="8">Belum ada data.</td></tr>`;
      return;
    }
    tbody.innerHTML = rows.map((m) => `
      <tr>
        <td style="font-weight:600;">
          ${m.nama}
          ${m.is_aktif ? '<span class="badge badge--ok" style="margin-left:8px;">dipakai optimasi</span>' : ""}
        </td>
        <td class="num">${m.berat != null ? Number(m.berat).toFixed(0) : "-"}</td>
        <td class="num">${Number(m.energi).toFixed(1)}</td>
        <td class="num">${Number(m.protein).toFixed(1)}</td>
        <td class="num">${Number(m.lemak).toFixed(1)}</td>
        <td class="num">${Number(m.karbo).toFixed(1)}</td>
        <td>
          ${m.is_aktif
            ? '<span class="badge badge--ok">Aktif</span>'
            : `<button class="btn-secondary" style="padding:4px 10px;font-size:12px;" onclick="window.__aktifkanMenuTetap(${m.id_menutetap})">Jadikan Aktif</button>`}
        </td>
        <td>
          <div class="row-actions">
            <button class="icon-btn" title="Edit" onclick="window.__editMenuTetap(${m.id_menutetap})">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M4 20L4.5 16.5L16 5L19 8L7.5 19.5L4 20Z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>
            </button>
            <button class="icon-btn danger" title="Hapus" onclick="window.__deleteMenuTetap(${m.id_menutetap}, '${m.nama.replace(/'/g, "\\'")}')">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M5 7H19M9 7V5C9 4 9.8 3 11 3H13C14.2 3 15 4 15 5V7M17 7L16.3 19C16.2 20.1 15.3 21 14.2 21H9.8C8.7 21 7.8 20.1 7.7 19L7 7" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </button>
          </div>
        </td>
      </tr>
    `).join("");
  }

  window.__aktifkanMenuTetap = async (id) => {
    try {
      const res = await fetch(`/api/menu-tetap/${id}/aktifkan`, { method: "POST" });
      const data = await res.json();
      if (!res.ok) throw new Error((data.errors || ["Gagal mengaktifkan"]).join("\n"));
      loadMenuTetapList();
    } catch (err) {
      alert(err.message);
    }
  };

  function openMenuTetapModal(data) {
    $("#menuTetapModalTitle").textContent = data ? "Edit Menu Tetap" : "Tambah Menu Tetap";
    $("#menuTetapId").value = data ? data.id_menutetap : "";
    $("#menuTetapNama").value = data ? data.nama : "";
    $("#menuTetapBerat").value = data && data.berat != null ? data.berat : "";
    $("#menuTetapEnergi").value = data ? data.energi : "";
    $("#menuTetapProtein").value = data ? data.protein : "";
    $("#menuTetapLemak").value = data ? data.lemak : "";
    $("#menuTetapKarbo").value = data ? data.karbo : "";
    $("#menuTetapFormError").hidden = true;
    $("#menuTetapModalOverlay").hidden = false;
  }

  function closeMenuTetapModal() {
    $("#menuTetapModalOverlay").hidden = true;
  }

  async function submitMenuTetapForm(e) {
    e.preventDefault();
    const id = $("#menuTetapId").value;
    const beratVal = $("#menuTetapBerat").value;
    const payload = {
      nama: $("#menuTetapNama").value.trim(),
      berat: beratVal === "" ? null : Number(beratVal),
      energi: Number($("#menuTetapEnergi").value),
      protein: Number($("#menuTetapProtein").value),
      lemak: Number($("#menuTetapLemak").value),
      karbo: Number($("#menuTetapKarbo").value),
    };
    const errBox = $("#menuTetapFormError");
    try {
      const url = id ? `/api/menu-tetap/${id}` : "/api/menu-tetap";
      const res = await fetch(url, {
        method: id ? "PUT" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) throw new Error((data.errors || ["Gagal menyimpan"]).join("\n"));
      closeMenuTetapModal();
      loadMenuTetapList();
    } catch (err) {
      errBox.hidden = false;
      errBox.textContent = err.message;
    }
  }

  window.__editMenuTetap = (id) => {
    const item = menuTetapCache.find((m) => m.id_menutetap === id);
    if (item) openMenuTetapModal(item);
  };

  window.__deleteMenuTetap = async (id, nama) => {
    if (!confirm(`Hapus "${nama}"?`)) return;
    try {
      const res = await fetch(`/api/menu-tetap/${id}`, { method: "DELETE" });
      const data = await res.json();
      if (!res.ok) throw new Error((data.errors || ["Gagal menghapus"]).join("\n"));
      loadMenuTetapList();
    } catch (err) {
      alert(err.message);
    }
  };

  // ======================================================================
  // TARGET GIZI
  // ======================================================================
  const TARGET_ROWS = [
    ["energi", "Energi", "kkal"],
    ["protein", "Protein", "g"],
    ["lemak", "Lemak", "g"],
    ["karbo", "Karbohidrat", "g"],
  ];

  function bindTargetView() {
    $("#targetGiziForm").addEventListener("submit", submitTargetGizi);
  }

  async function loadTargetGizi() {
    try {
      const res = await fetch("/api/target-gizi");
      const data = await res.json();
      renderTargetForm(data.aktif);
      renderTargetRiwayat(data.riwayat);
    } catch (err) {
      console.error(err);
    }
  }

  function renderTargetForm(aktif) {
    const grid = $("#targetGiziGrid");
    grid.innerHTML = TARGET_ROWS.map(([key, label, unit]) => `
      <div class="target-row">
        <div class="nutrient-name">${label} <span style="color:var(--ink-faint); font-weight:500;">(${unit})</span></div>
        <div>
          <label class="mini-label">Batas Bawah</label>
          <input type="number" step="0.01" min="0" class="text-input" style="width:100%;"
                 id="target_${key}_min" value="${aktif[key + "_min"]}" required>
        </div>
        <div>
          <label class="mini-label">Batas Atas</label>
          <input type="number" step="0.01" min="0" class="text-input" style="width:100%;"
                 id="target_${key}_max" value="${aktif[key + "_max"]}" required>
        </div>
      </div>
    `).join("");
    $("#targetSumber").value = aktif.sumber;
  }

  function renderTargetRiwayat(rows) {
    const tbody = $("#targetRiwayatBody");
    tbody.innerHTML = rows.map((t) => `
      <tr>
        <td style="font-size:.76rem;">#${t.id_targetgizi}</td>
        <td class="num" style="font-size:.76rem;">${t.energi_min}-${t.energi_max}</td>
        <td class="num" style="font-size:.76rem;">${t.protein_min}-${t.protein_max}</td>
        <td class="num" style="font-size:.76rem;">${t.lemak_min}-${t.lemak_max}</td>
        <td class="num" style="font-size:.76rem;">${t.karbo_min}-${t.karbo_max}</td>
      </tr>
    `).join("");
  }

  async function submitTargetGizi(e) {
    e.preventDefault();
    const payload = { sumber: $("#targetSumber").value.trim() };
    TARGET_ROWS.forEach(([key]) => {
      payload[key + "_min"] = Number($(`#target_${key}_min`).value);
      payload[key + "_max"] = Number($(`#target_${key}_max`).value);
    });
    try {
      const res = await fetch("/api/target-gizi", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) throw new Error((data.errors || ["Gagal menyimpan"]).join("\n"));
      loadTargetGizi();
      alert("Target gizi berhasil disimpan.");
    } catch (err) {
      alert(err.message);
    }
  }

  // ======================================================================
  // RIWAYAT
  // ======================================================================
  function bindRiwayatView() {
    $("#btnTutupDetailRiwayat").addEventListener("click", () => {
      $("#riwayatDetailPanel").hidden = true;
    });
  }

  async function loadRiwayatList() {
    try {
      const res = await fetch("/api/riwayat");
      const data = await res.json();
      renderRiwayatTable(data);
    } catch (err) {
      console.error(err);
    }
  }

  function renderRiwayatTable(rows) {
    const tbody = $("#riwayatTableBody");
    if (!rows.length) {
      tbody.innerHTML = `<tr class="empty-row"><td colspan="8">Belum ada riwayat optimasi.</td></tr>`;
      return;
    }
    tbody.innerHTML = rows.map((r) => `
      <tr>
        <td class="mono">#${r.id_hasil}</td>
        <td style="font-size:.8rem;">${new Date(r.tanggal).toLocaleString("id-ID")}</td>
        <td class="num">${r.population_size}</td>
        <td class="num">${r.generation}</td>
        <td class="num">${r.f1_terbaik ?? "-"}</td>
        <td class="num">${r.f2_terbaik ?? "-"}</td>
        <td><span class="status-chip ${r.status}">${r.status}</span></td>
        <td>
          ${r.status === "selesai"
            ? `<button class="btn-secondary btn-secondary--sm" onclick="window.__lihatRiwayat(${r.id_hasil})">Lihat</button>`
            : ""}
        </td>
      </tr>
    `).join("");
  }

  window.__lihatRiwayat = async (id) => {
    try {
      const res = await fetch(`/api/riwayat/${id}`);
      const data = await res.json();
      $("#btnExportRiwayat").href = `/api/riwayat/${id}/export`;
      renderRiwayatDetail(id, data.detail);
    } catch (err) {
      alert("Gagal memuat detail riwayat.");
    }
  };

  function renderRiwayatDetail(id, detailRows) {
    $("#riwayatDetailId").textContent = id;
    const grid = $("#riwayatTrayGrid");
    grid.innerHTML = detailRows.map((d) => {
      const allOk = !!d.gizi_terpenuhi;
      return `
        <div class="tray">
          <div class="tray__head">
            <span class="tray__day">Hari ${d.hari}</span>
            <span class="tray__status ${allOk ? "ok" : "warn"}">${allOk ? "Gizi Terpenuhi" : "Perlu Ditinjau"}</span>
          </div>
          <div class="tray__compartments">
            ${riwayatCompartment("pokok", d.pokok_nama, d.pokok_berat)}
            ${riwayatCompartment("lauk", d.lauk_nama, d.lauk_berat)}
            ${riwayatCompartment("sayur", d.sayur_nama, d.sayur_berat)}
            ${riwayatCompartment("buah", d.buah_nama, d.buah_berat)}
          </div>
          <div class="tray__milk">
            <span class="compartment__icon">${ICONS.susu}</span>
            <span>${d.susu_nama || "Menu tetap"} <em style="color:var(--ink-faint); font-style:normal;">(tetap)</em></span>
          </div>
          <div class="tray__nutrients">
            <div class="nut-cell"><div class="nut-cell__label">Energi</div><div class="nut-cell__value">${d.energi}</div></div>
            <div class="nut-cell"><div class="nut-cell__label">Protein</div><div class="nut-cell__value">${d.protein}</div></div>
            <div class="nut-cell"><div class="nut-cell__label">Lemak</div><div class="nut-cell__value">${d.lemak}</div></div>
            <div class="nut-cell"><div class="nut-cell__label">Karbo</div><div class="nut-cell__value">${d.karbo}</div></div>
          </div>
        </div>`;
    }).join("");
    $("#riwayatDetailPanel").hidden = false;
    $("#riwayatDetailPanel").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function riwayatCompartment(cat, nama, berat) {
    const beratHtml = berat != null
      ? `<span class="compartment__meta">${Number(berat).toFixed(0)}&nbsp;g</span>`
      : "";
    return `
      <div class="compartment compartment--${cat}">
        <span class="compartment__icon">${ICONS[cat]}</span>
        <span class="compartment__body">
          <span class="compartment__label">${cat}</span>
          <span class="compartment__name">${nama}</span>
          ${beratHtml}
        </span>
      </div>`;
  }

  document.addEventListener("DOMContentLoaded", init);
})();
