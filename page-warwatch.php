<?php
/**
 * Template Name: WARWATCH 戰爭預測情報中心
 *
 * 使用方式：
 * 1. 將此檔案放到你的佈景主題資料夾（如 /wp-content/themes/your-theme/）
 * 2. 在 WordPress 後台 → 頁面 → 新增頁面
 * 3. 右側「頁面屬性」選擇範本：「WARWATCH 戰爭預測情報中心」
 * 4. 發布頁面即可
 *
 * CSS 路徑: /wp-content/themes/css/warwatch.css
 * JS  路徑: /wp-content/themes/js/warwatch.js
 */

// 加入 body class 以隱藏主題 header/footer
add_filter('body_class', function($classes) {
    $classes[] = 'warwatch-fullpage';
    return $classes;
});

// ── Pizza / Bar 數據（Google Places API，每 30 分鐘更新）────────
$pizza_data_raw = get_option('ww_pizza_data', '');
$pizza_data     = $pizza_data_raw ? json_decode($pizza_data_raw, true) : null;
if (!$pizza_data) {
    $legacy = get_option('ww_pizza_shops', '');
    if ($legacy) $pizza_data = ['pizza'=>json_decode($legacy,true),'bars'=>[],'cross_signal'=>false];
}
$pizza_shops = $pizza_data ? json_encode($pizza_data['pizza'] ?? []) : json_encode([]);

// ── Polymarket 靜態備用（每日由 WP Cron 更新）───────────────
$poly_markets = get_option('ww_poly_markets', json_encode([
    ['question'=>'🇺🇦 俄烏停火：2026年底前達成協議？', 'yes_pct'=>37, 'volume'=>10500000, 'url'=>'https://polymarket.com/markets/politics/ukraine'],
    ['question'=>'🇮🇷 美伊直接軍事衝突（2026）？',     'yes_pct'=>28, 'volume'=>8200000,  'url'=>'https://polymarket.com/markets/politics/iran'],
    ['question'=>'🇸🇴 美軍攻擊索馬利亞海盜？',          'yes_pct'=>89, 'volume'=>5100000,  'url'=>'https://polymarket.com/markets/politics'],
    ['question'=>'🇹🇼 台海武裝衝突（2026年內）？',      'yes_pct'=>12, 'volume'=>4700000,  'url'=>'https://polymarket.com/markets/politics/china'],
    ['question'=>'☢️ 核武器在任何衝突中被使用（2026）？','yes_pct'=>5,  'volume'=>3200000,  'url'=>'https://polymarket.com/markets/politics'],
    ['question'=>'🌐 南海島礁武裝對峙升級？',            'yes_pct'=>22, 'volume'=>2900000,  'url'=>'https://polymarket.com/markets/politics/china'],
]));

// ── 航空異常（由 WP Cron 每 30 分鐘更新，來源：OpenSky Network）─
// 航空異常（WP Cron 每 30 分鐘更新，來源：OpenSky Network）
// 若快取空白顯示等待狀態，不用假數字
$avi_data = get_option('ww_avi_data', json_encode([
    'updated'  => '',
    'summary'  => ['tankers'=>0, 'awacs'=>0, 'uav'=>0, 'total'=>0, 'baseline_7d'=>0, 'anomaly_pct'=>0],
    'aircraft' => [],
    'loading'  => true,
]));

// ── 衝突熱點 Live Feed（WP Cron 每 15 分鐘，來源：NASA FIRMS）─
// 衝突熱點（WP Cron 每 15 分鐘更新，來源：NASA FIRMS）
// 若快取空白顯示等待狀態，不用假數字
$firms_data = get_option('ww_firms_data', json_encode([
    'updated'    => '',
    'fire_24h'   => 0,
    'fire_delta' => '--',
    'map_key'    => 'a6f68613078dd3564264e6c72a298dcb',
    'events'     => [],
    'event_types'=> [],
    'loading'    => true,
]));

// ── 經濟避險指標（WP Cron 每 10 分鐘，來源：Yahoo Finance）────
$finance_data_raw = get_option('ww_finance_data', '');
$finance_decoded  = $finance_data_raw ? json_decode($finance_data_raw, true) : null;

// 驗證黃金價格是否合理（應 > $3000），若不合理清除快取並立即重跑
$gold_price = 0;
foreach (($finance_decoded['assets'] ?? []) as $a) {
    if ($a['ticker'] === 'GC=F') { $gold_price = (float)$a['price']; break; }
}
if ($gold_price > 0 && $gold_price < 3000) {
    delete_option('ww_finance_data');
    if (function_exists('ww_cron_fetch_finance')) {
        ww_cron_fetch_finance(); // 立即重新抓取
        $finance_data_raw = get_option('ww_finance_data', '');
        $finance_decoded  = json_decode($finance_data_raw, true);
    }
}

$finance_data = $finance_data_raw ?: json_encode([
    'updated' => '',
    'assets'  => [
        ['ticker'=>'GC=F',     'name'=>'黃金',    'price'=>5246.00, 'change'=>+2.8,  'ma30'=>4980.00],
        ['ticker'=>'BZ=F',     'name'=>'布倫特油', 'price'=>72.87,   'change'=>+2.87, 'ma30'=>67.50],
        ['ticker'=>'USDCHF=X', 'name'=>'USD/CHF',  'price'=>0.7678,  'change'=>-0.64, 'ma30'=>0.8100],
        ['ticker'=>'^VIX',     'name'=>'恐慌指數', 'price'=>19.86,   'change'=>+6.6,  'ma30'=>16.20],
    ],
    'stocks' => [
        ['sym'=>'LMT', 'name'=>'洛克希德馬丁',    'price'=>485.20, 'change'=>+4.1, 'flag'=>false],
        ['sym'=>'RTX', 'name'=>'雷神技術',         'price'=>128.75, 'change'=>+3.7, 'flag'=>false],
        ['sym'=>'NOC', 'name'=>'諾斯洛普格魯曼',   'price'=>512.30, 'change'=>+5.2, 'flag'=>true],
        ['sym'=>'GD',  'name'=>'通用動力',         'price'=>298.40, 'change'=>+2.9, 'flag'=>false],
    ],
    'war_premium_oil' => 5.37,
]);

// ── 防止其他 JS 干擾 warwatch 頁面 ─────────────────────────────
add_action('wp_enqueue_scripts', function () {
    if (!is_page_template('page-warwatch.php')) return;
    // 移除可能干擾的 builder/plugin JS（保留 warwatch 自己的）
    wp_dequeue_script('elementor-frontend');
    wp_dequeue_script('jquery');  // warwatch 不用 jQuery
}, 100);

// ── 輸出緩衝：攔截並移除所有舊版 warwatch JS ────────────────
ob_start(function($html) {
    // 移除含有舊函數名稱的 <script> 區塊（來自 post_content 或舊快取）
    $old_fns = ['renderWarAlert','initPizzaSystem','initPizzaBar','initPizzaBarSystem',
                'initWarWatch','renderPizzaBarStatus','updatePizzaBarStatus'];
    $pattern = '/<script[^>]*>(.*?)<\/script>/is';
    $html = preg_replace_callback($pattern, function($m) use ($old_fns) {
        foreach ($old_fns as $fn) {
            if (strpos($m[1], $fn) !== false) {
                // 移除整個 script 標籤
                return '<!-- [WARWATCH] 移除舊版 JS: ' . htmlspecialchars($fn) . ' -->';
            }
        }
        return $m[0]; // 不含舊函數 → 保留
    }, $html);
    return $html;
});

get_header(); // WP header（fullpage CSS 已隱藏主題 header）
?>
<!DOCTYPE html>
<html <?php language_attributes(); ?>>
<head>
  <meta charset="<?php bloginfo('charset'); ?>">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>WARWATCH // 戰爭預測情報中心 — <?php bloginfo('name'); ?></title>
  <meta name="description" content="結合 Pentagon Pizza Index 與 Polymarket 預測市場的全球衝突指標觀測站">

  <!-- Google Fonts -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Orbitron:wght@400;700;900&family=IBM+Plex+Sans:wght@300;400;500&display=swap" rel="stylesheet">

  <!-- Chart.js -->
  <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>

  <!-- WP head（CSS、plugins 等） -->
  <?php wp_head(); ?>

  <!-- WARWATCH CSS -->
  <link rel="stylesheet" href="<?php echo get_template_directory_uri(); ?>/css/warwatch.css">

  <!-- 注入 PHP 數據給 JS -->
  <script>
    // WARWATCH v2 init — 若見到此 log 代表正確版本已載入
    console.log('[WARWATCH] page-warwatch.php v2 loaded OK');
    // Pizza/Bar 資料全由 fetchPizzaLive() 動態取得，不用 PHP 注入（避免舊快取污染）
    window.wwPizzaData   = [];
    window.wwBarData     = [];
    window.wwCrossSignal = false;
    window.wwPolyData    = <?php echo wp_json_encode(json_decode($poly_markets, true)); ?>;
    window.wwAviData     = <?php echo wp_json_encode(json_decode($avi_data, true)); ?>;
    window.wwFirmsData   = <?php echo wp_json_encode(json_decode($firms_data, true)); ?>;
    window.wwFinanceData = <?php echo wp_json_encode(json_decode($finance_data, true)); ?>;
    window.wwSiteUrl     = '<?php echo esc_url(site_url()); ?>';
  </script>
</head>
<body <?php body_class(); ?>>
<?php wp_body_open(); ?>

<div id="warwatch-page">
<div class="ww-bg-grid"></div>

<!-- ══════════ HEADER ══════════ -->
<div class="ww-header">
  <div class="ww-header-inner">
    <a href="<?php echo esc_url(home_url('/')); ?>" class="ww-logo">
      WAR<em>WATCH</em> <small>戰爭預測情報中心</small>
    </a>
    <div class="ww-hright">
      <div class="ww-live"><div class="ww-dot"></div><span>LIVE</span></div>
      <span id="ww-clock">--:--:-- UTC</span>
      <div class="ww-badge" id="ww-badge">威脅等級 ELEVATED</div>
    </div>
  </div>
</div>

<!-- ══════════ TICKER ══════════ -->
<div class="ww-ticker">
  <div class="ww-ticker-lbl">INTEL FEED</div>
  <div class="ww-ticker-body">
    <div class="ww-ticker-scroll">
      <?php
      // ── RSS 即時新聞（優先）＋ 靜態備用 ───────────────────
      $static_items = [
        '🍕 五角大廈披薩指數 <span class="hl">↑ 異常偏高</span>',
        'Polymarket：俄烏停火 <span class="hl">37%</span>',
        '末日時鐘距離午夜 <span class="danger">90秒</span> — 史上最近',
        '台海衝突 2026：Polymarket <span class="hl">12%</span>',
        '黃金避險需求 · 請查閱即時行情',
        '🍕 CIA 周邊深夜外送量異常上升',
      ];

      $rss_json  = get_option('ww_rss_feed');
      $rss_items = $rss_json ? json_decode($rss_json, true) : [];
      $ticker_items = [];

      if (!empty($rss_items)) {
        foreach (array_slice($rss_items, 0, 20) as $item) {
          $source = esc_html($item['source'] ?? '');
          $title  = esc_html($item['title']  ?? '');
          $age    = esc_html($item['age']    ?? '');
          $link   = esc_url($item['link']    ?? '#');
          $ticker_items[] = '<span class="ww-ti-src">[' . $source . ']</span> '
                          . '<a href="' . $link . '" target="_blank" rel="noopener" class="ww-ti-link">' . $title . '</a>'
                          . ' <span class="ww-ti-age">' . $age . '</span>';
        }
        $ticker_items = array_merge($ticker_items, $static_items);
      } else {
        $ticker_items = $static_items;
      }

      $all_items = array_merge($ticker_items, $ticker_items);
      foreach ($all_items as $item) {
        echo '<div class="ww-ti">' . $item . ' &nbsp;•</div>';
      }
      ?>
    </div>
  </div>
</div>

<div class="ww-wrap">

<!-- ══════════ WPI — 戰爭壓力指數 ══════════ -->
<div class="ww-wpi-section">

  <!-- 頂部標題列 -->
  <div class="ww-wpi-topbar">
    <div>
      <div class="ww-wpi-title">WAR PRESSURE INDEX <span class="ww-wpi-ver">v2.0</span></div>
      <div class="ww-wpi-subtitle">加權多源 OSINT 綜合指數 · 每 10 分鐘自動重算</div>
    </div>
    <div class="ww-wpi-alert-badge" id="ww-wpi-badge">
      <span id="ww-wpi-badge-icon">⚠</span>
      <span id="ww-wpi-badge-text">ELEVATED</span>
    </div>
  </div>

  <!-- 主體：大錶盤 + 四子指標 + 三級警戒 -->
  <div class="ww-wpi-body">
    <!-- 左：四子指標縱列 -->
    <div class="ww-wpi-factors">

      <!-- P: Polymarket -->
      <div class="ww-wpi-factor" id="wpi-factor-p">
        <div class="ww-wpi-f-header">
          <span class="ww-wpi-f-icon">📊</span>
          <span class="ww-wpi-f-name">Polymarket <em>P</em></span>
          <span class="ww-wpi-f-weight">×35%</span>
        </div>
        <div class="ww-wpi-f-bar-wrap">
          <div class="ww-wpi-f-bar"><div class="ww-wpi-f-fill" id="wpi-p-fill" style="width:0%"></div></div>
          <div class="ww-wpi-f-val" id="wpi-p-val">--</div>
        </div>
        <div class="ww-wpi-f-desc" id="wpi-p-desc">市場共識戰爭機率</div>
      </div>

      <!-- A: Aviation -->
      <div class="ww-wpi-factor" id="wpi-factor-a">
        <div class="ww-wpi-f-header">
          <span class="ww-wpi-f-icon">✈️</span>
          <span class="ww-wpi-f-name">Aviation <em>A</em></span>
          <span class="ww-wpi-f-weight">×30%</span>
        </div>
        <div class="ww-wpi-f-bar-wrap">
          <div class="ww-wpi-f-bar"><div class="ww-wpi-f-fill" id="wpi-a-fill" style="width:0%"></div></div>
          <div class="ww-wpi-f-val" id="wpi-a-val">--</div>
        </div>
        <div class="ww-wpi-f-desc" id="wpi-a-desc">軍機異常活動頻率</div>
      </div>

      <!-- F: FIRMS -->
      <div class="ww-wpi-factor" id="wpi-factor-f">
        <div class="ww-wpi-f-header">
          <span class="ww-wpi-f-icon">🔥</span>
          <span class="ww-wpi-f-name">FIRMS <em>F</em></span>
          <span class="ww-wpi-f-weight">×15%</span>
        </div>
        <div class="ww-wpi-f-bar-wrap">
          <div class="ww-wpi-f-bar"><div class="ww-wpi-f-fill" id="wpi-f-fill" style="width:0%"></div></div>
          <div class="ww-wpi-f-val" id="wpi-f-val">--</div>
        </div>
        <div class="ww-wpi-f-desc" id="wpi-f-desc">衛星火點異常指數</div>
      </div>

      <!-- S: Financial Sentiment -->
      <div class="ww-wpi-factor" id="wpi-factor-s">
        <div class="ww-wpi-f-header">
          <span class="ww-wpi-f-icon">💰</span>
          <span class="ww-wpi-f-name">Sentiment <em>S</em></span>
          <span class="ww-wpi-f-weight">×20%</span>
        </div>
        <div class="ww-wpi-f-bar-wrap">
          <div class="ww-wpi-f-bar"><div class="ww-wpi-f-fill" id="wpi-s-fill" style="width:0%"></div></div>
          <div class="ww-wpi-f-val" id="wpi-s-val">--</div>
        </div>
        <div class="ww-wpi-f-desc" id="wpi-s-desc">VIX · 黃金 · 油價避險情緒</div>
      </div>

    </div>

    <!-- 中：大錶盤 -->
    <div class="ww-wpi-gauge-wrap">
      <svg class="ww-wpi-arc" viewBox="0 0 220 130" xmlns="http://www.w3.org/2000/svg">
        <!-- 背景弧 -->
        <path d="M 20 110 A 90 90 0 0 1 200 110" fill="none" stroke="#1a2535" stroke-width="18" stroke-linecap="round"/>
        <!-- 彩色區段 -->
        <path d="M 20 110 A 90 90 0 0 1 65 33"   fill="none" stroke="#00ff88" stroke-width="18" stroke-linecap="round" opacity=".35"/>
        <path d="M 65 33  A 90 90 0 0 1 110 20"  fill="none" stroke="#ffaa00" stroke-width="18" stroke-linecap="round" opacity=".35"/>
        <path d="M 110 20 A 90 90 0 0 1 155 33"  fill="none" stroke="#ff6600" stroke-width="18" stroke-linecap="round" opacity=".35"/>
        <path d="M 155 33 A 90 90 0 0 1 200 110" fill="none" stroke="#ff2222" stroke-width="18" stroke-linecap="round" opacity=".35"/>
        <!-- 動態指針弧（JS 控制 stroke-dasharray） -->
        <path d="M 20 110 A 90 90 0 0 1 200 110" fill="none" stroke="url(#wpiGrad)" stroke-width="18" stroke-linecap="round"
          stroke-dasharray="0 283" id="ww-wpi-arc-fill" style="transition:stroke-dasharray 1.5s ease"/>
        <defs>
          <linearGradient id="wpiGrad" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%"   stop-color="#00ff88"/>
            <stop offset="40%"  stop-color="#ffaa00"/>
            <stop offset="70%"  stop-color="#ff6600"/>
            <stop offset="100%" stop-color="#ff2222"/>
          </linearGradient>
        </defs>
        <!-- 指針 -->
        <line id="ww-wpi-needle" x1="110" y1="110" x2="110" y2="28"
          stroke="#ffffff" stroke-width="2.5" stroke-linecap="round"
          transform="rotate(-90, 110, 110)"
          style="transition:transform 0.1s"/>
        <circle cx="110" cy="110" r="5" fill="#ffffff" opacity=".9"/>
      </svg>

      <!-- 中心大數字 -->
      <div class="ww-wpi-center">
        <div class="ww-wpi-num" id="ww-wpi-num">0</div>
        <div class="ww-wpi-num-lbl">/ 100</div>
        <div class="ww-wpi-level" id="ww-wpi-level">COMPUTING...</div>
      </div>

      <!-- 刻度標籤 -->
      <div class="ww-wpi-scale">
        <span style="color:#00ff88">0<br><small>LOW</small></span>
        <span style="color:#ffaa00">50<br><small>MED</small></span>
        <span style="color:#ff2222">100<br><small>MAX</small></span>
      </div>

      <!-- 公式展示 -->
      <div class="ww-wpi-formula">
        WPI = 0.35<em>P</em> + 0.30<em>A</em> + 0.15<em>F</em> + 0.20<em>S</em>
      </div>
    </div>

    <!-- 右：三級警戒判斷 -->
    <div class="ww-wpi-alerts">
      <div class="ww-wpi-al-title">多重驗證警戒</div>

      <div class="ww-wpi-al-item" id="wpi-al-low">
        <div class="ww-wpi-al-dot low"></div>
        <div>
          <div class="ww-wpi-al-name">低度警戒</div>
          <div class="ww-wpi-al-cond">僅 Polymarket 波動</div>
          <div class="ww-wpi-al-sub">可能是政治口水，無需行動</div>
        </div>
        <div class="ww-wpi-al-status" id="wpi-al-low-status">—</div>
      </div>

      <div class="ww-wpi-al-item" id="wpi-al-med">
        <div class="ww-wpi-al-dot med"></div>
        <div>
          <div class="ww-wpi-al-name">中度警戒</div>
          <div class="ww-wpi-al-cond">市場波動 + 披薩指數上升</div>
          <div class="ww-wpi-al-sub">內部人員可能已開始加班</div>
        </div>
        <div class="ww-wpi-al-status" id="wpi-al-med-status">—</div>
      </div>

      <div class="ww-wpi-al-item" id="wpi-al-high">
        <div class="ww-wpi-al-dot high"></div>
        <div>
          <div class="ww-wpi-al-name">高度警戒</div>
          <div class="ww-wpi-al-cond">以上皆有 + 大量加油機出現</div>
          <div class="ww-wpi-al-sub">軍事行動即將執行</div>
        </div>
        <div class="ww-wpi-al-status" id="wpi-al-high-status">—</div>
      </div>

      <!-- 衝突條狀圖（移到這裡） -->
      <div class="ww-wpi-al-title" style="margin-top:1.2rem">各地區熱度</div>
      <?php
      $meters = [
        ['label'=>'俄烏衝突', 'val'=>78, 'cls'=>'r'],
        ['label'=>'美伊對峙', 'val'=>65, 'cls'=>'o'],
        ['label'=>'台海緊張', 'val'=>42, 'cls'=>'b'],
        ['label'=>'朝鮮半島', 'val'=>55, 'cls'=>'o'],
        ['label'=>'中東地區', 'val'=>70, 'cls'=>'r'],
        ['label'=>'南海爭議', 'val'=>35, 'cls'=>'g'],
      ];
      foreach ($meters as $m): ?>
      <div class="ww-meter-row" style="margin-bottom:.4rem">
        <div class="ww-ml"><?php echo esc_html($m['label']); ?></div>
        <div class="ww-mb"><div class="ww-mf <?php echo $m['cls']; ?>" data-w="<?php echo $m['val']; ?>"></div></div>
        <div class="ww-mp <?php echo $m['cls']; ?>"><?php echo $m['val']; ?>%</div>
      </div>
      <?php endforeach; ?>

    </div>
  </div>

  <!-- 底部：更新時間 + 免責 -->
  <div class="ww-wpi-footer">
    <span id="ww-wpi-updated">⟳ 計算中…</span>
    <span>·</span>
    <span>權重：Polymarket 35% · Aviation 30% · FIRMS 15% · Sentiment 20%</span>
    <span>·</span>
    <span style="color:rgba(255,255,255,.3)">僅供參考，非投資建議</span>
  </div>

</div><!-- /.ww-wpi-section -->

<!-- ══════════ MAIN 2-COL ══════════ -->
<!-- ══════════ PIZZINT 整合卡片 ══════════ -->
<div class="ww-card ww-card-pizza-bar" style="margin-bottom:1.2rem">

  <!-- 警報橫幅 -->
  <div class="ww-pizza-alert" id="ww-pizza-alert">
    <div class="ww-scan"></div>
    <div class="ww-alert-hdr">
      <div class="ww-alert-tag">⚠ PIZZINT ALERT</div>
      <div class="ww-alert-lvl" id="ww-alert-lvl">CRITICAL ANOMALY</div>
      <div class="ww-alert-ts" id="ww-alert-ts">--:--:-- UTC</div>
    </div>
    <div class="ww-alert-main" id="ww-alert-main">🍕 Pizza DEFCON 異常升高 — 歷史上此訊號出現後 2–48 小時內曾發生軍事行動</div>
    <div class="ww-alert-stats">
      <div class="ww-alert-stat"><div class="ww-alert-stat-lbl">觸發店家</div><div class="ww-alert-stat-val" id="ww-alert-shops">-- / 6</div></div>
      <div class="ww-alert-stat"><div class="ww-alert-stat-lbl">歷史符合率</div><div class="ww-alert-stat-val" style="color:var(--ww-o)">~76%</div></div>
    </div>
    <div class="ww-alert-bullets" id="ww-alert-bullets"></div>
    <div class="ww-alert-disclaimer">⚠ 偽陽性風險：財年截止日、演習、重大體育賽事皆可能觸發。建議結合 Polymarket 與 GDELT 數據交叉驗證。來源：<a href="https://www.pizzint.watch" target="_blank" rel="noopener" style="color:var(--ww-b)">pizzint.watch</a></div>
  </div>

  <!-- 頭部：DEFCON + 儀表 -->
  <div class="ww-pbi-header">
    <div class="ww-pbi-title-row">
      <div>
        <div class="ww-sec-title" style="margin-bottom:.2rem">🍕 Pentagon Pizza Index (PizzINT) <span style="font-family:'Share Tech Mono',monospace;font-size:.58rem;color:var(--ww-dim);font-weight:400">+ 🍺 酒吧反向指標</span></div>
        <div style="font-family:'Share Tech Mono',monospace;font-size:.6rem;color:var(--ww-dim)">KGB 代號 PIZZINT · Google Maps Popular Times · 每小時更新 · Pentagon / 白宮 / CIA HQ 3英里</div>
      </div>
      <div style="text-align:right;flex-shrink:0">
        <div style="font-family:'Orbitron',monospace;font-size:.55rem;color:var(--ww-dim);letter-spacing:2px">PIZZA DEFCON</div>
        <div style="font-family:'Orbitron',monospace;font-size:1.6rem;font-weight:700;color:var(--ww-g);line-height:1" id="ww-defcon-label">正常</div>
        <div style="font-family:'Share Tech Mono',monospace;font-size:.58rem;color:var(--ww-dim)" id="ww-defcon-sub">ELEVATED</div>
      </div>
    </div>

    <!-- DEFCON 量尺 -->
    <div class="ww-gauge-wrap" style="margin:.6rem 0">
      <div class="ww-gauge-labels">
        <span>異常指數</span>
        <span id="ww-gauge-pct" style="color:var(--ww-dim);font-weight:700">--%</span>
      </div>
      <div class="ww-gauge-track">
        <div class="ww-gauge-fill" id="ww-gauge-fill" style="width:0%">
          <div style="position:absolute;right:0;top:0;bottom:0;width:4px;background:#fff;opacity:.9;border-radius:0 2px 2px 0"></div>
        </div>
        <div class="ww-gauge-thr-el"></div>
        <div class="ww-gauge-thr-hi"></div>
      </div>
      <div class="ww-gauge-zone-row">
        <span>DEFCON 5<br><small>正常</small></span>
        <span>DEFCON 4<br><small>偏高</small></span>
        <span>DEFCON 3<br><small>警戒</small></span>
        <span>DEFCON 1<br><small>危機</small></span>
      </div>
    </div>

    <!-- 說明一行 -->
    <div style="font-family:'Share Tech Mono',monospace;font-size:.64rem;color:var(--ww-dim);line-height:1.6;margin-bottom:.6rem">
      冷戰時 KGB 監視五角大廈深夜外送作為早期預警。<strong style="color:var(--ww-b)">反向邏輯</strong>：酒吧冷清＋Pizza 爆滿 → 五角大廈沒在慶祝，他們在策劃。
    </div>

    <!-- Cross-signal 橫幅 -->
    <div id="ww-cross-signal" style="display:none;margin-bottom:.8rem;padding:.7rem 1rem;background:rgba(255,0,68,.08);border:1px solid rgba(255,0,68,.4);border-left:3px solid var(--ww-r);border-radius:0 4px 4px 0">
      <div style="font-family:'Orbitron',monospace;font-size:.63rem;color:var(--ww-r);letter-spacing:2px;margin-bottom:.3rem">🚨 CROSS-SIGNAL CONFIRMED</div>
      <div style="font-family:'Share Tech Mono',monospace;font-size:.62rem;color:var(--ww-text);line-height:1.6">
        Pizza 多店爆單 <strong style="color:var(--ww-r)">同時</strong> 酒吧驟冷 — 歷史最強早期預警雙重訊號
      </div>
      <div id="ww-cross-detail" style="font-family:'Share Tech Mono',monospace;font-size:.57rem;color:var(--ww-dim);margin-top:.3rem"></div>
    </div>
  </div>

  <!-- 主體 2 欄：左披薩 / 右酒吧 -->
  <div class="ww-pbi-grid">

    <!-- 左：披薩店 -->
    <div>
      <div class="ww-sec-title" style="font-size:.62rem">🍕 披薩店監控</div>
      <div class="ww-pizza-grid" id="ww-pizza-grid">
        <div style="grid-column:span 2;text-align:center;padding:.8rem;font-family:'Share Tech Mono',monospace;font-size:.68rem;color:var(--ww-dim)">載入中…</div>
      </div>
    </div>

    <!-- 右：酒吧 -->
    <div>
      <div class="ww-sec-title" style="font-size:.62rem">🍺 酒吧反向監控</div>
      <div class="ww-bar-grid" id="ww-bar-grid">
        <div style="grid-column:span 2;text-align:center;padding:.8rem;font-family:'Share Tech Mono',monospace;font-size:.68rem;color:var(--ww-dim)">載入中…</div>
      </div>
      <div style="margin-top:.4rem;font-family:'Share Tech Mono',monospace;font-size:.56rem;color:var(--ww-dim);line-height:1.5;padding:.4rem .6rem;background:rgba(0,170,255,.04);border-left:2px solid rgba(0,170,255,.2)">
        下班時段（ET 17:00-22:00）酒吧冷清 = 異常
      </div>
    </div>
  </div>

  <!-- 分隔線 -->
  <div style="margin:.8rem 0;border-top:1px solid var(--ww-border)"></div>

  <!-- 歷史事件（橫向捲動） -->
  <div class="ww-sec-title" style="font-size:.62rem;margin-bottom:.4rem">🕐 歷史 PizzINT 事件</div>
  <div class="ww-ph-scroll">
    <?php
    $history = [
      ['1983',       '格瑞那達入侵前夕',      '🍕 激增'],
      ['1990',       'CIA 單夜訂 21 個披薩',   '🍕×21'],
      ['1991',       '沙漠風暴 101 筆外送',    '🍕×101'],
      ['2003',       '伊拉克戰爭前',           '🍕 確認'],
      ['2011',       '擊斃賓拉登當夜',         '🍕🍕🍕'],
      ['2024-04-13', '伊朗無人機攻以',         '🍕 峰值'],
      ['2025-06-12', '以色列炸伊朗前 1h',      '🍕 確認'],
      ['2025-06-22', '川普宣布打擊伊朗',       '🍕 確認'],
      ['2026-01-02', '美軍馬杜羅行動前夜',     '🍕 確認'],
    ];
    foreach ($history as $h): ?>
    <div class="ww-ph-chip">
      <div class="ww-ph-chip-year"><?php echo esc_html($h[0]); ?></div>
      <div class="ww-ph-chip-event"><?php echo esc_html($h[1]); ?></div>
      <div class="ww-ph-chip-tag"><?php echo esc_html($h[2]); ?></div>
    </div>
    <?php endforeach; ?>
  </div>

  <div style="margin-top:.6rem;text-align:right">
    <a href="https://www.pizzint.watch" target="_blank" rel="noopener" style="font-family:'Share Tech Mono',monospace;font-size:.6rem;color:var(--ww-b)">→ pizzint.watch ↗</a>
  </div>

</div><!-- /.ww-card-pizza-bar -->

<!-- ══════════ POLYMARKET 獨立卡片 ══════════ -->
<div class="ww-card ww-card-b" style="margin-bottom:1.5rem">
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:.6rem;flex-wrap:wrap;gap:.5rem">
    <div class="ww-sec-title" style="margin:0">📊 Polymarket 戰爭預測市場</div>
    <div style="font-family:'Share Tech Mono',monospace;font-size:.6rem;color:var(--ww-dim);display:flex;gap:.8rem;align-items:center">
      <span style="color:var(--ww-g)">⟳ 每 5 分鐘</span>
      <span id="ww-poly-updated">上次更新：載入中…</span>
    </div>
  </div>
  <div style="font-family:'Share Tech Mono',monospace;font-size:.63rem;color:var(--ww-dim);margin-bottom:.8rem;padding:.5rem .7rem;background:rgba(0,170,255,.05);border-left:2px solid var(--ww-b)">
    真實資金下注 · 準確率 <span style="color:var(--ww-g)">94%</span>（事件前一個月）· 2025 年地緣政治交易量 <span style="color:var(--ww-o)">$33B+</span>
  </div>
  <div class="ww-poly-grid" id="ww-poly-list">
    <?php
    $poly = json_decode($poly_markets, true);
    foreach ($poly as $m):
      $pct   = intval($m['yes_pct']);
      $color = $pct >= 70 ? 'var(--ww-r)' : ($pct >= 40 ? 'var(--ww-o)' : 'var(--ww-b)');
      $cls   = $pct >= 70 ? 'danger' : ($pct >= 40 ? 'warn' : '');
      $vol   = $m['volume'] >= 1e6 ? '$'.number_format($m['volume']/1e6,1).'M' : ($m['volume'] >= 1e3 ? '$'.number_format($m['volume']/1e3,0).'K' : '');
      $url   = !empty($m['url']) ? esc_url($m['url']) : 'https://polymarket.com';
    ?>
    <a href="<?php echo $url; ?>" target="_blank" rel="noopener" style="text-decoration:none;color:inherit">
    <div class="ww-poly-item <?php echo $cls; ?>" onmouseover="this.style.borderLeftWidth='5px'" onmouseout="this.style.borderLeftWidth='3px'" style="cursor:pointer;transition:border-color .2s">
      <div class="ww-poly-q"><?php echo esc_html($m['question']); ?></div>
      <div class="ww-poly-bar-row">
        <span style="font-family:'Share Tech Mono',monospace;font-size:.6rem;color:var(--ww-dim);width:24px">YES</span>
        <div class="ww-poly-bar"><div class="ww-poly-fill" style="width:<?php echo $pct; ?>%;background:linear-gradient(90deg,rgba(0,0,20,.8),<?php echo $color; ?>)"></div></div>
        <div class="ww-poly-pct" style="color:<?php echo $color; ?>"><?php echo $pct; ?>%</div>
      </div>
      <div class="ww-poly-meta">
        <span><?php echo $vol ? '交易量 '.$vol : ''; ?></span>
        <span style="color:var(--ww-dim);font-size:.55rem">polymarket.com ↗</span>
      </div>
    </div>
    </a>
    <?php endforeach; ?>
  </div>
  <div style="margin-top:.8rem;padding:.6rem .8rem;background:rgba(0,170,255,.04);border:1px solid rgba(0,170,255,.15);font-family:'Share Tech Mono',monospace;font-size:.58rem;color:var(--ww-dim)">
    ⚠️ 僅供資訊參考，不構成投資建議。機率隨事件發展即時變動。
  </div>
</div><!-- /.poly card -->


<!-- ══════════ BOTTOM 3-COL ══════════ -->
<div class="ww-bottom-grid">

  <!-- 全球熱點 -->
  <div class="ww-card ww-card-r">
    <div class="ww-sec-title">全球熱點衝突</div>
    <?php
    $conflicts = [
      ['🇺🇦 俄烏戰爭',   '持續進行 · 第3年 · 前線膠著', 'crit'],
      ['🇮🇱 以巴/中東',  '加薩持續 · 伊朗代理人威脅',   'crit'],
      ['🇺🇸🇮🇷 美伊對峙','核談判失敗 · 軍事集結中',      'high'],
      ['🇸🇩 蘇丹內戰',   'RSF vs SAF · 人道危機',        'high'],
      ['🇰🇵 朝鮮半島',   '飛彈試射 · 北韓援俄',          'med'],
      ['🇨🇳🇹🇼 台海',    '軍演頻率升高 · 紅線試探',      'med'],
      ['🌊 南海爭議',     '菲律賓/越南/中國摩擦',         'low'],
    ];
    foreach ($conflicts as $c): ?>
    <div class="ww-conf-item">
      <div>
        <div class="ww-conf-name"><?php echo esc_html($c[0]); ?></div>
        <div class="ww-conf-sub"><?php echo esc_html($c[1]); ?></div>
      </div>
      <div class="ww-pill <?php echo $c[2]; ?>"><?php echo strtoupper($c[2]); ?></div>
    </div>
    <?php endforeach; ?>
  </div>

  <!-- OSINT 情報 -->
  <div class="ww-card ww-card-g">
    <div class="ww-sec-title">OSINT 情報訊號</div>
    <?php
    // OSINT 即時來源連結（非特定日期新聞，連結到可持續查閱的即時頁面）
    $signals = [
      ['🍕','PizzINT Watch：五角大廈周邊 Pizza 店即時人流監控','即時','pizzint.watch',     'https://www.pizzint.watch'],
      ['✈️','ADS-B Exchange：全球軍機即時追蹤（過濾後）',      '即時','ADS-B Exchange',   'https://globe.adsbexchange.com/?mil=1'],
      ['🛰️','NASA FIRMS：全球衝突區域衛星火點即時地圖',        '即時','NASA FIRMS',        'https://firms.modaps.eosdis.nasa.gov/map/'],
      ['📊','Polymarket：戰爭相關事件預測市場即時機率',         '即時','Polymarket',        'https://polymarket.com/markets/politics'],
      ['🏦','TradingView：黃金/油/VIX 避險指標走勢',           '即時','TradingView',       'https://www.tradingview.com/markets/currencies/quotes-gold/'],
    ];
    foreach ($signals as $s): ?>
    <a href="<?php echo esc_url($s[4]); ?>" target="_blank" rel="noopener" style="text-decoration:none;color:inherit;display:block">
    <div class="ww-sig-item" style="cursor:pointer;transition:background .2s" onmouseover="this.style.background='rgba(0,255,136,0.04)'" onmouseout="this.style.background=''">
      <div class="ww-sig-icon"><?php echo $s[0]; ?></div>
      <div>
        <div class="ww-sig-text"><?php echo esc_html($s[1]); ?></div>
        <div class="ww-sig-meta"><?php echo esc_html($s[2]); ?> · <span class="ww-sig-src"><?php echo esc_html($s[3]); ?> ↗</span></div>
      </div>
    </div>
    </a>
    <?php endforeach; ?>
  </div>

  <!-- 末日時鐘 -->
  <div class="ww-card ww-card-p">
    <div class="ww-sec-title">☢️ 末日時鐘 &amp; 核威脅</div>
    <div class="ww-doom-clock">23:58:30</div>
    <div class="ww-doom-lbl">距離午夜（核戰）僅剩 90 秒</div>
    <div class="ww-doom-track-row">
      <span>00:00</span>
      <div class="ww-doom-track">
        <div class="ww-doom-fill"></div>
        <div class="ww-doom-pin"></div>
      </div>
      <span>MIDNIGHT</span>
    </div>
    <div style="font-family:'Share Tech Mono',monospace;font-size:.68rem;color:var(--ww-dim);line-height:1.65;margin-bottom:.8rem">
      <span style="color:var(--ww-p)">2023年設定，史上最近</span>。俄烏核威脅 + AI 軍備競賽 + 氣候危機。由《原子科學家公報》設定。
    </div>
    <?php
    $nukes = [
      ['🇷🇺 俄羅斯核武威懾言論','crit'],
      ['🇨🇳 中國核彈頭快速擴張','high'],
      ['🇮🇷 伊朗接近武器級濃縮','high'],
      ['🇮🇳🇵🇰 印巴核對峙','med'],
      ['Polymarket 核武使用（2026）— 5%','med'],
    ];
    foreach ($nukes as $n): ?>
    <div class="ww-conf-item" style="margin-bottom:.4rem">
      <div class="ww-conf-name"><?php echo esc_html($n[0]); ?></div>
      <div class="ww-pill <?php echo $n[1]; ?>"><?php echo strtoupper($n[1]); ?></div>
    </div>
    <?php endforeach; ?>
  </div>

</div><!-- /.ww-bottom-grid -->

<!-- ══════════ RSS 即時戰爭新聞 ══════════ -->
<div style="margin:1.5rem auto 2.5rem;padding:1.4rem 1.5rem;background:#0d1b26;border:1px solid #1a3040;border-top:2px solid #00ff88;position:relative;">
  <span style="position:absolute;top:0;left:0;width:10px;height:10px;border-top:1px solid #00ff88;border-left:1px solid #00ff88;display:block;"></span>
  <span style="position:absolute;bottom:0;right:0;width:10px;height:10px;border-bottom:1px solid #00ff88;border-right:1px solid #00ff88;display:block;"></span>

  <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:.5rem;margin-bottom:1rem;padding-bottom:.8rem;border-bottom:1px solid #1a3040;">
    <div style="font-family:'Orbitron',monospace;font-size:.82rem;font-weight:700;color:#00ff88;letter-spacing:2px;display:flex;align-items:center;gap:.6rem;">
      📡 即時戰爭新聞
      <span style="width:7px;height:7px;border-radius:50%;background:#ff4444;display:inline-block;animation:ww-blink 1.2s ease-in-out infinite;"></span>
    </div>
    <div style="font-family:'Share Tech Mono',monospace;font-size:.63rem;color:#4a6070;">
      <span id="ww-news-count">載入中…</span> &nbsp;·&nbsp; <span id="ww-news-updated">--</span> &nbsp;·&nbsp; 每30分鐘更新
    </div>
  </div>

  <div id="ww-news-filters" style="display:flex;flex-wrap:wrap;gap:.4rem;margin-bottom:1.2rem;">
    <button class="wwnf" data-src="all"             style="font-family:'Share Tech Mono',monospace;font-size:.6rem;padding:.28rem .8rem;background:rgba(0,255,136,.08);border:1px solid #00ff88;color:#00ff88;cursor:pointer;letter-spacing:1px;">全部</button>
    <button class="wwnf" data-src="BBC World"        style="font-family:'Share Tech Mono',monospace;font-size:.6rem;padding:.28rem .8rem;background:#0a121e;border:1px solid #1a3040;color:#4a6070;cursor:pointer;letter-spacing:1px;">BBC</button>
    <button class="wwnf" data-src="Al Jazeera"       style="font-family:'Share Tech Mono',monospace;font-size:.6rem;padding:.28rem .8rem;background:#0a121e;border:1px solid #1a3040;color:#4a6070;cursor:pointer;letter-spacing:1px;">AJ</button>
    <button class="wwnf" data-src="DW News"          style="font-family:'Share Tech Mono',monospace;font-size:.6rem;padding:.28rem .8rem;background:#0a121e;border:1px solid #1a3040;color:#4a6070;cursor:pointer;letter-spacing:1px;">DW</button>
    <button class="wwnf" data-src="Guardian World"   style="font-family:'Share Tech Mono',monospace;font-size:.6rem;padding:.28rem .8rem;background:#0a121e;border:1px solid #1a3040;color:#4a6070;cursor:pointer;letter-spacing:1px;">Guardian</button>
    <button class="wwnf" data-src="Euromaidan Press" style="font-family:'Share Tech Mono',monospace;font-size:.6rem;padding:.28rem .8rem;background:#0a121e;border:1px solid #1a3040;color:#4a6070;cursor:pointer;letter-spacing:1px;">Euromaidan</button>
    <button class="wwnf" data-src="UK Defence Jnl"   style="font-family:'Share Tech Mono',monospace;font-size:.6rem;padding:.28rem .8rem;background:#0a121e;border:1px solid #1a3040;color:#4a6070;cursor:pointer;letter-spacing:1px;">UK Defence</button>
  </div>

  <div id="ww-news-grid" style="display:grid;grid-template-columns:repeat(3,1fr);gap:.9rem;">
    <div style="grid-column:1/-1;display:flex;align-items:center;justify-content:center;gap:.8rem;padding:2.5rem;font-family:'Share Tech Mono',monospace;font-size:.72rem;color:#4a6070;">
      <span style="width:14px;height:14px;border:2px solid #1a3040;border-top-color:#00ff88;border-radius:50%;animation:ww-spin 1s linear infinite;display:inline-block;flex-shrink:0;"></span>
      正在載入最新戰情新聞…
    </div>
  </div>

  <div style="display:flex;align-items:center;justify-content:space-between;margin-top:1rem;padding-top:.7rem;border-top:1px solid #1a3040;">
    <span style="font-family:'Share Tech Mono',monospace;font-size:.58rem;color:#2a4050;">來源：BBC · Al Jazeera · AP · Guardian · Euromaidan Press · UK Defence Journal</span>
    <button id="ww-news-more" onclick="wwNewsShowMore()" style="display:none;font-family:'Share Tech Mono',monospace;font-size:.6rem;padding:.3rem .9rem;background:transparent;border:1px solid #00ff88;color:#00ff88;cursor:pointer;letter-spacing:1px;">載入更多 ↓</button>
  </div>
</div>

<!-- ══════════ OSINT 進階三模組 ══════════ -->
<div class="ww-osint-grid">

  <!-- ✈️ A. 航空異常監控 -->
  <?php
  $avi = json_decode($avi_data, true);
  $sum = $avi['summary'];
  $anomPct = $sum['anomaly_pct'];
  $anomCol = $anomPct > 100 ? 'var(--ww-r)' : ($anomPct > 50 ? 'var(--ww-o)' : 'var(--ww-g)');
  ?>
  <div class="ww-card" style="border-top:2px solid #cc44ff">
    <div class="ww-osint-header">
      <span>✈️ &nbsp;航空異常監控 (AVI)</span>
      <span class="ww-osint-updated" id="ww-avi-updated">
        <?php echo $avi['updated'] ? '更新：'.esc_html($avi['updated']) : 'OpenSky Network'; ?>
      </span>
    </div>

    <!-- 計數器 3 格 -->
    <?php $avi_loading = !empty($avi['loading']); ?>
    <div class="ww-avi-counter">
      <div class="ww-avi-box">
        <div class="ww-avi-box-val" style="color:<?php echo $avi_loading?'var(--ww-dim)':'#cc44ff'; ?>"><?php echo $avi_loading?'--':$sum['tankers']; ?></div>
        <div class="ww-avi-box-lbl">加油機</div>
      </div>
      <div class="ww-avi-box">
        <div class="ww-avi-box-val" style="color:<?php echo $avi_loading?'var(--ww-dim)':'#ffaa00'; ?>"><?php echo $avi_loading?'--':$sum['awacs']; ?></div>
        <div class="ww-avi-box-lbl">預警機</div>
      </div>
      <div class="ww-avi-box">
        <div class="ww-avi-box-val" style="color:<?php echo $avi_loading?'var(--ww-dim)':'#00aaff'; ?>"><?php echo $avi_loading?'--':$sum['uav']; ?></div>
        <div class="ww-avi-box-lbl">偵察無人機</div>
      </div>
    </div>

    <!-- 7日趨勢 -->
    <div style="margin-bottom:.8rem;padding:.5rem .7rem;background:rgba(204,68,255,.06);border:1px solid rgba(204,68,255,.2);font-family:'Share Tech Mono',monospace;font-size:.65rem;color:var(--ww-dim)">
      <?php if ($avi_loading): ?>
      ⏳ 正在從 OpenSky Network 取得資料，首次約需 1-2 分鐘…
      <?php else: ?>
      過去 1 小時出動架次較 7 日均值
      <strong style="color:<?php echo $anomCol; ?>;font-size:.85rem"> +<?php echo $anomPct; ?>%</strong>
      &nbsp;·&nbsp; 7日均值 <?php echo $sum['baseline_7d']; ?> 架次/hr
      <?php endif; ?>
    </div>

    <!-- 即時機表 -->
    <div class="ww-avi-list">
      <?php if ($avi_loading || empty($avi['aircraft'])): ?>
      <div style="text-align:center;padding:1.2rem;font-family:'Share Tech Mono',monospace;font-size:.68rem;color:var(--ww-dim)">
        ⏳ 等待 OpenSky Network 資料…<br>
        <span style="font-size:.58rem">Cron 執行後自動更新（約每 30 分鐘）</span>
      </div>
      <?php else: ?>
      <?php foreach ($avi['aircraft'] as $ac):
        $roleMap = ['tanker'=>'tanker','awacs'=>'awacs','uav'=>'uav'];
        $dotCls  = $roleMap[$ac['role']] ?? 'unknown';
        $trendUp = strpos($ac['trend'],'+') === 0;
        $trendCls= $trendUp ? 'up' : 'down';
        $roleLabel = ['tanker'=>'加油機','awacs'=>'預警機','uav'=>'偵察機'][$ac['role']] ?? $ac['role'];
      ?>
      <div class="ww-avi-item">
        <div class="ww-avi-dot <?php echo $dotCls; ?>"></div>
        <div>
          <div style="font-size:.72rem;color:var(--ww-text)"><?php echo esc_html($ac['callsign']); ?> &nbsp;<span style="color:var(--ww-dim);font-size:.6rem"><?php echo esc_html($ac['type']); ?></span></div>
          <div class="ww-avi-type"><?php echo esc_html($ac['region']); ?> · <?php echo esc_html($roleLabel); ?> · <?php echo number_format($ac['alt_ft']); ?>ft</div>
        </div>
        <div class="ww-avi-trend <?php echo $trendCls; ?>"><?php echo esc_html($ac['trend']); ?></div>
      </div>
      <?php endforeach; ?>
      <?php endif; ?>
    </div>

    <!-- 圖例 -->
    <div class="ww-avi-legend">
      <span><i style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#cc44ff"></i> 加油機</span>
      <span><i style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#ffaa00"></i> 預警機</span>
      <span><i style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#00aaff"></i> 無人機</span>
    </div>
    <div style="margin-top:.6rem;text-align:right">
      <a href="https://globe.adsbexchange.com" target="_blank" rel="noopener" style="font-family:'Share Tech Mono',monospace;font-size:.58rem;color:var(--ww-b)">ADSB.Exchange ↗</a>
      &nbsp;·&nbsp;
      <a href="https://opensky-network.org" target="_blank" rel="noopener" style="font-family:'Share Tech Mono',monospace;font-size:.58rem;color:var(--ww-b)">OpenSky ↗</a>
    </div>
  </div>

  <!-- 🔥 B. 全球衝突熱點 -->
  <?php
  $firms = json_decode($firms_data, true);
  $fireDelta = $firms['fire_delta'];
  $fireDeltaCol = strpos($fireDelta,'+')===0 ? 'var(--ww-r)' : 'var(--ww-g)';
  ?>
  <div class="ww-card" style="border-top:2px solid var(--ww-r)">
    <div class="ww-osint-header">
      <span>🔥 &nbsp;衝突熱點 (FIRMS)</span>
      <span class="ww-osint-updated" id="ww-firms-updated">
        <?php echo $firms['updated'] ? '更新：'.esc_html($firms['updated']) : 'NASA FIRMS'; ?>
      </span>
    </div>

    <!-- 摘要 -->
    <?php $firms_loading = !empty($firms['loading']) || empty($firms['fire_24h']); ?>
    <div class="ww-fire-summary">
      <div class="ww-fire-box">
        <div class="ww-fire-val" style="color:<?php echo $firms_loading?'var(--ww-dim)':'var(--ww-r)'; ?>"><?php echo $firms_loading?'--':number_format($firms['fire_24h']); ?></div>
        <div class="ww-fire-lbl">24hr 衛星火點</div>
      </div>
      <div class="ww-fire-box">
        <div class="ww-fire-val" style="color:<?php echo $firms_loading?'var(--ww-dim)':$fireDeltaCol; ?>"><?php echo $firms_loading?'--':esc_html($fireDelta); ?></div>
        <div class="ww-fire-lbl">vs 7日均值</div>
      </div>
    </div>

    <!-- Live Feed -->
    <div class="ww-live-feed" id="ww-live-feed">
      <?php if ($firms_loading || empty($firms['events'])): ?>
      <div style="text-align:center;padding:1.2rem;font-family:'Share Tech Mono',monospace;font-size:.68rem;color:var(--ww-dim)">
        ⏳ 等待 NASA FIRMS 資料…<br>
        <span style="font-size:.58rem">Cron 執行後自動更新（約每 15 分鐘）</span>
      </div>
      <?php else: ?>
      <?php foreach ($firms['events'] as $ev):
        $typeMap = ['fire'=>'fire','air'=>'air','move'=>'move','cyber'=>'cyber'];
        $cls = $typeMap[$ev['type']] ?? '';
        $typeIcon = ['fire'=>'🔥','air'=>'✈️','move'=>'🚛','cyber'=>'💻'][$ev['type']] ?? '⚡';
      ?>
      <div class="ww-feed-item <?php echo $cls; ?>">
        <div class="ww-feed-time"><?php echo esc_html($ev['time']); ?></div>
        <div>
          <div class="ww-feed-text"><?php echo $typeIcon; ?> <strong><?php echo esc_html($ev['region']); ?></strong> — <?php echo esc_html($ev['text']); ?></div>
        </div>
      </div>
      <?php endforeach; ?>
      <?php endif; ?>
    </div>

    <!-- 事件類型 -->
    <div class="ww-event-types">
      <?php if (!$firms_loading && !empty($firms['event_types'])): ?>
      <?php
      $tagColors = ['砲擊/爆炸'=>'var(--ww-r)','部隊移動'=>'var(--ww-o)','網路攻擊'=>'var(--ww-p)','防空啟動'=>'var(--ww-b)'];
      foreach ($firms['event_types'] as $label => $pct):
        $col = $tagColors[$label] ?? 'var(--ww-dim)';
      ?>
      <span class="ww-event-tag" style="color:<?php echo $col; ?>;border-color:<?php echo $col; ?>;background:<?php echo $col; ?>22">
        <?php echo esc_html($label); ?> <?php echo $pct; ?>%
      </span>
      <?php endforeach; ?>
      <?php endif; ?>
    </div>
    <div style="margin-top:.6rem;text-align:right">
      <a href="https://firms.modaps.eosdis.nasa.gov/map/" target="_blank" rel="noopener" style="font-family:'Share Tech Mono',monospace;font-size:.58rem;color:var(--ww-b)">NASA FIRMS 即時地圖 ↗</a>
    </div>
    <!-- NASA FIRMS WMS 靜態衛星圖（新版端點格式） -->
    <a href="https://firms.modaps.eosdis.nasa.gov/map/" target="_blank" rel="noopener" style="display:block;margin-top:.8rem;text-decoration:none">
      <img
        src="https://firms.modaps.eosdis.nasa.gov/mapserver/wms/fires/a6f68613078dd3564264e6c72a298dcb/fires_viirs_snpp_24,fires_viirs_noaa20_24/triangle,triangle/3,2/255+50+50,255+180+0/?REQUEST=GetMap&WIDTH=600&HEIGHT=300&BBOX=-180,-90,180,90&version=1.1.1"
        alt="NASA FIRMS 全球即時火點"
        style="width:100%;height:auto;display:block;opacity:.85;border:1px solid rgba(255,68,68,.2)"
        onerror="this.parentElement.style.display='none';document.getElementById('ww-firms-fallback').style.display='block'"
      >
      <div style="font-family:'Share Tech Mono',monospace;font-size:.55rem;color:var(--ww-dim);margin-top:.3rem;text-align:center">
        🛰️ VIIRS S-NPP + NOAA-20 · 24hr · 全球 · 點擊開啟互動地圖 ↗
      </div>
    </a>
    <!-- 圖片載入失敗時的 fallback -->
    <a id="ww-firms-fallback" href="https://firms.modaps.eosdis.nasa.gov/map/" target="_blank" rel="noopener"
       style="display:none;margin-top:.8rem;padding:.8rem;background:rgba(255,68,68,.06);border:1px solid rgba(255,68,68,.25);text-align:center;text-decoration:none">
      <div style="font-size:1.2rem;margin-bottom:.3rem">🛰️</div>
      <div style="font-family:'Orbitron',monospace;font-size:.65rem;color:var(--ww-r);letter-spacing:2px">開啟 NASA FIRMS 即時火點圖</div>
      <div style="font-family:'Share Tech Mono',monospace;font-size:.58rem;color:var(--ww-dim);margin-top:.2rem">VIIRS S-NPP · 24hr · 全球 ↗</div>
    </a>
  </div>
  <?php $fin = json_decode($finance_data, true); ?>
  <div class="ww-card" style="border-top:2px solid var(--ww-g)">
    <div class="ww-osint-header">
      <span>💰 &nbsp;經濟避險指標 (FIN)</span>
      <span class="ww-osint-updated" id="ww-fin-updated">
        <?php echo $fin['updated'] ? '更新：'.esc_html($fin['updated']) : 'Yahoo Finance'; ?>
      </span>
    </div>

    <!-- 主要資產 2x2 -->
    <div class="ww-fin-grid">
      <?php foreach ($fin['assets'] as $a):
        $chgSign = $a['change'] > 0 ? '+' : '';
        $chgCls  = $a['change'] > 0 ? 'up' : 'down';
        $devPct  = $a['ma30'] > 0
          ? round(($a['price'] - $a['ma30']) / $a['ma30'] * 100, 1)
          : 0;
        $isAlert = abs($devPct) > 5;
      ?>
      <div class="ww-fin-box" <?php echo $isAlert ? 'style="border-color:'.($a['change']>0?'rgba(255,170,0,.4)':'rgba(0,255,136,.3)').'"' : ''; ?>>
        <div class="ww-fin-ticker"><?php echo esc_html($a['ticker']); ?></div>
        <?php $tzh=['GC=F'=>'黃金','BZ=F'=>'布倫特原油','USDCHF=X'=>'美元/瑞郎','^VIX'=>'恐慌指數'];
        if(isset($tzh[$a['ticker']])): ?><div class="ww-fin-ticker-zh" style="font-family:'Share Tech Mono',monospace;font-size:.58rem;color:#4a6070;opacity:.8;margin-bottom:.2rem;"><?php echo $tzh[$a['ticker']]; ?></div><?php endif; ?>
        <div class="ww-fin-price" style="color:<?php echo $a['change']>0?'var(--ww-o)':'var(--ww-g)'; ?>">
          <?php echo $a['ticker']==='USDCHF' ? number_format($a['price'],4) : number_format($a['price'],2); ?>
        </div>
        <div class="ww-fin-change <?php echo $chgCls; ?>"><?php echo $chgSign.$a['change']; ?>% 24h</div>
        <div style="font-family:'Share Tech Mono',monospace;font-size:.55rem;color:var(--ww-dim);margin-top:.2rem">
          30MA偏離 <?php echo ($devPct>=0?'+':'').$devPct; ?>%
          <?php echo abs($devPct)>5 ? '<span style="color:var(--ww-o)"> ⚠</span>' : ''; ?>
        </div>
      </div>
      <?php endforeach; ?>
    </div>

    <!-- 戰爭溢價 -->
    <div class="ww-fin-war-premium">
      ⛽ 油價戰爭溢價：當前布倫特較 30 日均價高出
      <strong style="color:var(--ww-o);font-size:.85rem"> +$<?php echo $fin['war_premium_oil']; ?>/bbl</strong>
      &nbsp;— 溢價超過 $8 通常代表市場已預期軍事行動
    </div>

    <!-- 軍工股 -->
    <div style="font-family:'Share Tech Mono',monospace;font-size:.6rem;color:var(--ww-dim);margin:.7rem 0 .3rem;letter-spacing:2px">DEFENSE STOCKS</div>
    <div class="ww-fin-stocks">
      <?php foreach ($fin['stocks'] as $s):
        $chgSign = $s['change'] > 0 ? '+' : '';
        $chgCls  = $s['change'] > 0 ? 'up' : 'down';
      ?>
      <div class="ww-fin-stock-item">
        <div class="ww-fin-stock-sym"><?php echo esc_html($s['sym']); ?></div>
        <div class="ww-fin-stock-name"><?php echo esc_html($s['name']); ?></div>
        <div class="ww-fin-stock-px"><?php echo number_format($s['price'],2); ?></div>
        <div class="ww-fin-stock-chg <?php echo $chgCls; ?>">
          <?php echo $chgSign.$s['change']; ?>%
          <?php echo $s['flag'] ? ' 🚨' : ''; ?>
        </div>
      </div>
      <?php endforeach; ?>
    </div>
    <div style="margin-top:.6rem;font-family:'Share Tech Mono',monospace;font-size:.57rem;color:var(--ww-dim)">
      🚨 = 無財報情況下異常漲幅，可能反映地緣政治張力
    </div>
    <div style="margin-top:.4rem;text-align:right">
      <a href="https://finance.yahoo.com" target="_blank" rel="noopener" style="font-family:'Share Tech Mono',monospace;font-size:.58rem;color:var(--ww-b)">Yahoo Finance ↗</a>
    </div>
  </div>

</div><!-- /.ww-osint-grid -->

<!-- ══ 相關性分析區塊 ══════════════════════════════════════ -->
<div class="ww-corr-wrap" style="background:#0d1b26;border:1px solid #1a3040;border-top:2px solid #ff8800;padding:1.4rem 1.5rem 1.4rem;margin-bottom:1.5rem;position:relative;">
  <span style="position:absolute;top:0;left:0;width:10px;height:10px;border-top:1px solid #00ff88;border-left:1px solid #00ff88;display:block;"></span>
  <span style="position:absolute;bottom:0;right:0;width:10px;height:10px;border-bottom:1px solid #00ff88;border-right:1px solid #00ff88;display:block;"></span>
  <div class="ww-corr-chart-box">
    <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:.4rem;margin-bottom:.8rem;">
      <div style="font-family:'Orbitron',monospace;font-size:.82rem;font-weight:700;color:#ff8800;letter-spacing:2px;">📈 金融市場 × WPI 相關性分析</div>
      <div style="font-family:'Share Tech Mono',monospace;font-size:.62rem;color:#4a6070;">資料每 10 分鐘更新 &nbsp;·&nbsp; <span id="corr-sample-count" style="color:#c8d8e0;">載入中…</span></div>
    </div>
    <div class="ww-corr-canvas-wrap" style="height:220px;margin-bottom:1.2rem;position:relative;background:#080f18;border:1px solid #1a3040;">
      <div id="corr-loading" style="display:flex;align-items:center;justify-content:center;height:100%;font-family:'Share Tech Mono',monospace;font-size:.7rem;color:#4a6070;text-align:center;padding:0 2rem;">⏳ 歷史數據累積中，數筆後自動顯示趨勢線…</div>
      <canvas id="corr-chart" style="display:none;width:100%;height:100%;"></canvas>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:.8rem;margin-bottom:1.2rem;">
      <div style="background:#080f18;border:1px solid #1a3040;border-top:2px solid #ffaa00;padding:.9rem 1rem;">
        <div style="font-family:'Share Tech Mono',monospace;font-size:.58rem;color:#4a6070;letter-spacing:1px;text-transform:uppercase;margin-bottom:.5rem;">🥇 黃金價格 × WPI</div>
        <div id="corr-gold" style="font-family:'Orbitron',monospace;font-size:.9rem;color:#c8d8e0;">累積中…</div>
      </div>
      <div style="background:#080f18;border:1px solid #1a3040;border-top:2px solid #00aaff;padding:.9rem 1rem;">
        <div style="font-family:'Share Tech Mono',monospace;font-size:.58rem;color:#4a6070;letter-spacing:1px;text-transform:uppercase;margin-bottom:.5rem;">🛢️ 布倫特油價 × WPI</div>
        <div id="corr-oil" style="font-family:'Orbitron',monospace;font-size:.9rem;color:#c8d8e0;">累積中…</div>
      </div>
      <div style="background:#080f18;border:1px solid #1a3040;border-top:2px solid #66bb6a;padding:.9rem 1rem;">
        <div style="font-family:'Share Tech Mono',monospace;font-size:.58rem;color:#4a6070;letter-spacing:1px;text-transform:uppercase;margin-bottom:.5rem;">⛽ 油價戰爭溢價 × WPI</div>
        <div id="corr-prem" style="font-family:'Orbitron',monospace;font-size:.9rem;color:#c8d8e0;">累積中…</div>
      </div>
    </div>
    <div style="font-family:'Share Tech Mono',monospace;font-size:.65rem;color:#4a6070;padding:.7rem 1rem;background:#080f18;border:1px solid #1a3040;border-left:2px solid #ff8800;line-height:1.7;">
      <strong style="color:#ff8800;">如何解讀：</strong> 相關係數 r 介於 -1 到 +1。
      <strong style="color:#ff4444;">|r| ≥ 0.7</strong> 為強相關；
      <strong style="color:#ff8800;">0.4–0.7</strong> 為中度相關；
      <strong style="color:#4a6070;">|r| &lt; 0.4</strong> 為弱相關。
      &nbsp;·&nbsp; 資料來源：Stooq / Yahoo Finance · WPI 本地計算 · 最多保留 90 筆（約 15 小時）
    </div>
  </div>
</div>



<!-- 免責聲明 -->
<div class="ww-disclaimer">
  ⚠️ 本網站資訊僅供研究與觀察用途，不構成任何投資、軍事或政策建議。
  Pizza 指數存在「偽陽性」風險；Polymarket 機率會隨時間實時變動。
</div>

</div><!-- /.ww-wrap -->

<!-- FOOTER -->
<div class="ww-footer">
  WARWATCH 戰爭預測情報中心 &nbsp;|&nbsp;
  數據來源：Polymarket Gamma API · @PenPizzaReport · pizzint.watch · Bulletin of Atomic Scientists &nbsp;|&nbsp;
  非投資建議 &nbsp;|&nbsp;
  <a href="<?php echo esc_url(home_url('/')); ?>" style="color:var(--ww-dim)">← 回首頁</a>
</div>

</div><!-- /#warwatch-page -->

<!-- WARWATCH JS -->
<?php
$ww_js = get_template_directory() . '/js/warwatch.js';
$ww_ver = file_exists($ww_js) ? filemtime($ww_js) : time();
?>
<script src="<?php echo get_template_directory_uri(); ?>/js/warwatch.js?v=<?php echo $ww_ver; ?>" defer></script>

<?php wp_footer(); ?>
</body>
</html>
<?php
/**
 * ══════════════════════════════════════════════════════════
 * WP CRON — 每小時自動更新 Polymarket 數據（加在 functions.php）
 * ══════════════════════════════════════════════════════════
 * 複製以下程式碼到你的佈景主題 functions.php：
 *
 * // 每小時抓取 Polymarket 並儲存到 WP Options
 * add_action('ww_fetch_polymarket', 'ww_cron_fetch_polymarket');
 * function ww_fetch_polymarket_schedule() {
 *   if (!wp_next_scheduled('ww_fetch_polymarket')) {
 *     wp_schedule_event(time(), 'hourly', 'ww_fetch_polymarket');
 *   }
 * }
 * add_action('wp', 'ww_fetch_polymarket_schedule');
 *
 * function ww_cron_fetch_polymarket() {
 *   $response = wp_remote_get('https://gamma-api.polymarket.com/markets?active=true&limit=200');
 *   if (is_wp_error($response)) return;
 *   $body = json_decode(wp_remote_retrieve_body($response), true);
 *   if (!is_array($body)) return;
 *   $war_kw = ['war','strike','attack','ceasefire','nuclear','Iran','Taiwan','Ukraine','Korea'];
 *   $filtered = array_filter($body, function($m) use ($war_kw) {
 *     $q = strtolower(($m['question']??'').' '.($m['description']??''));
 *     foreach ($war_kw as $kw) { if (str_contains($q, $kw)) return true; }
 *     return false;
 *   });
 *   usort($filtered, fn($a,$b) => floatval($b['volume']??0) <=> floatval($a['volume']??0));
 *   $filtered = array_slice($filtered, 0, 8);
 *   $result = array_map(function($m) {
 *     $yes_price = 0;
 *     foreach (($m['outcomes']??[]) as $o) {
 *       if (strtolower($o['name']??'')==='yes') $yes_price = floatval($o['price']??0);
 *     }
 *     return ['question'=>$m['question'], 'yes_pct'=>round($yes_price*100), 'volume'=>floatval($m['volume']??0)];
 *   }, array_values($filtered));
 *   update_option('ww_poly_markets', json_encode($result));
 * }
 */
?><style>
.entry-header,.ast-page-title-bar,.ast-breadcrumbs-wrapper,
.ast-above-header-wrap,.ast-below-header-wrap,.page-title-bar,
h1.entry-title,.page-header { display:none !important; }
</style>

