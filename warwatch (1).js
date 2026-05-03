/**
 * WARWATCH — 戰爭預測情報中心
 * WordPress JS v2.1 (2026-03-02)
 * 路徑: /wp-content/themes/js/warwatch.js
 * fixes: ww-card-pizza-bar selector, ww-defcon-label id, DEFAULT_BARS fallback
 */
(function () {
  'use strict';

  // 全域錯誤攔截：防止頁面其他舊 JS 報錯中斷本腳本
  const _origError = window.onerror;
  window.onerror = function(msg, src, line, col, err) {
    // 攔截非 warwatch.js 來源的錯誤，不讓它冒泡中斷執行
    if (src && src.indexOf('warwatch') === -1) {
      console.warn('[WARWATCH] 攔截外部錯誤（不影響本腳本）:', msg, src+':'+line);
      return true; // 阻止預設行為
    }
    if (_origError) return _origError.apply(this, arguments);
    return false;
  };

  /* ──────────────────────────────────────────────────────────
     設定區
  ────────────────────────────────────────────────────────── */
  // Polymarket 由後端 PHP Cron 抓取，前端打 /wp-json/warwatch/v1/polymarket

  const DEFAULT_PIZZA = [
    { name: 'We The Pizza',          busyness: 0, baseline: 45, icon: '🍕', is_open: false, status: 'closed' },
    { name: 'Pizzato Pizza',         busyness: 0, baseline: 40, icon: '🍕', is_open: false, status: 'closed' },
    { name: 'Papa Johns Pizza',      busyness: 0, baseline: 38, icon: '🍕', is_open: false, status: 'closed' },
    { name: "Domino's Pizza",        busyness: 0, baseline: 35, icon: '🍕', is_open: false, status: 'closed' },
    { name: 'Extreme Pizza',         busyness: 0, baseline: 30, icon: '🍕', is_open: false, status: 'closed' },
    { name: 'District Pizza Palace', busyness: 0, baseline: 32, icon: '🍕', is_open: false, status: 'closed' },
  ];

const DEFAULT_BARS = [
  { name: "Freddie's Beach Bar", busyness: 0, icon: '🍺', is_open: false, status: 'closed', is_quiet: false },
  { name: 'Sine Irish Pub',      busyness: 0, icon: '🍺', is_open: false, status: 'closed', is_quiet: false },
  { name: 'The Ugly Mug',        busyness: 0, icon: '🍺', is_open: false, status: 'closed', is_quiet: false },
  { name: 'Cantina Marina',      busyness: 0, icon: '🍺', is_open: false, status: 'closed', is_quiet: false },
  { name: 'Sequoia Restaurant',  busyness: 0, icon: '🍺', is_open: false, status: 'closed', is_quiet: false },
];

  const THRESHOLD = { ELEVATED: 40, HIGH: 60, ANOMALY: 70 };
  const ANOMALY_SHOPS_REQUIRED = 2;
  const HISTORICAL_MATCH = { 1:'~42%', 2:'~63%', 3:'~76%', 4:'~91%' };

  const WAR_KEYWORDS = ['war','strike','attack','invasion','ceasefire','nuclear',
    'missile','military','Iran','Taiwan','Ukraine','Korea','NATO','Israel'];

  // Polymarket 靜態備援（API 失敗時使用）
  const STATIC_POLY = [
    { question:'🇺🇦 俄烏停火：2026年底前達成協議？',  yes_pct:37, volume:10500000, color:'var(--ww-b)' },
    { question:'🇮🇷 美伊直接軍事衝突（2026）？',      yes_pct:28, volume:8200000,  color:'var(--ww-r)' },
    { question:'🇸🇴 美軍攻擊索馬利亞海盜？',           yes_pct:89, volume:5100000,  color:'var(--ww-o)' },
    { question:'🇹🇼 台海武裝衝突（2026年內）？',       yes_pct:12, volume:4700000,  color:'var(--ww-b)' },
    { question:'☢️ 核武器在任何衝突中被使用（2026）？', yes_pct:5,  volume:3200000,  color:'#cc44ff'     },
    { question:'🌐 南海島礁武裝對峙升級（2026）？',     yes_pct:22, volume:2900000,  color:'var(--ww-g)' },
  ];

  /* ──────────────────────────────────────────────────────────
     DOM 工具（只定義一次）
  ────────────────────────────────────────────────────────── */
  const $ = id => document.getElementById(id);
  const ready = fn => document.readyState === 'loading'
    ? document.addEventListener('DOMContentLoaded', fn) : fn();

  /* ──────────────────────────────────────────────────────────
     UTC 時鐘
  ────────────────────────────────────────────────────────── */
  function startClock() {
    const tick = () => {
      const d = new Date();
      const p = n => String(n).padStart(2,'0');
      const s = `${p(d.getUTCHours())}:${p(d.getUTCMinutes())}:${p(d.getUTCSeconds())} UTC`;
      const el = $('ww-clock'); if (el) el.textContent = s;
      const ts = $('ww-alert-ts'); if (ts) ts.textContent = s;
    };
    tick(); setInterval(tick, 1000);
  }

  function animateMeters() {
    document.querySelectorAll('.ww-mf[data-w]').forEach(el => {
      el.style.width = '0%';
      setTimeout(() => { el.style.width = el.dataset.w + '%'; }, 500);
    });
  }

  /* ──────────────────────────────────────────────────────────
     🍕 PIZZA ANOMALY ENGINE
  ────────────────────────────────────────────────────────── */
  function getPizzaData() {
    return (window.wwPizzaData && window.wwPizzaData.length)
      ? window.wwPizzaData : DEFAULT_PIZZA;
  }

  /* ──────────────────────────────────────────────────────────
     🍕🍺 Pizza + Bar 即時資料
  ────────────────────────────────────────────────────────── */
  async function fetchPizzaLive() {
    if (!window.wwSiteUrl) return;
    try {
      const res = await fetch(`${window.wwSiteUrl}/wp-json/warwatch/v1/pizza-live`);
      if (!res.ok) throw new Error();
      const d = await res.json();
      if (!d || !d.shops || !d.shops.length) throw new Error('empty');

      // 更新全域資料（Pizza）
      window.wwPizzaData = d.shops;

      // 渲染 Pizza 店
      const status = evaluatePizza(d.shops);
      renderPizzaShops(d.shops);
      renderPizzaAlert(status, d.shops);

      // 渲染酒吧
      if (d.bars && d.bars.length) renderBars(d.bars);

      // 交叉訊號
      renderCrossSignal(d);

      // 時間戳
      const ts = $('ww-defcon-sub');
      if (ts) ts.textContent = d.updated ? `資料時間：${d.updated}` : '';

    } catch(e) {
      console.warn('[WARWATCH] FIRMS fetch failed:', e.message);
      // 使用 PHP 注入的初始值，不需要額外操作
    }
  }

  function renderBars(bars) {
    const grid = $('ww-bar-grid'); if (!grid) return;
    grid.innerHTML = bars.map(bar => {
      const isClosed = bar.is_open === false || bar.status === 'closed';
      const isQuiet  = bar.is_quiet === true;

      const [dotCls, sCol, sTxt] = isClosed
        ? ['dim', 'rgba(255,255,255,.3)', '⬛ CLOSED']
        : isQuiet
        ? ['b',   'var(--ww-b)',   `⚠ 異常冷清 (${bar.busyness}%)`]
        : ['g',   'var(--ww-g)',   `✓ 正常 (${bar.busyness}%)`];

      const barCol = isClosed ? 'var(--ww-border)' : isQuiet ? 'var(--ww-b)' : 'var(--ww-g)';

      return `<div class="ww-pshop${isQuiet ? ' quiet' : ''}${isClosed ? ' closed' : ''}">
  <div class="ww-pshop-name">${bar.icon || '🍺'} ${bar.name}</div>
  <div class="ww-pshop-status">
    <div class="ww-sd ${dotCls}"></div>
    <span style="color:${sCol};font-size:.65rem">${sTxt}</span>
  </div>
  <div class="ww-shop-bar-wrap">
    <div class="ww-shop-bar">
      <div class="ww-shop-bar-fill" style="width:${isClosed ? 0 : bar.busyness}%;background:${barCol}"></div>
    </div>
    <div class="ww-shop-dev" style="color:${isQuiet ? 'var(--ww-b)' : 'var(--ww-dim)'}">
      ${isClosed ? '目前未營業' : isQuiet ? '⚠ 下班時段應忙卻冷清' : '正常客流'}
    </div>
  </div>
</div>`;
    }).join('');
  }

  function renderCrossSignal(d) {
    const el = $('ww-cross-signal'); if (!el) return;
    if (d.cross_signal) {
      el.style.display = 'block';
      const detail = $('ww-cross-detail');
      if (detail) {
        detail.textContent =
          `Pizza 異常店家：${d.pizza_busy_cnt} / ${(d.pizza||[]).length} 間　` +
          `酒吧冷清：${d.bar_quiet_cnt} / ${(d.bars||[]).filter(b=>b.is_open).length} 間（${Math.round((d.bar_quiet_ratio||0)*100)}% 冷清）`;
      }
    } else {
      el.style.display = 'none';
    }
  }

  function evaluatePizza(shops) {
    // 打烊的店排除在警報計算外
    const openShops = shops.filter(s => s.is_open !== false && s.status !== 'closed');
    const allClosed = openShops.length === 0;

    if (allClosed) {
      return { level:'CLOSED', labelZh:'🔒 全部打烊', color:'var(--ww-dim)',
               anomalyShops:[], highShops:[], avg:0, allClosed:true };
    }

    // 下班時段異常優先判斷
    const afterHoursAnomalies = openShops.filter(s => s.after_hours_anomaly === true);
    const anomaly = openShops.filter(s => s.busyness >= THRESHOLD.ANOMALY);
    const high    = openShops.filter(s => s.busyness >= THRESHOLD.HIGH && s.busyness < THRESHOLD.ANOMALY);
    const avg     = openShops.reduce((a,s) => a + s.busyness, 0) / openShops.length;

    let level, labelZh, color;

    if (afterHoursAnomalies.length >= 2) {
      // 下班時段多店異常 → 最高警戒
      level='ANOMALY'; labelZh='⚠ 下班異常警報'; color='var(--ww-r)';
    } else if (afterHoursAnomalies.length === 1) {
      level='HIGH'; labelZh='⚠ 下班時段偏高'; color='#ff8800';
    } else if (anomaly.length >= ANOMALY_SHOPS_REQUIRED) {
      level='ANOMALY'; labelZh='⚠ 戰爭預警'; color='var(--ww-r)';
    } else if (anomaly.length === 1 || high.length >= 2) {
      level='HIGH';    labelZh='⚠ 高度警戒'; color='#ff8800';
    } else if (avg >= THRESHOLD.ELEVATED) {
      level='ELEVATED'; labelZh='▲ 偏高';    color='var(--ww-o)';
    } else {
      level='NORMAL';   labelZh='● 正常';    color='var(--ww-g)';
    }

    return { level, labelZh, color,
             anomalyShops: afterHoursAnomalies.length ? afterHoursAnomalies : anomaly,
             highShops: high, avg, allClosed: false };
  }

  function renderPizzaShops(shops) {
    const grid = $('ww-pizza-grid'); if (!grid) return;
    grid.innerHTML = shops.map(shop => {
      const isClosed = shop.is_open === false || shop.status === 'closed';
      const isA = !isClosed && shop.busyness >= THRESHOLD.ANOMALY;
      const isH = !isClosed && !isA && shop.busyness >= THRESHOLD.HIGH;
      const isAfterHours = shop.after_hours_anomaly === true;

      const dev = shop.baseline
        ? Math.round(((shop.busyness - shop.baseline) / shop.baseline) * 100) : 0;
      const devStr = dev >= 0 ? `+${dev}%` : `${dev}%`;

      // 狀態顯示
      const [dotCls, sCol, sTxt] = isClosed
        ? ['dim', 'rgba(255,255,255,.3)',  '⬛ CLOSED']
        : isAfterHours
        ? ['r',   'var(--ww-r)',   `🚨 下班異常 (${shop.busyness}%)`]
        : isA
        ? ['r',   'var(--ww-r)',   `🚨 ANOMALY (${shop.busyness}%)`]
        : isH
        ? ['o',   'var(--ww-o)',   `⚠ ELEVATED (${shop.busyness}%)`]
        : ['g',   'var(--ww-g)',   `✓ NORMAL (${shop.busyness}%)`];

      const barCol  = isClosed ? 'var(--ww-border)'
        : isAfterHours || isA ? 'var(--ww-r)'
        : isH ? 'var(--ww-o)' : 'var(--ww-g)';

      const distTag = shop.dist ? `<span style="color:var(--ww-dim);font-size:.55rem;margin-left:.4rem">${shop.dist}</span>` : '';

      // 下班時段標籤
      const afterTag = shop.is_afterhours
        ? `<span style="font-size:.52rem;color:var(--ww-o);margin-left:.5rem">下班時段</span>` : '';

      return `<div class="ww-pshop${isAfterHours || isA ? ' anomaly' : ''}${isClosed ? ' closed' : ''}">
  <div class="ww-pshop-name">${shop.icon || '🍕'} ${shop.name}${distTag}${afterTag}</div>
  <div class="ww-pshop-status">
    <div class="ww-sd ${dotCls}"></div>
    <span style="color:${sCol};font-size:.65rem">${sTxt}</span>
  </div>
  <div class="ww-shop-bar-wrap">
    <div class="ww-shop-bar">
      <div class="ww-shop-bar-fill" style="width:${isClosed ? 0 : shop.busyness}%;background:${barCol}"></div>
    </div>
    ${isClosed
      ? `<div class="ww-shop-dev" style="color:rgba(255,255,255,.25);font-size:.58rem">目前未營業 · 資料來自 Google Places API</div>`
      : `<div class="ww-shop-dev" style="color:${isAfterHours||isA?'var(--ww-r)':isH?'var(--ww-o)':'var(--ww-dim)'}">vs 基準 <strong>${devStr}</strong></div>`
    }
  </div>
</div>`;
    }).join('');
  }

  function renderPizzaAlert(status, shops) {
    const alertEl  = $('ww-pizza-alert');
    const cardEl   = document.querySelector('.ww-card-pizza-bar, .ww-pizza-card');
    const gaugeEl  = $('ww-gauge-fill');
    const gaugePct = $('ww-gauge-pct');
    const levelNum = $('ww-defcon-label');
    const lvlLbl   = $('ww-alert-lvl');
    const mainTxt  = $('ww-alert-main');
    const shopsCnt = $('ww-alert-shops');
    const bullets  = $('ww-alert-bullets');
    const badge    = $('ww-badge');

    const gaugeVal = Math.round(status.avg);
    if (gaugeEl)  gaugeEl.style.width = gaugeVal + '%';
    if (gaugePct) { gaugePct.textContent = gaugeVal + '%'; gaugePct.style.color = status.color; }
    if (levelNum) { levelNum.textContent = status.labelZh; levelNum.style.color = status.color; }
    if (!alertEl) return;

    // 全部打烊（顯示 ET 當地時間讓使用者了解原因）
    if (status.allClosed) {
      alertEl.style.display = 'none';
      if (cardEl) { cardEl.classList.remove('anomaly'); cardEl.style.opacity = '.5'; }
      if (badge) {
        // 計算美東時間（UTC-5，夏令 UTC-4）
        const now = new Date();
        const etOffset = -5; // 標準時 EST，可改 -4 夏令
        const etHour = (now.getUTCHours() + etOffset + 24) % 24;
        const etMin  = String(now.getUTCMinutes()).padStart(2,'0');
        const period = etHour < 12 ? 'AM' : 'PM';
        const h12    = etHour % 12 || 12;
        badge.textContent = `🔒 打烊中（ET ${h12}:${etMin} ${period}）`;
        badge.style.borderColor = badge.style.color = 'var(--ww-dim)';
      }
      return;
    }
    if (cardEl) cardEl.style.opacity = '';

    if (status.level === 'ANOMALY') {
      alertEl.style.display = 'block';
      if (cardEl) cardEl.classList.add('anomaly');
      const ac  = status.anomalyShops.length;
      const hm  = HISTORICAL_MATCH[ac] || '~76%';
      const top = [...status.anomalyShops].sort((a,b) => b.busyness - a.busyness)[0];
      const topDev = top?.baseline ? Math.round(((top.busyness - top.baseline) / top.baseline) * 100) : 0;
      const isAfterHours = status.anomalyShops.some(s => s.after_hours_anomaly);

      if (lvlLbl)   lvlLbl.textContent = isAfterHours
        ? `下班時段異常 — ${ac} 家店觸發`
        : `CRITICAL ANOMALY — ${ac} 家店觸發`;
      if (mainTxt)  mainTxt.innerHTML  = isAfterHours
        ? `🍕 下班時段（ET 17:00-21:00）出現<strong style="color:var(--ww-r)">異常訂單潮</strong> — 五角大廈周邊 Pizza 店在非尖峰時段大量湧入，歷史上此訊號曾先於軍事行動 2–48 小時出現`
        : `🍕 披薩指數<strong style="color:var(--ww-r)">嚴重異常</strong> — 歷史上此訊號出現後 <strong>2–48 小時</strong>內曾有軍事行動發生`;
      if (shopsCnt) shopsCnt.textContent = `${ac} / ${shops.filter(s=>s.is_open!==false).length}`;
      if (bullets)  bullets.innerHTML = `
<div style="color:var(--ww-r)">▶ ${top?.name} 繁忙度較基準高出 <strong>+${topDev}%</strong></div>
<div style="color:var(--ww-o)">▶ ${ac} 家店同時出現異常，交叉確認可信度提升</div>
<div style="color:var(--ww-o)">▶ 歷史符合率：${hm}（${ac} 家店同時觸發時）</div>
<div style="color:var(--ww-dim)">▶ 建議同步觀察：Polymarket 機率、FlightRadar24 軍機動態</div>`;
      if (badge) { badge.textContent = isAfterHours ? '🍕 下班異常' : '🍕 PIZZA ANOMALY'; badge.style.borderColor = badge.style.color = 'var(--ww-r)'; }

    } else if (status.level === 'HIGH') {
      alertEl.style.display = 'block';
      if (cardEl) cardEl.classList.remove('anomaly');
      if (lvlLbl)  lvlLbl.textContent = 'HIGH ACTIVITY';
      if (mainTxt) mainTxt.innerHTML  = `🍕 披薩指數<strong style="color:var(--ww-o)">偏高</strong> — 多店出現高於平均訂單量，尚未達到歷史警戒門檻`;
      const cnt   = status.highShops.length + status.anomalyShops.length;
      const names = [...status.highShops,...status.anomalyShops].map(s=>s.name).join('、');
      if (shopsCnt) shopsCnt.textContent = `${cnt} / ${shops.filter(s=>s.is_open!==false).length}`;
      if (bullets)  bullets.innerHTML = `
<div style="color:var(--ww-o)">▶ 高活躍度店家：${names}</div>
<div style="color:var(--ww-dim)">▶ 當前：偏高，尚未達 ANOMALY 閾值（需 ≥${THRESHOLD.ANOMALY}%）</div>
<div style="color:var(--ww-dim)">▶ 若再有 1 家店升至異常，將觸發紅色戰爭警報</div>`;
      if (badge) { badge.textContent = '威脅 高度警戒'; badge.style.borderColor = badge.style.color = 'var(--ww-o)'; }

    } else {
      alertEl.style.display = 'none';
      if (cardEl) cardEl.classList.remove('anomaly');
    }
  }

  function initPizza() {
    // 先渲染 pizza + bars 靜態狀態，等 API 回來再覆蓋
    renderPizzaShops(DEFAULT_PIZZA);
    renderBars(DEFAULT_BARS);
    const status = evaluatePizza(DEFAULT_PIZZA);
    renderPizzaAlert(status, DEFAULT_PIZZA);
  }

  /* ──────────────────────────────────────────────────────────
     📊 POLYMARKET
     修正：Gamma API 的 yes 機率在 outcomePrices 字串陣列
     "[\"0.37\",\"0.63\"]"，index 0 = Yes
  ────────────────────────────────────────────────────────── */
  /* ──────────────────────────────────────────────────────────
     WPI — War Pressure Index 計算
     WPI = 0.35P + 0.30A + 0.15F + 0.20S  (0-100)
  ────────────────────────────────────────────────────────── */
  function recalcWpi() {
    // ── 各分項分數計算 ────────────────────────────────────

    // P: Polymarket — 戰爭相關市場加權平均機率
    const poly = window.wwPolyData || [];
    let P = 0;
    if (poly.length) {
      const weights = { high: 1.5, med: 1.0, low: 0.6 };
      let wSum = 0, vSum = 0;
      poly.forEach(m => {
        const pct = m.yes_pct ?? 0;
        const w = pct >= 50 ? weights.high : pct >= 25 ? weights.med : weights.low;
        vSum += pct * w; wSum += w;
      });
      P = wSum > 0 ? Math.min(100, Math.round(vSum / wSum)) : 0;
    }

    // A: Aviation — 軍機異常指數
    // 邏輯：以 total 架次 + anomaly_pct 雙重判斷
    // 正常日常偵察：3-8 架 → A=15-30
    // 異常升高：10-15 架 → A=40-60
    // 高度異常：20+ 架 → A=80-100
    const avi = window.wwAviData || {};
    const aviSum = avi.summary || {};
    let A = 0;
    if (aviSum.total != null) {
      const total = aviSum.total || 0;
      const base  = Math.max(aviSum.baseline_7d || 3, 1);
      const ratio = total / base; // 1.0 = 正常, 2.0 = 兩倍, 3.0+ = 高度異常

      // 分段映射：ratio 1.0→A=20, 1.5→A=35, 2.0→A=50, 3.0→A=70, 4.0+→A=90
      if      (ratio >= 4.0) A = 90;
      else if (ratio >= 3.0) A = Math.round(70 + (ratio - 3.0) * 20);
      else if (ratio >= 2.0) A = Math.round(50 + (ratio - 2.0) * 20);
      else if (ratio >= 1.5) A = Math.round(35 + (ratio - 1.5) * 30);
      else if (ratio >= 1.0) A = Math.round(20 + (ratio - 1.0) * 30);
      else                   A = Math.round(ratio * 20);

      A = Math.min(100, Math.max(0, A));
      console.log(`[WARWATCH] Aviation: total=${total} base=${base.toFixed(1)} ratio=${ratio.toFixed(2)} A=${A}`);
    }

    // F: FIRMS — 衛星火點異常指數
    const firms = window.wwFirmsData || {};
    let F = 0;
    if (firms.fire_24h != null) {
      // fire_delta 是相對於前一天的百分比變化（e.g. "+5.2%" 或 "-3.1%"）
      const deltaStr = firms.fire_delta || '0%';
      const deltaPct = parseFloat(deltaStr.replace('%','')) || 0;
      // 基準：delta=0 → F=30; delta=+20% → F=50; delta=+50% → F=75; delta=+100% → F=100
      F = Math.min(100, Math.max(0, Math.round(30 + deltaPct * 0.7)));
    }

    // S: Sentiment — VIX + 黃金 + 油價
    const fin = window.wwFinanceData || {};
    let S = 0;
    if (fin.assets && fin.assets.length) {
      const vix  = fin.assets.find(a => a.ticker === '^VIX');
      const gold = fin.assets.find(a => a.ticker === 'GC=F');
      const oil  = fin.assets.find(a => a.ticker === 'BZ=F');
      const vixScore  = vix  ? Math.min(100, Math.max(0, Math.round((vix.price  - 15) / 45 * 100))) : 30;
      const goldScore = gold ? Math.min(100, Math.max(0, gold.change > 0 ? Math.round(gold.change * 8) : 0)) : 20;
      const oilScore  = oil  ? Math.min(100, Math.max(0, Math.round((fin.war_premium_oil || 0) * 5 + 20))) : 20;
      S = Math.round((vixScore * 0.5 + goldScore * 0.3 + oilScore * 0.2));
    }

    // WPI 加權合計
    const wpi = Math.min(100, Math.round(P * 0.35 + A * 0.30 + F * 0.15 + S * 0.20));

    // ── 更新 DOM ─────────────────────────────────────────
    // 分項 bars
    const factors = { p: P, a: A, f: F, s: S };
    Object.entries(factors).forEach(([k, v]) => {
      const fill = $('wpi-' + k + '-fill'); if (fill) fill.style.width = v + '%';
      const val  = $('wpi-' + k + '-val');  if (val)  val.textContent = v;
    });

    // WPI 數字
    const numEl = $('ww-wpi-num');
    if (numEl) numEl.textContent = wpi;

    // 指針：SVG transform rotate + rAF 平滑動畫
    const needle = $('ww-wpi-needle');
    if (needle) {
      const targetAngle = -90 + (wpi / 100) * 180;
      const currentTransform = needle.getAttribute('transform') || 'rotate(-90, 110, 110)';
      const currentAngle = parseFloat((currentTransform.match(/rotate\(([-\d.]+)/) || [0, -90])[1]);
      const duration = 1500; // ms
      const startTime = performance.now();
      const fromAngle = currentAngle;
      const animateNeedle = (now) => {
        const elapsed = now - startTime;
        const progress = Math.min(elapsed / duration, 1);
        // easeOutCubic
        const ease = 1 - Math.pow(1 - progress, 3);
        const angle = fromAngle + (targetAngle - fromAngle) * ease;
        needle.setAttribute('transform', `rotate(${angle.toFixed(2)}, 110, 110)`);
        if (progress < 1) requestAnimationFrame(animateNeedle);
      };
      requestAnimationFrame(animateNeedle);
    }

    // SVG arc fill (strokeDasharray, 總周長 283)
    const arc = $('ww-wpi-arc-fill');
    if (arc) arc.setAttribute('stroke-dasharray', Math.round(wpi * 2.83) + ' 283');

    // Level 文字 + badge
    const levels = [
      { min: 75, label: 'CRITICAL',  badge: '🚨 危機等級', cls: 'critical' },
      { min: 55, label: 'HIGH',      badge: '⚠ 高度警戒', cls: 'high'     },
      { min: 35, label: 'ELEVATED',  badge: '▲ 中度警戒', cls: 'elevated' },
      { min:  0, label: 'LOW',       badge: '✓ 低度',     cls: 'low'      },
    ];
    const lv = levels.find(l => wpi >= l.min) || levels[3];

    const lvEl = $('ww-wpi-level'); if (lvEl) lvEl.textContent = lv.label;
    const badge = $('ww-wpi-badge');
    if (badge) { badge.className = 'ww-wpi-alert-badge ' + lv.cls; }
    const badgeIcon = $('ww-wpi-badge-icon');
    const badgeTxt  = $('ww-wpi-badge-text');
    if (badgeIcon) badgeIcon.textContent = lv.badge.split(' ')[0];
    if (badgeTxt)  badgeTxt.textContent  = lv.badge.split(' ').slice(1).join(' ');

    // alert items
    const alLow  = $('wpi-al-low-status');
    const alMed  = $('wpi-al-med-status');
    const alHigh = $('wpi-al-high-status');
    if (alLow)  alLow.textContent  = wpi >= 35 ? '✅ 觸發' : '—';
    if (alMed)  alMed.textContent  = wpi >= 55 ? '✅ 觸發' : '—';
    if (alHigh) alHigh.textContent = wpi >= 75 ? '🚨 觸發' : '—';

    // formula bar
    const formula = document.querySelector('.ww-wpi-formula');
    if (formula) {
      formula.textContent = `» 計算中… 權重：Polymarket ${P}% · Aviation ${A}% · FIRMS ${F}% · Sentiment ${S}%`;
    }

    // 分項 desc
    const pDesc = $('wpi-p-desc'); if (pDesc && poly.length) pDesc.textContent = `市場共識戰爭機率（${poly.length} 個市場）`;
    const aDesc = $('wpi-a-desc'); if (aDesc && aviSum.total != null) aDesc.textContent = `軍機異常活動頻率（總計 ${aviSum.total} 架次）`;
    const fDesc = $('wpi-f-desc'); if (fDesc && firms.fire_24h) fDesc.textContent = `衛星火點異常指數（24h: ${firms.fire_24h.toLocaleString()} 個）`;

    console.log(`[WARWATCH] WPI=${wpi} (P=${P} A=${A} F=${F} S=${S})`);
  }

  async function fetchPolymarket() {
    const list = $('ww-poly-list'); if (!list) { console.warn('[WARWATCH] ww-poly-list not found'); return; }
    try {
      const ctrl = new AbortController();
      const tid = setTimeout(() => ctrl.abort(), 10000);
      const res = await fetch(`${window.wwSiteUrl}/wp-json/warwatch/v1/polymarket`, { signal: ctrl.signal });
      clearTimeout(tid);
      if (!res.ok) throw new Error(`API ${res.status}`);
      const d = await res.json();
      console.log('[WARWATCH] Polymarket API:', d);
      const markets = Array.isArray(d.markets) ? d.markets : (Array.isArray(d) ? d : []);
      if (!markets.length) throw new Error('empty response');

      // 更新時間
      const ts = $('ww-poly-updated');
      if (ts && d.updated) ts.textContent = '更新：' + d.updated;

      // WPI 用
      window.wwPolyData = markets;

      // 渲染
      list.innerHTML = markets.slice(0, 6).map(m => {
        const pct   = m.yes_pct ?? 0;
        const color = pct >= 70 ? 'var(--ww-r)' : pct >= 40 ? 'var(--ww-o)' : 'var(--ww-b)';
        const vol   = m.volume >= 1e6 ? `$${(m.volume/1e6).toFixed(1)}M` : m.volume >= 1e3 ? `$${(m.volume/1e3).toFixed(0)}K` : '';
        const cls   = pct >= 70 ? 'danger' : pct >= 40 ? 'warn' : '';
        const url   = m.url || 'https://polymarket.com';
        return `<a href="${url}" target="_blank" rel="noopener" style="text-decoration:none;color:inherit;display:block">
  <div class="ww-poly-item ${cls}" style="cursor:pointer" onmouseover="this.style.borderLeftWidth='5px'" onmouseout="this.style.borderLeftWidth='3px'">
    <div class="ww-poly-q">${m.question}</div>
    <div class="ww-poly-bar-row">
      <span style="font-family:'Share Tech Mono',monospace;font-size:.62rem;color:var(--ww-dim);width:24px">YES</span>
      <div class="ww-poly-bar"><div class="ww-poly-fill" style="width:${pct}%;background:linear-gradient(90deg,#001,${color})"></div></div>
      <div class="ww-poly-pct" style="color:${color}">${pct}%</div>
    </div>
    <div class="ww-poly-meta">
      <span>${vol ? '交易量 '+vol : ''}</span>
      <span style="color:var(--ww-dim)">polymarket.com ↗</span>
    </div>
  </div>
</a>`;
      }).join('');

      // WPI P score
      return { markets };
    } catch(e) {
      // fallback：用靜態備援數據
      console.warn('[WARWATCH] Polymarket API failed:', e.message);
      const ts2 = $('ww-poly-updated');
      if (ts2) ts2.textContent = '靜態備援資料（API 暫時無法連線）';
      const list2 = $('ww-poly-list'); if (!list2) return;
      list2.innerHTML = STATIC_POLY.map(m => {
        const pct   = m.yes_pct;
        const color = m.color;
        const cls   = pct >= 70 ? 'danger' : pct >= 40 ? 'warn' : '';
        return `<div class="ww-poly-item ${cls}">
    <div class="ww-poly-q">${m.question}</div>
    <div class="ww-poly-bar-row">
      <span style="font-family:'Share Tech Mono',monospace;font-size:.62rem;color:var(--ww-dim);width:24px">YES</span>
      <div class="ww-poly-bar"><div class="ww-poly-fill" style="width:${pct}%;background:linear-gradient(90deg,#001,${color})"></div></div>
      <div class="ww-poly-pct" style="color:${color}">${pct}%</div>
    </div>
  </div>`;
      }).join('');
    }
  }


  async function fetchAviation() {
    if (!window.wwSiteUrl) return;
    try {
      const res = await fetch(`${window.wwSiteUrl}/wp-json/warwatch/v1/aviation`);
      if (!res.ok) throw new Error();
      const d = await res.json();
      if (!d || !d.summary) return;

      // 同步更新 wwAviData 供 WPI 使用
      window.wwAviData = d;

      const sum = d.summary;
      document.querySelectorAll('.ww-avi-box').forEach((box, i) => {
        const val = box.querySelector('.ww-avi-box-val');
        if (val) val.textContent = [sum.tankers, sum.awacs, sum.uav][i] ?? val.textContent;
      });

      const ts = $('ww-avi-updated');
      if (ts && d.updated) ts.textContent = '更新：' + d.updated;

      const list = document.querySelector('.ww-avi-list');
      if (list && d.aircraft && d.aircraft.length) {
        const roleLbl = { tanker:'加油機', awacs:'預警機', uav:'偵察機' };
        list.innerHTML = d.aircraft.map(ac => {
          const tUp = (ac.trend||'').startsWith('+');
          return `<div class="ww-avi-item">
  <div class="ww-avi-dot ${ac.role||'unknown'}"></div>
  <div>
    <div style="font-size:.72rem;color:var(--ww-text)">${ac.callsign} <span style="color:var(--ww-dim);font-size:.6rem">${ac.type}</span></div>
    <div class="ww-avi-type">${ac.region} · ${roleLbl[ac.role]||ac.role}${ac.alt_ft?' · '+ac.alt_ft.toLocaleString()+'ft':''}</div>
  </div>
  <div class="ww-avi-trend ${tUp?'up':'down'}">${ac.trend||'-'}</div>
</div>`;
        }).join('');
      }
    } catch(e) {
      console.warn('[WARWATCH] Aviation fetch failed:', e.message);
      // 使用 PHP 注入的初始值，不需要額外操作
    }
  }

  /* ──────────────────────────────────────────────────────────
     🔥 FIRMS — 每 15 分鐘
  ────────────────────────────────────────────────────────── */
  async function fetchFirms() {
    if (!window.wwSiteUrl) return;
    try {
      const res = await fetch(`${window.wwSiteUrl}/wp-json/warwatch/v1/firms`);
      if (!res.ok) throw new Error();
      const d = await res.json();
      if (!d) return;

      // 同步更新 wwFirmsData 供 WPI 使用
      window.wwFirmsData = d;

      const fireBoxes = document.querySelectorAll('.ww-fire-box .ww-fire-val');
      if (fireBoxes[0] && d.fire_24h)   fireBoxes[0].textContent = d.fire_24h.toLocaleString();
      if (fireBoxes[1] && d.fire_delta) {
        fireBoxes[1].textContent  = d.fire_delta;
        fireBoxes[1].style.color  = d.fire_delta.startsWith('+') ? 'var(--ww-r)' : 'var(--ww-g)';
      }

      const ts = $('ww-firms-updated');
      if (ts && d.updated) ts.textContent = '更新：' + d.updated;

      const typeIcon = { fire:'🔥', air:'✈️', move:'🚛', cyber:'💻' };
      const feed = $('ww-live-feed');
      if (feed && d.events && d.events.length) {
        feed.innerHTML = d.events.map(ev => `<div class="ww-feed-item ${ev.type||''}">
  <div class="ww-feed-time">${ev.time}</div>
  <div><div class="ww-feed-text">${typeIcon[ev.type]||'⚡'} <strong>${ev.region}</strong> — ${ev.text}</div></div>
</div>`).join('');
      }
    } catch(e) {
      // API 失敗時，顯示靜態 fallback（全部 CLOSED）
      const shops = DEFAULT_PIZZA;
      renderPizzaShops(shops);
      const status = evaluatePizza(shops);
      renderPizzaAlert(status, shops);
      renderBars(DEFAULT_BARS);
    }
  }

  /* ──────────────────────────────────────────────────────────
     💰 金融避險指標 — 每 10 分鐘
  ────────────────────────────────────────────────────────── */
  async function fetchFinance() {
    if (!window.wwSiteUrl) return;
    try {
      const res = await fetch(`${window.wwSiteUrl}/wp-json/warwatch/v1/finance`);
      if (!res.ok) throw new Error();
      const d = await res.json();
      if (!d || !d.assets || !d.assets.length) {
        console.warn('[WARWATCH] Finance: empty or invalid response', d);
        return;
      }
      // 驗證每個 asset 有合理數值
      const validAssets = d.assets.filter(a => a.price > 0 && isFinite(a.price));
      if (validAssets.length < d.assets.length) {
        console.warn('[WARWATCH] Finance: some assets invalid', d.assets.filter(a => !(a.price > 0)));
      }
      d.assets = validAssets.length ? validAssets : d.assets; // fallback 保留原始

      console.log('[WARWATCH] Finance OK:', d.assets.map(a => `${a.ticker}=${a.price}`).join(', '));

      // 同步更新 wwFinanceData 供 WPI 使用
      window.wwFinanceData = d;

      const assetBoxes = document.querySelectorAll('.ww-fin-box');
      d.assets.forEach((a, i) => {
        const box = assetBoxes[i]; if (!box) return;
        const px  = box.querySelector('.ww-fin-price');
        const chg = box.querySelector('.ww-fin-change');
        const dev = box.querySelector('[data-ma30]') || box.querySelectorAll('div')[3];
        if (px)  {
          px.textContent = a.ticker === 'USDCHF=X'
            ? (+a.price).toFixed(4)
            : (+a.price).toLocaleString('en',{minimumFractionDigits:2,maximumFractionDigits:2});
          px.style.color = a.change >= 0 ? 'var(--ww-o)' : 'var(--ww-g)';
        }
        if (chg) { chg.textContent = (a.change>=0?'+':'')+a.change+'% 24h'; chg.className='ww-fin-change '+(a.change>=0?'up':'down'); }
        const devPct = a.ma30 > 0 ? ((a.price-a.ma30)/a.ma30*100).toFixed(1) : 0;
        if (dev && dev.tagName) dev.innerHTML = `30MA偏離 ${devPct>=0?'+':''}${devPct}%${Math.abs(devPct)>5?' <span style="color:var(--ww-o)">⚠</span>':''}`;
      });

      const prem = document.querySelector('.ww-fin-war-premium strong');
      if (prem && d.war_premium_oil != null) prem.textContent = ' +$' + d.war_premium_oil + '/bbl';

      const stockItems = document.querySelectorAll('.ww-fin-stock-item');
      (d.stocks||[]).forEach((s, i) => {
        const row = stockItems[i]; if (!row) return;
        const px  = row.querySelector('.ww-fin-stock-px');
        const chg = row.querySelector('.ww-fin-stock-chg');
        if (px)  px.textContent = (+s.price).toFixed(2);
        if (chg) { chg.textContent=(s.change>=0?'+':'')+s.change+'%'+(s.flag?' 🚨':''); chg.className='ww-fin-stock-chg '+(s.change>=0?'up':'down'); }
      });

      const ts = $('ww-fin-updated');
      if (ts && d.updated) ts.textContent = '更新：' + d.updated;
    } catch(e) {
      // Finance API 失敗時，用 window.wwFinanceData（PHP 注入的初始值）
      console.warn('[WARWATCH] Finance fetch failed:', e.message);
      const d = window.wwFinanceData;
      if (d && d.assets) {
        const assetBoxes = document.querySelectorAll('.ww-fin-box');
        d.assets.forEach((a, i) => {
          const box = assetBoxes[i]; if (!box) return;
          const px  = box.querySelector('.ww-fin-price');
          const chg = box.querySelector('.ww-fin-change');
          if (px) {
            px.textContent = a.ticker === 'USDCHF=X'
              ? (+a.price).toFixed(4)
              : (+a.price).toLocaleString('en',{minimumFractionDigits:2,maximumFractionDigits:2});
          }
          if (chg) {
            chg.textContent = (a.change>=0?'+':'')+a.change+'% 24h';
            chg.className = 'ww-fin-change '+(a.change>=0?'up':'down');
          }
        });
        const ts = $('ww-fin-updated');
        if (ts) ts.textContent = '快取資料：' + (d.updated || '--');
      }
    }
  }

  /* ──────────────────────────────────────────────────────────
     Init
  ────────────────────────────────────────────────────────── */
  ready(function () {
    try { startClock(); } catch(e) { console.warn('[WARWATCH] clock err', e); }
    try { animateMeters(); } catch(e) {}
    try { initPizza(); } catch(e) { console.warn('[WARWATCH] initPizza err', e); }

    // Polymarket：fetch 後立即重算 WPI
    const startPolyRefresh = () => {
      fetchPolymarket().then(recalcWpi);
      setInterval(() => fetchPolymarket().then(recalcWpi), 5 * 60 * 1000);
    };
    startPolyRefresh();

    // 三個 OSINT 模組：fetch 後立即重算 WPI
    const fetchAndRecalc = async fn => {
      try { await fn(); recalcWpi(); } catch(e) { console.warn('[WARWATCH] fetchAndRecalc err', e.message); }
    };

    fetchAndRecalc(fetchAviation); setInterval(() => fetchAndRecalc(fetchAviation), 30*60*1000);
    fetchAndRecalc(fetchFirms);    setInterval(() => fetchAndRecalc(fetchFirms),    15*60*1000);
    fetchAndRecalc(fetchFinance);  setInterval(() => fetchAndRecalc(fetchFinance),  10*60*1000);

    // Pizza + Bar 即時資料（每 30 分鐘）
    try { fetchPizzaLive(); } catch(e) { console.warn('[WARWATCH] pizza err', e); }
    setInterval(() => { try { fetchPizzaLive(); } catch(e) {} }, 30 * 60 * 1000);

    // WPI 首次計算（用 PHP 注入的靜態初始值）
    setTimeout(recalcWpi, 300);
    // 每 10 分鐘定時重算
    setInterval(recalcWpi, 10*60*1000);
  });

})();
