/* Kalshi presentation: no client-side source requests or WPI scoring. */
(() => {
  'use strict';
  let snapshot = null, initialRequested = false;
  const en = () => window.WarhubI18n?.language === 'en';
  const txt = (zh, english) => en() ? english : zh;
  const node = (tag, text, cls) => {
    const e = document.createElement(tag);
    if (text !== undefined) e.textContent = text;
    if (cls) e.className = cls;
    return e;
  };
  const finite = n => typeof n === 'number' && Number.isFinite(n);
  function draw() {
    const root = document.getElementById('kalshi-market-container');
    if (!root) return;
    root.replaceChildren();

    const states = {
      available: ['選定系列已完成查詢', 'Selected series checked'],
      partial: ['部分資料 · 尚未查齊', 'Partial data · incomplete scan'],
      stale: ['上次資料 · 本輪未取得有效更新', 'Previous data · refresh unavailable'],
      unavailable: ['暫時無法取得資料', 'Data temporarily unavailable'],
      authorization_pending: ['尚未啟用資料收集', 'Data collection not enabled']
    };
    if (snapshot?.snapshot_kind === 'initial_probe') root.append(node('p', txt('首次實測快照 · 等待正常排程更新', 'Initial API snapshot · awaiting scheduled refresh'), 'kalshi-status'));
    const state = states[snapshot?.status] || ['等待首次收集', 'Awaiting first collection'];
    root.append(node('p', txt(...state), 'kalshi-status'));
    const fetched = Date.parse(snapshot?.fetched_at);
    const stale = snapshot?.status === 'stale' || !Number.isFinite(fetched) || Date.now()-fetched > 21600000 || fetched > Date.now()+300000;
    if (Number.isFinite(fetched)) root.append(node('p', txt('取得時間：', 'Retrieved: ') + new Date(fetched).toLocaleString(en() ? 'en-GB' : 'zh-TW'), 'kalshi-status'));
    const markets = Array.isArray(snapshot?.markets) ? snapshot.markets : [];
    const grid = document.getElementById('poly-list-container');
    if (!grid) return;
    grid.querySelectorAll('[data-exchange="kalshi"]').forEach(e=>e.remove());
    for (const m of markets.slice(0, 8)) {
      const card = node('article', undefined, 'poly-item');
      card.dataset.exchange='kalshi';
      card.append(node('span', 'Kalshi', 'market-exchange'));
      card.append(node('div', en() ? (m.question_en || m.question || 'Title unavailable') : (m.question_zh || '中文翻譯待補'), 'poly-question'));
      const valid = !stale && m.quote_status === 'two_sided' && finite(m.display_midpoint) && m.display_midpoint >= 0 && m.display_midpoint <= 1 && Date.parse(m.end_date) > Date.now();
      const barrow=node('div', undefined, 'poly-bar-container');
      barrow.append(node('span','YES ', 'market-yes'));
      const bar=node('div',undefined,'poly-bar'),fill=node('div',undefined,'poly-fill');
      fill.style.width=valid?(m.display_midpoint*100)+'%':'0%';bar.append(fill);
      const value=node('strong',valid?(m.display_midpoint*100).toFixed(1)+'%':txt('缺值','N/A'),'poly-percent');
      value.title=txt('買賣中價；非實際發生機率','Bid/ask midpoint; not an event probability');
      barrow.append(bar,value);card.append(barrow);
      const meta=node('div',undefined,'poly-meta');
      meta.append(node('span',txt('合約量 ','Contracts ')+(finite(m.volume_contracts)?m.volume_contracts.toLocaleString():'—')));
      const source=node('a','Kalshi ↗');source.href='https://kalshi.com';
      if(typeof m.series_ticker==='string' && /^[A-Z0-9_-]+$/.test(m.series_ticker))source.href+='/markets/'+m.series_ticker.toLowerCase();
      source.target='_blank';source.rel='noopener noreferrer';meta.append(source);card.append(meta);
      if(!valid)card.append(node('small',txt('目前報價不可用','Current quote unavailable')));
      const details = node('details');
      details.append(node('summary', txt('原文與報價資料', 'Original title and quote details')));
      details.append(node('p', m.question || '—'));
      if (m.rules?.yes_sub_title) details.append(node('p', 'YES: ' + m.rules.yes_sub_title));
      const price = n => finite(n) && n >= 0 && n <= 1 ? (n*100).toFixed(1)+'¢' : '—';
      details.append(node('p', txt('買價／賣價：', 'Bid / ask: ') + price(m.yes_bid) + ' / ' + price(m.yes_ask)));
      details.append(node('p', txt('成交合約數：', 'Contracts traded: ') + (finite(m.volume_contracts) && m.volume_contracts >= 0 ? m.volume_contracts.toLocaleString() : '—')));
      details.append(node('p', txt('代碼：', 'Ticker: ') + (m.ticker || '—')));
      if (typeof m.series_ticker === 'string' && /^[A-Z0-9_-]+$/.test(m.series_ticker)) {
        const link = node('a', txt('查看 Kalshi 系列 ↗', 'View Kalshi series ↗'));
        link.href = 'https://kalshi.com/markets/' + m.series_ticker.toLowerCase();
        link.target = '_blank'; link.rel = 'noopener noreferrer';
        details.append(link);
      }
      card.append(details);
      grid.append(card);
    }

    for (const slot of document.querySelectorAll('[data-kalshi-region]')) {
      slot.replaceChildren();
      const related = markets.filter(m => m.region === slot.dataset.kalshiRegion);
      if (!related.length) continue;
      const a = node('a', txt('Kalshi 背景參考 · ', 'Kalshi context · ') + related.length + txt(' 個期限題目 ↗', ' dated contracts ↗'));
      a.href = '#poly-card';
      a.addEventListener('click', () => document.getElementById('poly-card')?.classList.remove('folded'));
      slot.append(a, node('small', stale ? txt('舊資料 · 暫不作即時參考', 'Stale · not a current reference') : txt('外交／政策背景；不重複計分', 'Diplomatic / policy context; not double-counted')));
    }
    if (!markets.length && snapshot?.status === 'available') root.append(node('p', txt('選定系列目前沒有符合篩選且具有效雙邊報價的市場。', 'No markets in the selected series currently pass the filter with valid two-sided quotes.')));
    root.append(node('p', txt('同系列不同期限不是獨立證據。僅涵蓋選定系列；不同平台題目未核對結算條件前，不合併價格或計分。', 'Different deadlines in a series are not independent evidence. Selected series only. Prices and scores are not combined across platforms without matching settlement terms.'), 'kalshi-status'));
  }
  window.refreshKalshiReferences = draw;
  window.renderKalshiMarkets = data => {
    if (data && typeof data === 'object') { snapshot = data; draw(); return; }
    draw();
    if (snapshot || initialRequested) return;
    initialRequested = true;
    fetch('/research/kalshi-initial.json').then(r => { if (!r.ok) throw new Error('Initial snapshot unavailable'); return r.json(); })
      .then(data => { if (!snapshot && data?.snapshot_kind === 'initial_probe') { snapshot = data; draw(); } })
      .catch(() => {});
  };
  document.addEventListener('warhub-language-change', draw);
  document.addEventListener('warhub-i18n-ready', draw);
})();
