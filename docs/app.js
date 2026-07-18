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
    montecarlo: renderMonteCarlo, stats: renderStats,
  };
  (map[state.activeTab] || (() => {}))();
}

// ---- AI予想 ----
function renderPrediction() {
  const preds = period().predictions;
  let html = `<div class="card"><h3>🤖 第${state.data.latest_round + 1}回 予想（${el("periodDisplay").textContent}）</h3>
    <p class="note">各位ごとに有力数字を選出。モードごとに重視する指標が異なります。信頼度はモンテカルロによる選出割合です。</p></div>`;
  for (const mk of MODE_ORDER) {
    const p = preds[mk];
    if (!p) continue;
    const mc = p.monte_carlo || {};
    const posCells = p.per_position.map(e => `
      <div class="pos-cell">
        <div class="plabel">${e.label}</div>
        ${digitBadge(e.digit)}
        <div class="cands">候補: ${e.candidates.map(c => `${c.digit}(${c.confidence}%)`).join(" ")}</div>
      </div>`).join("");
    const reasons = p.per_position.map(e => `<li>▸ ${e.reason_text}</li>`).join("");
    const conf = [];
    if (mc.straight_pct != null) conf.push(`ストレート ${mc.straight_pct}%`);
    if (mc.box_pct != null) conf.push(`ボックス ${mc.box_pct}%`);
    if (mc.mini_pct != null) conf.push(`ミニ ${mc.mini_pct}%`);
    const tsum = p.metrics.target_sum ? ` ｜ 目標合計 ${p.metrics.target_sum}` : "";
    html += `<div class="pred-card">
      <div class="pred-head">
        <span class="pred-mode">${p.mode_name}</span>
        <span class="pred-conf">${conf.join(" ／ ")}</span>
      </div>
      ${numberBadges(p.digits, true)}
      <div class="pred-metrics">合計 ${p.metrics.sum} ｜ 奇偶 ${p.metrics.odd_even} ｜ 大小 ${p.metrics.big_small} ｜ ${p.metrics.shape}${tsum}</div>
      <div class="pos-row">${posCells}</div>
      <ul class="reason-list">${reasons}</ul>
    </div>`;
  }
  el("predictionResult").innerHTML = html;
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
