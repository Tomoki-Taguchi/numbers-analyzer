/* ============================================================
   NUMBERS ANALYZER - front-end
   analysis_numbers{3,4}.json を読み込み、各タブを描画する。
   ============================================================ */

const state = {
  game: "numbers3",
  data: null,
  periodKey: "all",
  activeTab: "prediction",
  charts: {},
  allReasons: false, // true のとき全候補の選出根拠を一括表示
};

const MODE_ORDER = ["balanced", "frequency_heavy", "recent_heavy", "pull_heavy", "cycle_heavy", "ml_heavy", "sum_target"];

// ---- helpers ----
function isN4() { return state.game === "numbers4"; }
function el(id) { return document.getElementById(id); }

function digitBadge(d, big) {
  const cls = ["digit", isN4() ? "n4" : "", big ? "big" : ""].filter(Boolean).join(" ");
  return `<span class="${cls}">${d}</span>`;
}

function numberBadges(digits, big) {
  return `<div class="number-str">${digits.map(d => digitBadge(d, big)).join("")}</div>`;
}

function heatColor(v, lo, hi) {
  // lo..hi を 青(cold) -> 中立 -> 赤(hot) に写像
  if (hi - lo < 1e-9) return "rgba(200,200,200,0.12)";
  const t = (v - lo) / (hi - lo); // 0..1
  if (t < 0.5) {
    const a = (0.5 - t) * 2; // cold強度
    return `rgba(87,176,165,${0.10 + a * 0.45})`;
  }
  const a = (t - 0.5) * 2; // hot強度
  return `rgba(224,138,122,${0.10 + a * 0.45})`;
}

function destroyChart(key) {
  if (state.charts[key]) { state.charts[key].destroy(); delete state.charts[key]; }
}

function period() { return state.data.periods[state.periodKey]; }
function positions() { return state.data.position_labels; }

// ---- load / init ----
async function loadGame(game) {
  state.game = game;
  document.querySelectorAll(".game-btn").forEach(b => b.classList.toggle("active", b.dataset.game === game));
  el("main").style.opacity = "0.4";
  try {
    const res = await fetch(`data/analysis_${game}.json?t=${Date.now()}`);
    state.data = await res.json();
  } catch (e) {
    el("predictionResult").innerHTML = `<div class="loading">データを読み込めませんでした: ${e}</div>`;
    return;
  }
  el("main").style.opacity = "1";
  // デフォルト期間 = all（末尾）
  state.periodKey = "all";
  buildPeriodSlider();
  renderStatsBar();
  el("dataSource").textContent = `データ元: 楽天×宝くじ ｜ 最終更新: ${state.data.last_updated} ｜ 第${state.data.latest_round}回まで`;
  renderCurrent();
}

function buildPeriodSlider() {
  const labels = state.data.period_labels; // [直近100..1000, all]
  const slider = el("periodSlider");
  slider.min = 0;
  slider.max = labels.length - 1;
  slider.value = labels.length - 1; // all
  slider.oninput = () => {
    state.periodKey = labels[+slider.value].key;
    updatePeriodDisplay();
    renderCurrent();
  };
  updatePeriodDisplay();
}

function updatePeriodDisplay() {
  const labels = state.data.period_labels;
  const idx = labels.findIndex(l => l.key === state.periodKey);
  const l = labels[idx >= 0 ? idx : labels.length - 1];
  el("periodSlider").value = idx >= 0 ? idx : labels.length - 1;
  el("periodDisplay").textContent = `${l.label}（${l.range} / ${l.draws}回）`;
}

function renderStatsBar() {
  const d = state.data;
  el("statsBar").innerHTML = `
    <div>ゲーム <span>${d.game === "numbers4" ? "ナンバーズ4" : "ナンバーズ3"}</span></div>
    <div>総回数 <span>${d.periods.all.summary_stats.total_draws}</span></div>
    <div>最新 <span>第${d.latest_round}回</span></div>
    <div>次回予想 <span>第${d.latest_round + 1}回</span></div>`;
}

// ---- tab switching ----
function switchTab(name) {
  state.activeTab = name;
  document.querySelectorAll(".tab").forEach(t => t.classList.toggle("active", t.dataset.tab === name));
  document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
  el(`tab-${name}`).classList.add("active");
  renderCurrent();
}

function renderCurrent() {
  if (!state.data) return;
  const map = {
    prediction: renderPrediction, frequency: renderFrequency, grid: renderGrid,
    pull: renderPull, sum: renderSum, shape: renderShape, recent: renderRecent,
    weekday: renderWeekday, montecarlo: renderMonteCarlo, stats: renderStats,
  };
  (map[state.activeTab] || (() => {}))();
}

// ---- AI予想 ----
// 予想カード（候補10点＋根拠パネル）を組み立てる。src は 'period' か 'wd'。
function predCardHtml(src, mk, p) {
  const mc = p.monte_carlo || {};
  const cands = p.candidates || [{ number_str: p.number_str, sum: p.metrics.sum, shape: p.metrics.shape, pull_count: 0 }];
  const cardHtml = cands.map((c, i) => {
    const pull = c.pull_count > 0 ? `<span class="pull-tag" title="引っ張り${c.pull_count}箇所">⚡${c.pull_count}</span>` : "";
    return `<div class="cand ${i === 0 ? "top" : ""}" onclick="showReasons('${src}','${mk}',${i})" id="cand-${src}-${mk}-${i}">
      <span class="cand-rank">${i + 1}</span>
      <span class="cand-num">${c.number_str}</span>
      <span class="cand-meta">計${c.sum}・${c.shape}${pull}</span>
    </div>`;
  }).join("");
  const conf = [];
  if (mc.straight_pct != null && mc.straight_pct > 0) conf.push(`#1 ストレート ${mc.straight_pct}%`);
  if (mc.box_pct != null && mc.box_pct > 0) conf.push(`ボックス ${mc.box_pct}%`);
  if (mc.mini_pct != null && mc.mini_pct > 0) conf.push(`ミニ ${mc.mini_pct}%`);
  const tsum = p.metrics.target_sum ? ` ｜ 目標合計帯 ${p.metrics.target_sum}` : "";
  const weakNote = mk === "pull_heavy" ? '<span class="pill" style="color:var(--hot)">参考（記憶なしゲームでは当たりにくい）</span>' : "";
  return `<div class="pred-card">
    <div class="pred-head">
      <span class="pred-mode">${p.mode_name} ${weakNote}</span>
      <span class="pred-head-r">
        <span class="pred-conf">${conf.join(" ／ ")}${tsum}</span>
        <button class="copy-btn" onclick="copyModeReasons('${src}','${mk}',this)" title="この予想と選出根拠をコピー">📋 コピー</button>
      </span>
    </div>
    <div class="cand-grid">${cardHtml}</div>
    <div class="cand-reasons" id="reasons-${src}-${mk}"></div>
  </div>`;
}

function _predBySource(src, mk) {
  if (src === "wd") return state.data.weekday_predictions && state.data.weekday_predictions.predictions[mk];
  return period().predictions[mk];
}

function renderPrediction() {
  const preds = period().predictions;
  let html = `<div class="card"><h3>🤖 第${state.data.latest_round + 1}回 予想（${el("periodDisplay").textContent}）</h3>
    <p class="note">各モードが重視する指標で候補を10点ずつ提示します（#1＝最有力）。<strong>「全候補の選出根拠を表示」ボタン</strong>で全数字の根拠を一括表示、または候補をクリックで1件だけ表示できます。⚡は前回と同じ位置に同じ数字が出る「引っ張り」を含む候補。ナンバーズは各位0-9がほぼ一様なので引っ張りは平均約1/3の頻度で自然に現れます。</p>
    ${reasonsToggleBtn()}</div>`;
  for (const mk of MODE_ORDER) {
    if (preds[mk]) html += predCardHtml("period", mk, preds[mk]);
  }
  el("predictionResult").innerHTML = html;
  applyReasons("period", preds);
}

const REASON_FACTOR = { freq: "頻度", recent: "直近", drought: "未出", pull: "引っ張り", cycle: "周期", rf: "RF", lstm: "LSTM" };

// 1候補分の各位選出根拠リスト（<ul>）を組み立てる
function reasonRowsHtml(pred, cand) {
  const table = pred.digit_reasons || [];
  const rows = (cand.digits || []).map((d, p) => {
    const entry = (table[p] && table[p].digits[String(d)]) || {};
    const tag = REASON_FACTOR[entry.top_factor] || "";
    return `<li><span class="rz-pos">${(table[p] && table[p].label) || ""}</span>
      <span class="rz-tag">${tag}</span> ${entry.text || ""}</li>`;
  }).join("");
  return `<ul class="reason-list">${rows}</ul>`;
}

// 候補クリックで、その数字1件の各位の選出根拠を表示（src: 'period' | 'wd'）
function showReasons(src, mk, idx) {
  if (state.allReasons) return; // 全表示中はクリックで折りたたまない
  const pred = _predBySource(src, mk);
  if (!pred) return;
  const cand = (pred.candidates || [])[idx];
  if (!cand) return;
  const pullNote = cand.pull_count > 0 ? ` ⚡引っ張り${cand.pull_count}箇所` : "";
  const panel = el(`reasons-${src}-${mk}`);
  if (!panel) return;
  panel.innerHTML = `<div class="reasons-head">「${cand.number_str}」の選出根拠${pullNote}</div>${reasonRowsHtml(pred, cand)}`;
  const grid = panel.previousElementSibling;
  if (grid) grid.querySelectorAll(".cand").forEach((c, i) => c.classList.toggle("selected", i === idx));
}

// 「選出根拠」ボタン: そのモードの全候補（10点）の根拠をまとめて表示
function renderAllReasons(src, mk) {
  const pred = _predBySource(src, mk);
  if (!pred) return;
  const panel = el(`reasons-${src}-${mk}`);
  if (!panel) return;
  panel.innerHTML = (pred.candidates || []).map((cand, i) => {
    const pullNote = cand.pull_count > 0 ? ` ⚡引っ張り${cand.pull_count}箇所` : "";
    return `<div class="reasons-block">
      <div class="reasons-head">${i + 1}位「${cand.number_str}」の選出根拠${pullNote}</div>
      ${reasonRowsHtml(pred, cand)}</div>`;
  }).join("");
  const grid = panel.previousElementSibling;
  if (grid) grid.querySelectorAll(".cand").forEach(c => c.classList.remove("selected"));
}

// セクション（'period' | 'wd'）内の全カードの根拠表示を現在の状態に合わせる
function applyReasons(src, preds) {
  for (const mk of MODE_ORDER) {
    if (!preds[mk]) continue;
    if (state.allReasons) renderAllReasons(src, mk);
    else showReasons(src, mk, 0);
  }
}

// 全候補根拠の一括表示 ⇄ 個別表示 を切り替える
function toggleAllReasons() {
  state.allReasons = !state.allReasons;
  renderCurrent();
}

// 一括表示トグルボタンのHTML
function reasonsToggleBtn() {
  const label = state.allReasons ? "🔽 選出根拠をたたむ" : "📖 全候補の選出根拠を表示";
  return `<button class="reasons-toggle ${state.allReasons ? "on" : ""}" onclick="toggleAllReasons()">${label}</button>`;
}

// ---- コピー ----
// そのモードの全候補（番号＋各位の選出根拠）を整形テキストにする
function buildModeCopyText(src, mk) {
  const pred = _predBySource(src, mk);
  if (!pred) return "";
  const round = state.data.latest_round + 1;
  const table = pred.digit_reasons || [];
  const lines = [`【第${round}回】${pred.mode_name}`];
  (pred.candidates || []).forEach((cand, i) => {
    const pull = cand.pull_count > 0 ? ` ⚡引${cand.pull_count}` : "";
    lines.push(`${i + 1}位 ${cand.number_str} 計${cand.sum}/${cand.shape}${pull}`);
    (cand.digits || []).forEach((d, p) => {
      const entry = (table[p] && table[p].digits[String(d)]) || {};
      const tag = REASON_FACTOR[entry.top_factor] || "";
      const label = (table[p] && table[p].label) || "";
      lines.push(` ${label}｜${tag}: ${entry.text || ""}`);
    });
  });
  return lines.join("\n");
}

// クリップボードにコピー（secure context優先、失敗時はtextareaでフォールバック）
async function copyModeReasons(src, mk, btn) {
  const text = buildModeCopyText(src, mk);
  let ok = false;
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      ok = true;
    } else {
      ok = fallbackCopy(text);
    }
  } catch (e) {
    ok = fallbackCopy(text);
  }
  flashCopyBtn(btn, ok ? "✅ コピーしました" : "⚠️ コピー失敗");
}

function fallbackCopy(text) {
  try {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.top = "-9999px";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(ta);
    return ok;
  } catch (e) {
    return false;
  }
}

// ボタン文言を一時的に切り替えてフィードバック
function flashCopyBtn(btn, msg) {
  if (!btn) return;
  const orig = btn.dataset.orig || btn.textContent;
  btn.dataset.orig = orig;
  btn.textContent = msg;
  btn.classList.add("copied");
  setTimeout(() => {
    btn.textContent = btn.dataset.orig || "📋 コピー";
    btn.classList.remove("copied");
  }, 1500);
}

// ---- 各位頻度 ----
function renderFrequency() {
  const freq = period().frequency.per_position;
  const pos = positions();
  let html = "";
  for (let p = 0; p < pos.length; p++) {
    const f = freq[String(p)];
    const counts = Object.values(f.counts).map(Number);
    const lo = Math.min(...counts), hi = Math.max(...counts);
    const cells = [];
    for (let d = 0; d < 10; d++) {
      const c = f.counts[String(d)];
      const pct = f.percentages[String(d)];
      const dr = f.drought[String(d)];
      cells.push(`<div class="digit-cell" style="background:${heatColor(c, lo, hi)}" title="未出 ${dr}回">
        <div class="dnum">${d}</div><div class="dcnt">${c}回</div><div class="dcnt">${pct}%</div></div>`);
    }
    html += `<div class="card">
      <h3>${f && pos[p]} <span class="pill">ホット ${f.hot.join(" ")} ／ コールド ${f.cold.join(" ")}</span></h3>
      <div class="digit-grid">${cells.join("")}</div>
    </div>`;
  }
  el("frequencyResult").innerHTML = html;
}

// ---- 出目表 ----
function renderGrid() {
  const g = period().appearance_grid;
  const freq = period().frequency.per_position;
  const pos = positions();
  // ヘッダー
  let head = "<tr><th>位＼数字</th>" + Array.from({ length: 10 }, (_, d) => `<th>${d}</th>`).join("") + "<th>ホット</th><th>コールド</th></tr>";
  let rows = "";
  for (let p = 0; p < pos.length; p++) {
    const counts = Object.values(g.grid[String(p)]).map(Number);
    const lo = Math.min(...counts), hi = Math.max(...counts);
    let cells = "";
    for (let d = 0; d < 10; d++) {
      const c = g.grid[String(p)][String(d)];
      cells += `<td style="background:${heatColor(c, lo, hi)}">${c}</td>`;
    }
    const f = freq[String(p)];
    rows += `<tr><th>${pos[p]}</th>${cells}<td class="mark">${f.hot.join(",")}</td><td style="color:var(--cold)">${f.cold.join(",")}</td></tr>`;
  }
  el("gridResult").innerHTML = `<div class="card">
    <h3>📋 出目表（${el("periodDisplay").textContent} ／ 全${g.total_draws}回）</h3>
    <p class="note">各位で0〜9が何回出たか。色が濃い赤ほど多く、青ほど少ない。</p>
    <div class="grid-wrap"><table class="appear-grid">${head}${rows}</table></div>
  </div>`;
}

// ---- 引っ張り ----
function renderPull() {
  const pull = period().pull;
  const pos = positions();
  const D = pos.length;
  // 分布バー
  let distBars = "";
  const distVals = Object.entries(pull.distribution);
  const maxd = Math.max(...distVals.map(([, v]) => v), 1);
  for (const [k, v] of distVals) {
    distBars += `<div class="bar-row"><span class="lbl">${k}箇所</span>
      <div class="bar-track"><div class="bar-fill" style="width:${v / maxd * 100}%"></div></div>
      <span class="val">${v}回</span></div>`;
  }
  let posBars = "";
  for (let p = 0; p < D; p++) {
    const r = pull.per_position_rate[String(p)] * 100;
    posBars += `<div class="bar-row"><span class="lbl">${pos[p]}</span>
      <div class="bar-track"><div class="bar-fill" style="width:${Math.min(100, r * 3)}%"></div></div>
      <span class="val">${r.toFixed(1)}%</span></div>`;
  }
  const recent = pull.recent_pulls.map(r => `<tr><td>第${r.round}回</td><td>${r.date}</td>
    <td>${r.digits.join("")}</td><td>${r.pull_count > 0 ? r.pulled_positions.map(i => pos[i]).join("・") : "—"}</td></tr>`).join("");
  el("pullResult").innerHTML = `
    <div class="metric-big">平均 ${pull.average} 箇所/回 が前回から引っ張り</div>
    <div class="two-col">
      <div class="card"><h3>引っ張り箇所数の分布</h3>${distBars}</div>
      <div class="card"><h3>各位の反復率（期待値≈10%）</h3>${posBars}</div>
    </div>
    <div class="card"><h3>直近の引っ張り状況</h3><div class="tbl-wrap"><table>
      <tr><th>回</th><th>日付</th><th>当選</th><th>引っ張り位置</th></tr>${recent}</table></div></div>`;
}

// ---- 合計値 ----
function renderSum() {
  const s = period().digit_sum;
  const dist = s.distribution;
  const labels = Object.keys(dist);
  const vals = Object.values(dist).map(Number);
  const bands = s.bands.map(b => `<tr><td>${b.band}</td><td>${b.count}回</td><td>${b.percentage}%</td></tr>`).join("");
  el("sumResult").innerHTML = `
    <div class="metric-big">平均合計 ${s.avg} ｜ 目安レンジ ${s.range[0]}〜${s.range[1]}</div>
    <div class="card"><h3>合計値の分布</h3><div class="chart-container"><canvas id="sumChart"></canvas></div></div>
    <div class="card"><h3>合計値帯 TOP10</h3><div class="tbl-wrap"><table>
      <tr><th>帯</th><th>回数</th><th>割合</th></tr>${bands}</table></div></div>`;
  destroyChart("sum");
  state.charts.sum = new Chart(el("sumChart"), {
    type: "bar",
    data: { labels, datasets: [{ label: "出現回数", data: vals, backgroundColor: isN4() ? "#7a86c4" : "#c49a3f" }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } },
      scales: { x: { title: { display: true, text: "合計値" } } } },
  });
}

// ---- 形 ----
function renderShape() {
  const sh = period().shape;
  const box = period().top_box_combos;
  const oe = Object.entries(sh.odd_even_dist).map(([k, v]) => `<tr><td>${k}</td><td>${v}回</td></tr>`).join("");
  const bs = Object.entries(sh.big_small_dist).map(([k, v]) => `<tr><td>${k}</td><td>${v}回</td></tr>`).join("");
  const boxRows = box.slice(0, 15).map(b => `<tr><td>${b.combo.join("")}</td><td>${b.count}回</td><td>${b.percentage}%</td></tr>`).join("");
  el("shapeResult").innerHTML = `
    <div class="card"><h3>形の割合</h3>
      <div class="bar-row"><span class="lbl">ゾロ目</span><div class="bar-track"><div class="bar-fill" style="width:${sh.zoro_rate * 100 * 8}%"></div></div><span class="val">${(sh.zoro_rate * 100).toFixed(2)}%</span></div>
      <div class="bar-row"><span class="lbl">連番</span><div class="bar-track"><div class="bar-fill" style="width:${sh.sequential_rate * 100 * 8}%"></div></div><span class="val">${(sh.sequential_rate * 100).toFixed(2)}%</span></div>
      <div class="bar-row"><span class="lbl">重複</span><div class="bar-track"><div class="bar-fill" style="width:${sh.repeat_rate * 100}%"></div></div><span class="val">${(sh.repeat_rate * 100).toFixed(1)}%</span></div>
    </div>
    <div class="two-col">
      <div class="card"><h3>奇数:偶数</h3><div class="tbl-wrap"><table><tr><th>比</th><th>回数</th></tr>${oe}</table></div></div>
      <div class="card"><h3>大(5-9):小(0-4)</h3><div class="tbl-wrap"><table><tr><th>比</th><th>回数</th></tr>${bs}</table></div></div>
    </div>
    <div class="card"><h3>ボックス組合せ TOP15</h3><div class="tbl-wrap"><table>
      <tr><th>組合せ</th><th>回数</th><th>割合</th></tr>${boxRows}</table></div></div>`;
}

// ---- 直近結果 ----
function renderRecent() {
  const recent = period().recent_draws;
  const rows = recent.map(r => `<tr><td>第${r.round}回</td><td>${r.date}</td>
    <td>${numberBadges(r.digits)}</td><td>${r.sum}</td><td>${r.odd_even}</td><td>${r.shape}</td></tr>`).join("");
  el("recentResult").innerHTML = `<h3>直近の抽選結果（${el("periodDisplay").textContent}）</h3>
    <table><tr><th>回</th><th>日付</th><th>当選番号</th><th>合計</th><th>奇偶</th><th>形</th></tr>${rows}</table>`;
}

// ---- 曜日 ----
function renderWeekday() {
  const w = state.data.weekday;
  if (!w || !w.weekdays) { el("weekdayResult").innerHTML = '<div class="card"><p class="note">曜日データがありません。</p></div>'; return; }
  const wds = w.weekdays;
  const order = ["0", "1", "2", "3", "4"]; // 月〜金
  const next = w.next_weekday != null ? String(w.next_weekday) : null;

  const vals = [];
  order.forEach(k => { if (wds[k]) for (let d = 0; d < 10; d++) vals.push(wds[k].overall[String(d)]); });
  const lo = Math.min(...vals), hi = Math.max(...vals);

  const head = "<tr><th>曜日＼数字</th>" + Array.from({ length: 10 }, (_, d) => `<th>${d}</th>`).join("") + "<th>件数</th><th>平均合計</th><th>引っ張り率</th><th>ホット</th></tr>";
  let rows = "";
  order.forEach(k => {
    const wd = wds[k]; if (!wd) return;
    const isNext = k === next;
    let cells = "";
    for (let d = 0; d < 10; d++) { const v = wd.overall[String(d)]; cells += `<td style="background:${heatColor(v, lo, hi)}">${v}</td>`; }
    rows += `<tr class="${isNext ? "wd-next" : ""}"><th>${wd.label}${isNext ? " ⭐" : ""}</th>${cells}<td>${wd.count}</td><td>${wd.avg_sum}</td><td>${(wd.pull_average).toFixed(2)}</td><td class="mark">${wd.hot.join(",")}</td></tr>`;
  });

  // 次回曜日の各位ホット
  let nextHtml = "";
  if (next && wds[next]) {
    const wd = wds[next];
    const posHtml = positions().map((lab, p) => {
      const pp = wd.per_position[String(p)];
      const ranked = Object.entries(pp).sort((a, b) => b[1] - a[1]).slice(0, 3);
      return `<div class="pos-cell"><div class="plabel">${lab}</div>${digitBadge(+ranked[0][0])}
        <div class="cands">出やすい: ${ranked.map(([d, v]) => `${d}(${v}%)`).join(" ")}</div></div>`;
    }).join("");
    nextHtml = `<div class="card"><h3>⭐ 次回抽選【${wd.label}曜】に出やすい数字（全期間）</h3>
      <p class="note">${wd.label}曜の全${wd.count}回で、各位のホット数字（差はほぼ揺らぎです）。</p>
      <div class="pos-row">${posHtml}</div></div>`;
  }

  // 曜日別 平均合計・引っ張り率の比較バー
  const sums = order.map(k => wds[k] ? wds[k].avg_sum : 0);
  const pulls = order.map(k => wds[k] ? wds[k].pull_average : 0);
  const smax = Math.max(...sums, 1), pmax = Math.max(...pulls, 0.001);
  const cmpRows = order.map(k => {
    const wd = wds[k]; if (!wd) return "";
    const isNext = k === next;
    return `<div class="bar-row"><span class="lbl">${wd.label}${isNext ? "⭐" : ""}</span>
      <div class="bar-track"><div class="bar-fill" style="width:${wd.avg_sum / smax * 100}%"></div></div>
      <span class="val">合計${wd.avg_sum}</span>
      <div class="bar-track"><div class="bar-fill" style="width:${wd.pull_average / pmax * 100}%;background:var(--cold)"></div></div>
      <span class="val">引${wd.pull_average.toFixed(2)}</span></div>`;
  }).join("");
  const cmpHtml = `<div class="card"><h3>📊 曜日別 平均合計・引っ張り率</h3>
    <p class="note">左=平均合計、右(青)=1回あたりの引っ張り位置数。引っ張りの基準は各位≈10%（${positions().length}桁で約${(positions().length * 0.1).toFixed(1)}）。</p>
    ${cmpRows}</div>`;

  // 次回曜日の合計値分布チャート
  let sumChartHtml = "";
  if (next && wds[next] && wds[next].sum_distribution) {
    sumChartHtml = `<div class="card"><h3>📈【${wds[next].label}曜】の合計値分布（${wds[next].count}回）</h3>
      <p class="note">平均${wds[next].avg_sum}・ばらつき±${wds[next].sum_std}。</p>
      <div class="chart-container chart-small"><canvas id="wdSumChart"></canvas></div></div>`;
  }

  // 曜日専用予想
  const wp = state.data.weekday_predictions;
  let predHtml = "";
  if (wp && wp.predictions) {
    predHtml = `<div class="card"><h3>🤖⭐【${wp.label}曜】専用AI予想（${wp.count}回のデータのみ）</h3>
      <p class="note">次回抽選の曜日のデータだけで算出した「出し分け」予想です。各モード10点・<strong>「全候補の選出根拠を表示」ボタン</strong>または候補クリックで根拠。差はほぼ揺らぎですが読み物としてどうぞ。</p>
      ${reasonsToggleBtn()}</div>`;
    for (const mk of MODE_ORDER) { if (wp.predictions[mk]) predHtml += predCardHtml("wd", mk, wp.predictions[mk]); }
  }

  el("weekdayResult").innerHTML = `
    ${nextHtml}
    ${predHtml}
    <div class="card"><h3>📅 曜日別 数字の出やすさ（全期間 ${w.total_draws}回）</h3>
      <p class="note">${next && wds[next] ? `次回抽選は【${wds[next].label}曜】⭐ ｜ ` : ""}各曜日で0〜9の出現率(%)。赤いほど多く・青いほど少ない。本来は各10%（公平なくじ）。</p>
      <div class="grid-wrap"><table class="appear-grid">${head}${rows}</table></div></div>
    ${cmpHtml}
    ${sumChartHtml}`;

  // 曜日専用予想の根拠を初期表示
  if (wp && wp.predictions) applyReasons("wd", wp.predictions);

  // 合計値チャート描画
  if (next && wds[next] && wds[next].sum_distribution) {
    destroyChart("wdSum");
    const dist = wds[next].sum_distribution;
    state.charts.wdSum = new Chart(el("wdSumChart"), {
      type: "bar",
      data: { labels: Object.keys(dist), datasets: [{ data: Object.values(dist).map(Number), backgroundColor: isN4() ? "#7a86c4" : "#c49a3f" }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { title: { display: true, text: "合計値" } } } },
    });
  }
}

// ---- モンテカルロ ----
function renderMonteCarlo() {
  const p = period().predictions.balanced;
  const mc = p.monte_carlo;
  const pos = positions();
  let html = `<div class="card"><h3>総合予想 ${p.number_str} の信頼度</h3>
    <p class="note">ストレート ${mc.straight_pct}% ／ ボックス ${mc.box_pct}%${mc.mini_pct != null ? ` ／ ミニ ${mc.mini_pct}%` : ""}</p></div>`;
  for (let pi = 0; pi < pos.length; pi++) {
    const per = mc.per_position[String(pi)];
    if (!per) continue;
    const vals = Object.values(per).map(Number);
    const lo = Math.min(...vals), hi = Math.max(...vals);
    let cells = "";
    for (let d = 0; d < 10; d++) {
      const v = per[String(d)];
      cells += `<div class="digit-cell" style="background:${heatColor(v, lo, hi)}"><div class="dnum">${d}</div><div class="dcnt">${v}%</div></div>`;
    }
    html += `<div class="card"><h3>${pos[pi]}</h3><div class="digit-grid">${cells}</div></div>`;
  }
  el("mcResult").innerHTML = html;
}

// ---- 成績 ----
function renderStats() {
  const bt = state.data.backtest;
  const rb = bt.random_baseline;
  const modeNames = { balanced: "総合", frequency_heavy: "頻度", recent_heavy: "直近", pull_heavy: "引っ張り", cycle_heavy: "周期", sum_target: "合計値" };
  const btRows = Object.entries(bt.modes).map(([mk, m]) => `<tr>
    <td>${modeNames[mk] || mk}</td><td>${m.straight_rate}%</td><td>${m.box_rate}%</td><td>${m.set_rate}%</td>
    ${isN4() ? "" : `<td>${m.mini_rate != null ? m.mini_rate + "%" : "—"}</td>`}</tr>`).join("");
  const straightBase = (rb.straight_prob * 100).toFixed(isN4() ? 2 : 1);

  // アーカイブ実成績
  const ms = state.data.mode_stats;
  let archiveHtml = "";
  const allStats = (ms.by_period && ms.by_period.all) || null;
  const totalAll = (ms.total_by_period && ms.total_by_period.all) || 0;
  if (allStats && totalAll > 0) {
    const rows = MODE_ORDER.filter(mk => allStats[mk]).map(mk => {
      const a = allStats[mk];
      return `<tr><td>${a.mode_name}</td><td>${a.total}</td><td>${a.straight}</td><td>${a.box}</td><td>${a.set}</td><td>${a.straight_rate}%</td></tr>`;
    }).join("");
    archiveHtml = `<div class="card"><h3>📁 アーカイブ実成績（全期間モード・答え合わせ済み ${totalAll}回）</h3>
      <div class="tbl-wrap"><table><tr><th>モード</th><th>検証</th><th>ストレート</th><th>ボックス</th><th>セット</th><th>ストレート率</th></tr>${rows}</table></div>
      <p class="note">実運用でAIを含む全モードの成績が抽選ごとに蓄積されます。</p></div>`;
  } else {
    archiveHtml = `<div class="card"><h3>📁 アーカイブ実成績</h3>
      <p class="note">まだ答え合わせデータがありません。次回抽選以降、AIを含む全モードの予想と結果が自動で蓄積されます。</p></div>`;
  }

  el("statsResult").innerHTML = `
    <div class="card"><h3>🧪 バックテスト（統計モード・${bt.range} ／ ${bt.rounds_tested}回）</h3>
      <p class="note">${bt.note}</p>
      <div class="tbl-wrap"><table>
        <tr><th>モード</th><th>ストレート</th><th>ボックス</th><th>セット</th>${isN4() ? "" : "<th>ミニ</th>"}</tr>
        ${btRows}
        <tr style="color:var(--text-muted)"><td>ランダム基準</td><td>${straightBase}%</td><td>—</td><td>—</td>${isN4() ? "" : "<td>1%</td>"}</tr>
      </table></div>
      <p class="note">ストレート理論確率は N3=0.1%(1/1000)・N4=0.01%(1/10000)。統計モードもほぼ基準線どおりで、ナンバーズが当てにくいゲームであることを示します。</p>
    </div>
    ${archiveHtml}`;
}

// ---- wire up ----
document.querySelectorAll(".game-btn").forEach(b => b.addEventListener("click", () => loadGame(b.dataset.game)));
document.querySelectorAll(".tab").forEach(t => t.addEventListener("click", () => switchTab(t.dataset.tab)));
loadGame("numbers3");
