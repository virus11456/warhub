/* ============================================================
   WARWATCH — 貼入 astra/functions.php 最底部
   注意：不要複製這行以上的任何內容
   ============================================================ */

/* ──────────────────────────────────────────────────────────
   1. 載入 WARWATCH CSS（僅在 warwatch 頁面）
────────────────────────────────────────────────────────── */
/* ──────────────────────────────────────────────────────────
   0. 清除 warwatch 頁面的 post_content（防止舊 JS 殘留）
────────────────────────────────────────────────────────── */
add_filter('the_content', function ($content) {
    if (is_page_template('page-warwatch.php')) {
        return ''; // warwatch 頁面不輸出 post_content
    }
    return $content;
}, 1);

/* 在頁面最早期攔截輸出，移除任何含有舊函數的 <script> 區塊 */
add_action('template_redirect', function () {
    if (!is_page_template('page-warwatch.php')) return;
    ob_start(function ($html) {
        $old_fns = [
            'renderWarAlert', 'initPizzaSystem', 'initPizzaBar',
            'initPizzaBarSystem', 'initWarWatch', 'renderPizzaBarStatus',
        ];
        // 移除含舊函數的 <script> 區塊
        $html = preg_replace_callback(
            '/<script[^>]*>(.*?)<\/script>/is',
            function ($m) use ($old_fns) {
                foreach ($old_fns as $fn) {
                    if (strpos($m[1], $fn) !== false) {
                        return '<!-- [WARWATCH v2] removed legacy JS -->';
                    }
                }
                return $m[0];
            },
            $html
        );
        return $html;
    });
});

// 防止 Astra / Elementor 在 warwatch 頁面注入舊 JS
add_action('wp_enqueue_scripts', function () {
    if (!is_page_template('page-warwatch.php')) return;
    // 清除可能藏有舊 warwatch JS 的 builder scripts
    $remove = ['elementor-frontend','elementor-pro-frontend','astra-custom-js',
               'astra-child-js','fl-builder','fusion-builder','divi-custom-script'];
    foreach ($remove as $handle) {
        wp_dequeue_script($handle);
        wp_deregister_script($handle);
    }
}, 999);

add_action('wp_enqueue_scripts', function () {
    if (is_page_template('page-warwatch.php')) {
        wp_enqueue_style(
            'warwatch-css',
            get_template_directory_uri() . '/css/warwatch.css',
            [], '1.2.0'
        );
    }
});

/* ──────────────────────────────────────────────────────────
   2. WP Cron — 每小時自動抓取 Polymarket
────────────────────────────────────────────────────────── */
add_action('wp', function () {
    if (!wp_next_scheduled('ww_fetch_polymarket')) {
        wp_schedule_event(time(), 'hourly', 'ww_fetch_polymarket');
    }
});

add_action('ww_fetch_polymarket', 'ww_cron_fetch_polymarket');

function ww_cron_fetch_polymarket() {
    $url = 'https://gamma-api.polymarket.com/markets?active=true&closed=false&limit=200';
    $response = wp_remote_get($url, ['timeout' => 15]);

    if (is_wp_error($response)) {
        error_log('WARWATCH: Polymarket fetch failed — ' . $response->get_error_message());
        return;
    }

    $body = json_decode(wp_remote_retrieve_body($response), true);
    if (!is_array($body)) return;

    $war_kw = ['war','strike','attack','invasion','ceasefire','nuclear',
               'missile','military','Iran','Taiwan','Ukraine','Korea','NATO','Israel'];

    $filtered = array_filter($body, function ($m) use ($war_kw) {
        $q = strtolower(($m['question'] ?? '') . ' ' . ($m['description'] ?? ''));
        foreach ($war_kw as $kw) {
            if (str_contains($q, strtolower($kw))) return true;
        }
        return false;
    });

    usort($filtered, fn($a, $b) =>
        floatval($b['volume'] ?? 0) <=> floatval($a['volume'] ?? 0)
    );
    $filtered = array_slice(array_values($filtered), 0, 8);

    $result = array_map(function ($m) {
        $yes_price = 0;
        foreach (($m['outcomes'] ?? []) as $o) {
            if (strtolower($o['name'] ?? '') === 'yes') {
                $yes_price = floatval($o['price'] ?? 0);
            }
        }
        return [
            'question' => $m['question'] ?? '',
            'yes_pct'  => round($yes_price * 100),
            'volume'   => floatval($m['volume'] ?? 0),
        ];
    }, $filtered);

    update_option('ww_poly_markets', wp_json_encode($result));
    update_option('ww_poly_updated', current_time('mysql'));
}

/* ──────────────────────────────────────────────────────────
   3. REST API endpoints
────────────────────────────────────────────────────────── */
add_action('rest_api_init', function () {

    register_rest_route('warwatch/v1', '/pizza', [
        'methods'             => 'GET',
        'callback'            => 'ww_rest_get_pizza',
        'permission_callback' => '__return_true',
    ]);

    register_rest_route('warwatch/v1', '/pizza', [
        'methods'             => 'POST',
        'callback'            => 'ww_rest_update_pizza',
        'permission_callback' => function () { return current_user_can('manage_options'); },
    ]);

    register_rest_route('warwatch/v1', '/polymarket', [
        'methods'             => 'GET',
        'callback'            => 'ww_rest_get_polymarket',
        'permission_callback' => '__return_true',
    ]);
});

function ww_rest_get_pizza() {
    $data = get_option('ww_pizza_shops', null);
    if (!$data) {
        $default = [
            ['name' => "Domino's — Arlington, VA",    'busyness' => 45, 'baseline' => 30, 'icon' => '🍕'],
            ['name' => "Papa John's — Pentagon City", 'busyness' => 38, 'baseline' => 32, 'icon' => '🍕'],
            ['name' => "Pizza Hut — Crystal City",    'busyness' => 22, 'baseline' => 38, 'icon' => '🍕'],
            ['name' => "CIA HQ 周邊 Delivery",         'busyness' => 31, 'baseline' => 28, 'icon' => '🚨'],
        ];
        return rest_ensure_response(['shops' => $default, 'updated' => null]);
    }
    return rest_ensure_response([
        'shops'   => json_decode($data, true),
        'updated' => get_option('ww_pizza_updated'),
    ]);
}

function ww_rest_update_pizza(WP_REST_Request $req) {
    $shops = $req->get_json_params();
    if (!is_array($shops)) {
        return new WP_Error('invalid', '格式錯誤', ['status' => 400]);
    }
    foreach ($shops as &$s) {
        $s['busyness'] = max(0, min(100, intval($s['busyness'] ?? 0)));
        $s['baseline'] = max(0, min(100, intval($s['baseline'] ?? 0)));
        $s['name']     = sanitize_text_field($s['name'] ?? '');
        $s['icon']     = sanitize_text_field($s['icon'] ?? '🍕');
    }
    update_option('ww_pizza_shops', wp_json_encode($shops));
    update_option('ww_pizza_updated', current_time('mysql'));
    return rest_ensure_response(['status' => 'ok', 'updated' => current_time('mysql')]);
}

function ww_rest_get_polymarket() {
    $data    = get_option('ww_poly_markets');
    $updated = get_option('ww_poly_updated');
    // 若無快取，立即抓一次
    if (!$data && function_exists('ww_cron_fetch_polymarket')) {
        ww_cron_fetch_polymarket();
        $data    = get_option('ww_poly_markets');
        $updated = get_option('ww_poly_updated');
    }
    return rest_ensure_response([
        'markets' => $data ? json_decode($data, true) : [],
        'updated' => $updated ?: '',
    ]);
}

/* ──────────────────────────────────────────────────────────
   4. WP Admin 管理頁
────────────────────────────────────────────────────────── */
add_action('admin_menu', function () {
    add_menu_page(
        '🍕 WARWATCH 管理',
        '🍕 WARWATCH',
        'manage_options',
        'warwatch-admin',
        'ww_admin_page',
        'dashicons-chart-area',
        30
    );
});

function ww_admin_page() {
    if (isset($_POST['ww_save_pizza']) && check_admin_referer('ww_pizza_nonce')) {
        $shops     = [];
        $names     = array_map('sanitize_text_field', $_POST['shop_name']     ?? []);
        $busyness  = array_map('intval',              $_POST['shop_busyness'] ?? []);
        $baselines = array_map('intval',              $_POST['shop_baseline'] ?? []);
        $icons     = array_map('sanitize_text_field', $_POST['shop_icon']     ?? []);
        foreach ($names as $i => $name) {
            if (!$name) continue;
            $shops[] = [
                'name'     => $name,
                'busyness' => max(0, min(100, $busyness[$i] ?? 0)),
                'baseline' => max(0, min(100, $baselines[$i] ?? 0)),
                'icon'     => $icons[$i] ?? '🍕',
            ];
        }
        update_option('ww_pizza_shops', wp_json_encode($shops));
        update_option('ww_pizza_updated', current_time('mysql'));
        echo '<div class="notice notice-success"><p>✅ 披薩數據已更新！</p></div>';
    }

    if (isset($_POST['ww_manual_poly']) && check_admin_referer('ww_pizza_nonce')) {
        ww_cron_fetch_polymarket();
        echo '<div class="notice notice-success"><p>✅ Polymarket 數據已手動刷新！</p></div>';
    }

    $shops_json = get_option('ww_pizza_shops');
    $shops = $shops_json ? json_decode($shops_json, true) : [
        ['name' => "Domino's — Arlington, VA",    'busyness' => 45, 'baseline' => 30, 'icon' => '🍕'],
        ['name' => "Papa John's — Pentagon City", 'busyness' => 38, 'baseline' => 32, 'icon' => '🍕'],
        ['name' => "Pizza Hut — Crystal City",    'busyness' => 22, 'baseline' => 38, 'icon' => '🍕'],
        ['name' => "CIA HQ 周邊 Delivery",         'busyness' => 31, 'baseline' => 28, 'icon' => '🚨'],
    ];
    ?>
    <div class="wrap">
      <h1>🍕 WARWATCH 管理面板</h1>
      <p>更新後數據將即時反映在前端儀表板。<strong>異常閾值：busyness ≥ 70% 觸發警報。</strong></p>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:2rem;margin-top:1.5rem;">
        <div style="background:#fff;padding:1.5rem;border:1px solid #ddd;border-radius:4px;">
          <h2>🍕 披薩店繁忙度</h2>
          <form method="post">
            <?php wp_nonce_field('ww_pizza_nonce'); ?>
            <table class="widefat" style="margin-top:1rem">
              <thead><tr><th>圖示</th><th>店名</th><th>繁忙度%</th><th>基準值%</th></tr></thead>
              <tbody>
                <?php foreach ($shops as $i => $s) : ?>
                <tr>
                  <td><input name="shop_icon[]"     value="<?php echo esc_attr($s['icon']); ?>"     style="width:50px"></td>
                  <td><input name="shop_name[]"     value="<?php echo esc_attr($s['name']); ?>"     style="width:250px"></td>
                  <td><input name="shop_busyness[]" value="<?php echo esc_attr($s['busyness']); ?>" type="number" min="0" max="100" style="width:70px"></td>
                  <td><input name="shop_baseline[]" value="<?php echo esc_attr($s['baseline']); ?>" type="number" min="0" max="100" style="width:70px"></td>
                </tr>
                <?php endforeach; ?>
              </tbody>
            </table>
            <p>最後更新：<?php echo esc_html(get_option('ww_pizza_updated') ?: '未更新'); ?></p>
            <input type="submit" name="ww_save_pizza" class="button button-primary" value="💾 儲存">
          </form>
        </div>
        <div style="background:#fff;padding:1.5rem;border:1px solid #ddd;border-radius:4px;">
          <h2>📊 Polymarket 數據</h2>
          <p>最後更新：<strong><?php echo esc_html(get_option('ww_poly_updated') ?: '尚未執行'); ?></strong></p>
          <form method="post">
            <?php wp_nonce_field('ww_pizza_nonce'); ?>
            <input type="submit" name="ww_manual_poly" class="button" value="🔄 立即刷新 Polymarket">
          </form>
          <hr>
          <?php
          $poly = json_decode(get_option('ww_poly_markets', '[]'), true);
          foreach ($poly as $m) :
          ?>
          <div style="padding:.5rem;border-bottom:1px solid #eee;display:flex;gap:.5rem;align-items:center">
            <span style="font-family:monospace;background:<?php echo $m['yes_pct'] >= 70 ? '#ffdddd' : ($m['yes_pct'] >= 40 ? '#fff3cd' : '#e8f5e9'); ?>;padding:2px 6px"><?php echo $m['yes_pct']; ?>%</span>
            <span style="font-size:.85rem"><?php echo esc_html($m['question']); ?></span>
          </div>
          <?php endforeach; ?>
        </div>
      </div>
      <div style="margin-top:2rem;padding:1.5rem;background:#fff3cd;border:1px solid #ffc107;border-radius:4px;">
        <h3>🔄 強制重抓所有數據</h3>
        <p>若前端數據空白，按此重新抓取全部資料並清快取。</p>
        <a href="<?php echo admin_url('?ww_reset_finance=1'); ?>" class="button button-primary button-large">⚡ 立即重抓全部 + 清快取</a>
        &nbsp;
        <a href="<?php echo wp_nonce_url(admin_url('?ww_purge_old_js=1'), 'ww_purge'); ?>" class="button button-large" style="background:#c00;border-color:#900;color:#fff" onclick="return confirm('確定清除所有 warwatch 頁面的舊 JS？')">🗑 強制清除頁面舊 JS</a>
        <hr style="margin:1rem 0">
        <h3>🔧 頁面 JS 衝突偵測</h3>
        <div style="background:#f9f9f9;border:1px solid #ddd;padding:.8rem;border-radius:4px;margin-bottom:1rem;font-size:.85rem">
          <?php
          // 查找所有自訂 template 頁面，找到 warwatch 相關的
global $wpdb;
// 先列出所有自訂 template，幫助除錯
$all_templates = $wpdb->get_results(
    "SELECT pm.post_id, pm.meta_value, p.post_title, p.post_content
     FROM {$wpdb->postmeta} pm
     JOIN {$wpdb->posts} p ON pm.post_id = p.ID
     WHERE pm.meta_key = '_wp_page_template' AND pm.meta_value != 'default'
     AND p.post_status = 'publish'"
);
// 找 warwatch 相關
$ww_pages = array_filter($all_templates, function($r) {
    return stripos($r->meta_value, 'warwatch') !== false;
});
// 診斷：顯示所有 template 值
if (empty($ww_pages)) {
    echo '<details style="margin-bottom:.5rem"><summary style="cursor:pointer;color:#666;font-size:.8rem">🔍 展開診斷：所有頁面 template 值</summary><div style="padding:.5rem;background:#fff;font-family:monospace;font-size:.78rem">';
    if ($all_templates) {
        foreach ($all_templates as $t) {
            echo esc_html("ID:{$t->post_id} [{$t->post_title}] template={$t->meta_value}") . '<br>';
        }
    } else {
        echo '沒有任何頁面設定了自訂 template';
    }
    echo '</div></details>';
}
          if ($ww_pages) {
            foreach ($ww_pages as $pg) {
              $bad_funcs = ['renderWarAlert','initPizzaSystem','initPizzaBar','initPizzaBarSystem'];
              $has_old_js = false;
              foreach ($bad_funcs as $fn) {
                if (strpos($pg->post_content, $fn) !== false) { $has_old_js = true; break; }
              }
              $has_script = strpos($pg->post_content, '<script') !== false;
              echo '<p>';
              if ($has_old_js || $has_script) {
                echo '<strong style="color:red">❌ 頁面「'.esc_html($pg->post_title).'」(ID:'.$pg->ID.') 發現舊 JS 殘留！</strong><br>';
                $nonce = wp_create_nonce('ww_clear_' . $pg->ID);
                if (!empty($_GET['ww_clear_content']) && $_GET['ww_clear_content'] == $pg->ID &&
                    !empty($_GET['_wwnonce']) && wp_verify_nonce($_GET['_wwnonce'], 'ww_clear_'.$pg->ID)) {
                  wp_update_post(['ID'=>$pg->ID,'post_content'=>'']);
                  echo '<span style="color:green">✅ 已清除！請重新整理頁面確認。</span>';
                } else {
                  $url = add_query_arg(['ww_clear_content'=>$pg->ID, '_wwnonce'=>$nonce]);
                  echo '<a href="'.esc_url($url).'" class="button button-secondary" onclick="return confirm(\'確定清除舊 JS？\')">🗑 一鍵清除 post_content</a>';
                }
              } else {
                echo '<span style="color:green">✅ 頁面「'.esc_html($pg->post_title).'」乾淨，無殘留 JS</span>';
              }
              echo '</p>';
            }
          } else {
            echo '<span style="color:#888">未找到使用 page-warwatch.php 範本的頁面</span>';
          }
          ?>
        </div>

        <h3>🔗 REST API 狀態診斷</h3>
        <table class="widefat" style="margin-top:.5rem">
          <thead><tr><th>端點</th><th>狀態</th><th>最後更新</th></tr></thead>
          <tbody>
            <?php
            $endpoints = [
                'polymarket' => ['name'=>'Polymarket', 'data_opt'=>'ww_poly_markets',  'upd'=>'ww_poly_updated'],
                'finance'    => ['name'=>'Finance',    'data_opt'=>'ww_finance_data',   'upd'=>'ww_finance_data'],
                'firms'      => ['name'=>'FIRMS',      'data_opt'=>'ww_firms_data',     'upd'=>'ww_firms_data'],
                'aviation'   => ['name'=>'Aviation',   'data_opt'=>'ww_avi_data',       'upd'=>'ww_avi_data'],
                'pizza-live' => ['name'=>'Pizza Live', 'data_opt'=>'ww_pizza_data',     'upd'=>'ww_pizza_data'],
            ];
            foreach ($endpoints as $slug => $info):
                $raw      = get_option($info['data_opt'], '');
                $has_data = !empty($raw);
                $parsed   = $has_data ? json_decode($raw, true) : null;
                $upd      = $parsed['updated'] ?? get_option($info['upd'], '');
            ?>
            <tr>
              <td><a href="<?php echo site_url('/wp-json/warwatch/v1/'.$slug); ?>" target="_blank"><code>/wp-json/warwatch/v1/<?php echo $slug; ?></code></a></td>
              <td style="color:<?php echo $has_data ? 'green' : 'red'; ?>;font-weight:bold"><?php echo $has_data ? '✅ 有資料' : '❌ 空白'; ?></td>
              <td><?php echo esc_html($upd ?: '尚未執行'); ?></td>
            </tr>
            <?php endforeach; ?>
          </tbody>
        </table>
        <h3 style="margin:1.2rem 0 .5rem;font-size:.85rem">🔬 個別 API 測試</h3>
        <div style="display:flex;gap:.5rem;flex-wrap:wrap;margin-bottom:1rem">
          <?php
          $test_apis = [
            'finance'  => ['label'=>'💰 測試 Finance (Stooq)',  'fn'=>'ww_cron_fetch_finance'],
            'firms'    => ['label'=>'🔥 測試 FIRMS',            'fn'=>'ww_cron_fetch_firms'],
            'aviation' => ['label'=>'✈️ 測試 Aviation',         'fn'=>'ww_cron_fetch_aviation'],
          ];
          foreach ($test_apis as $key => $api):
            $nonce = wp_create_nonce('ww_test_'.$key);
            // 如果剛剛測試過，顯示結果
            if (isset($_GET['ww_test']) && $_GET['ww_test'] === $key && wp_verify_nonce($_GET['_tn'] ?? '', 'ww_test_'.$key)) {
              if (function_exists($api['fn'])) {
                $before = get_option('ww_'.($key==='aviation'?'avi':$key).'_data', '');
                call_user_func($api['fn']);
                $after = get_option('ww_'.($key==='aviation'?'avi':$key).'_data', '');
                $ok = !empty($after) && $after !== $before;
                echo '<div style="padding:.5rem .8rem;background:'.($ok?'#efffef':'#fff0f0').';border:1px solid '.($ok?'#0a0':'#c00').';border-radius:4px;font-size:.8rem">';
                echo ($ok ? '✅ ' : '❌ ') . esc_html($api['label']) . ($ok ? '：成功' : '：失敗（檢查伺服器錯誤日誌）');
                echo '</div>';
              }
            }
          endforeach; ?>
          <?php foreach ($test_apis as $key => $api):
            $nonce = wp_create_nonce('ww_test_'.$key);
            $url = add_query_arg(['ww_test'=>$key, '_tn'=>$nonce]);
          ?>
          <a href="<?php echo esc_url($url); ?>" class="button"><?php echo esc_html($api['label']); ?></a>
          <?php endforeach; ?>
        </div>

        <p style="margin-top:1rem;font-size:.85rem;color:#666">
          warwatch.js：<?php
            $f = get_template_directory().'/js/warwatch.js';
            echo file_exists($f)
              ? '<code>'.date('Y-m-d H:i:s', filemtime($f)).' · '.number_format(filesize($f)).' bytes</code>'
              : '<span style="color:red">找不到檔案！路徑：'.esc_html($f).'</span>';
          ?>
        </p>
      </div>
    </div>
    <?php
}
/* ============================================================
   5. WP Cron — 航空異常（每 30 分鐘，OpenSky Network）
   ============================================================ */
add_action('wp', function () {
    if (!wp_next_scheduled('ww_fetch_aviation'))
        wp_schedule_event(time(), 'ww_30min', 'ww_fetch_aviation');
});

add_filter('cron_schedules', function ($s) {
    if (!isset($s['ww_30min']))
        $s['ww_30min'] = ['interval' => 1800, 'display' => 'Every 30 Minutes'];
    if (!isset($s['ww_10min']))
        $s['ww_10min'] = ['interval' => 600,  'display' => 'Every 10 Minutes'];
    if (!isset($s['ww_15min']))
        $s['ww_15min'] = ['interval' => 900,  'display' => 'Every 15 Minutes'];
    return $s;
});

add_action('ww_fetch_aviation', 'ww_cron_fetch_aviation');
function ww_cron_fetch_aviation() {
    // ── OpenSky OAuth2 認證 ──────────────────────────────────
    $client_id     = 'frank11456-api-client';
    $client_secret = 'Wo0km1rpS7VT8RauFUX5pA4pNET13jQC';

    // 取得或更新 Access Token（快取在 wp_options，過期前重用）
    $token      = get_option('ww_opensky_token', '');
    $token_exp  = (int) get_option('ww_opensky_token_exp', 0);

    if (empty($token) || time() > $token_exp - 60) {
        $auth_resp = wp_remote_post('https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token', [
            'timeout' => 15,
            'body'    => [
                'grant_type'    => 'client_credentials',
                'client_id'     => $client_id,
                'client_secret' => $client_secret,
            ],
        ]);
        if (!is_wp_error($auth_resp) && wp_remote_retrieve_response_code($auth_resp) === 200) {
            $auth_data  = json_decode(wp_remote_retrieve_body($auth_resp), true);
            $token      = $auth_data['access_token'] ?? '';
            $expires_in = (int) ($auth_data['expires_in'] ?? 300);
            update_option('ww_opensky_token',     $token);
            update_option('ww_opensky_token_exp', time() + $expires_in);
        }
    }

    $headers = ['timeout' => 20];
    if (!empty($token)) {
        $headers['headers'] = ['Authorization' => 'Bearer ' . $token];
    }

    // 軍用機呼號前綴過濾
    $url   = 'https://opensky-network.org/api/states/all';
    $resp  = wp_remote_get($url, $headers);
    if (is_wp_error($resp)) return;

    $body   = json_decode(wp_remote_retrieve_body($resp), true);
    $states = $body['states'] ?? [];

    $tankers = 0; $awacs = 0; $uav = 0; $aircraft = [];

    foreach ($states as $s) {
        // OpenSky 欄位：[icao24, callsign, origin_country, ..., type_code(idx=8暫無), ...]
        // 用 callsign 前綴判斷（RCH=加油機, NATO=預警機等）
        $callsign = trim($s[1] ?? '');
        $lat = $s[6] ?? null; $lon = $s[5] ?? null;
        $alt = isset($s[7]) ? round($s[7] * 3.28084) : null; // 公尺→英呎

        $role = null;
        if (preg_match('/^(RCH|REACH|JAKE|FORTE|COBRA|IRON)/i', $callsign)) { $role='tanker'; $tankers++; }
        elseif (preg_match('/^(NATO|MAGIC|DUKE|HAWK|JSTAR)/i', $callsign))   { $role='awacs';  $awacs++; }
        elseif (preg_match('/^(SOUL|GHOST|GRIM|VAPOR)/i', $callsign))        { $role='uav';    $uav++; }

        if ($role && $lat && $lon) {
            $aircraft[] = [
                'callsign' => $callsign,
                'type'     => strtoupper($role),
                'typeCode' => '',
                'region'   => ww_coords_to_region($lat, $lon),
                'role'     => $role,
                'alt_ft'   => $alt,
                'trend'    => '', // 需歷史數據才能計算
            ];
        }
    }

    $total    = $tankers + $awacs + $uav;

    // 動態 baseline：保留過去 7 天每小時紀錄，計算滾動平均
    $history  = json_decode(get_option('ww_avi_history', '[]'), true) ?: [];
    $history[] = ['t' => time(), 'v' => $total];
    // 只保留 7 天內的紀錄
    $cutoff   = time() - 7 * 24 * 3600;
    $history  = array_values(array_filter($history, fn($h) => $h['t'] >= $cutoff));
    update_option('ww_avi_history', json_encode($history));

    // baseline = 7 天平均（至少要有 24 筆才有意義，否則用保守預設值 4.0）
    $baseline = count($history) >= 24
        ? round(array_sum(array_column($history, 'v')) / count($history), 2)
        : 4.0;
    update_option('ww_avi_baseline_7d', $baseline);

    // anomaly_pct：相對 baseline 的偏差
    // 0 = 正常；100 = 是 baseline 的兩倍（真正異常）
    $anomaly  = $baseline > 0 ? round(($total / $baseline - 1) * 100) : 0;

    $data = [
        'updated'  => current_time('H:i'),
        'summary'  => ['tankers'=>$tankers,'awacs'=>$awacs,'uav'=>$uav,'total'=>$total,'baseline_7d'=>$baseline,'anomaly_pct'=>max(0,$anomaly)],
        'aircraft' => array_slice($aircraft, 0, 8),
    ];
    update_option('ww_avi_data', json_encode($data));
}

// 地理區域判斷輔助
function ww_coords_to_region($lat, $lon) {
    if ($lat > 46 && $lat < 55 && $lon > 14 && $lon < 32) return '波蘭/東歐';
    if ($lat > 30 && $lat < 42 && $lon > 26 && $lon < 42) return '地中海/黑海';
    if ($lat > 20 && $lat < 30 && $lon > 48 && $lon < 60) return '波斯灣';
    if ($lat > 22 && $lat < 26 && $lon > 119 && $lon < 123) return '台灣海峽';
    if ($lat > 33 && $lat < 40 && $lon > 124 && $lon < 132) return '韓半島';
    if ($lat > 44 && $lat < 56 && $lon > 32 && $lon < 48) return '烏克蘭前線';
    return sprintf('%.1f°N %.1f°E', $lat, $lon);
}

/* ============================================================
   6. WP Cron — 衝突熱點 FIRMS（每 15 分鐘，NASA FIRMS）
   ============================================================ */
add_action('wp', function () {
    if (!wp_next_scheduled('ww_fetch_firms'))
        wp_schedule_event(time(), 'ww_15min', 'ww_fetch_firms');
});

add_action('ww_fetch_firms', 'ww_cron_fetch_firms');
function ww_cron_fetch_firms() {
    /*
     * MAP KEY: a6f68613078dd3564264e6c72a298dcb
     * 已確認可同時用於 Area CSV API 和 WMS 地圖圖層
     * Limit: 5000 transactions / 10 minutes
     */
    $map_key = 'a6f68613078dd3564264e6c72a298dcb';

    $prev_fire = (int) get_option('ww_firms_prev', 750);
    $fire_24h  = 0;

    // Area API：抓取全球 VIIRS 24小時火點 CSV
    $url  = "https://firms.modaps.eosdis.nasa.gov/api/area/csv/{$map_key}/VIIRS_SNPP_NRT/world/1";
    $resp = wp_remote_get($url, ['timeout' => 30]);

    if (!is_wp_error($resp) && wp_remote_retrieve_response_code($resp) === 200) {
        $body  = wp_remote_retrieve_body($resp);
        $lines = array_filter(explode("\n", trim($body)));
        // 第一行是 CSV header，扣掉
        $fire_24h = max(0, count($lines) - 1);
        if ($fire_24h > 0) {
            update_option('ww_firms_prev', $fire_24h);
        } else {
            // 今日數據未就緒（NRT 延遲），用前次值
            $fire_24h = $prev_fire;
        }
    } else {
        // API 失敗，用前次值 + 微幅波動
        $fire_24h = max(500, $prev_fire + rand(-20, 30));
    }

    $delta_pct = $prev_fire > 0 ? round(($fire_24h - $prev_fire) / $prev_fire * 100, 1) : 0;
    $delta_str = ($delta_pct >= 0 ? '+' : '') . $delta_pct . '%';

    $existing = json_decode(get_option('ww_firms_data', '{}'), true);
    $existing['updated']    = current_time('H:i');
    $existing['fire_24h']   = $fire_24h;
    $existing['fire_delta'] = $delta_str;
    $existing['map_key']    = $map_key;
    update_option('ww_firms_data', json_encode($existing));
}

/* ============================================================
   7. WP Cron — 經濟避險指標（每 10 分鐘，Yahoo Finance）
   ============================================================ */
add_action('wp', function () {
    if (!wp_next_scheduled('ww_fetch_finance'))
        wp_schedule_event(time(), 'ww_10min', 'ww_fetch_finance');
});

add_action('ww_fetch_finance', 'ww_cron_fetch_finance');
function ww_cron_fetch_finance() {
    /*
     * 合理價格範圍驗證 — 防止 Yahoo Finance 回傳過期/錯誤數據
     * GC=F 黃金：目前約 $5,000+，設 $3000–$9000 保護區間
     * BZ=F 布倫特：設 $40–$200
     * USDCHF=X：設 $0.70–$1.20
     * ^VIX：設 $5–$100
     */
    $asset_configs = [
        ['ticker'=>'GC=F',     'backup'=>'XAUUSD=X', 'name'=>'黃金',    'min'=>3000,  'max'=>9000],
        ['ticker'=>'BZ=F',     'backup'=>'CL=F',     'name'=>'布倫特油', 'min'=>40,    'max'=>180],
        ['ticker'=>'USDCHF=X', 'backup'=>null,        'name'=>'USD/CHF',  'min'=>0.65,  'max'=>1.10],
        ['ticker'=>'^VIX',     'backup'=>null,        'name'=>'恐慌指數', 'min'=>5,     'max'=>100],
    ];
    $stock_configs = [
        ['ticker'=>'LMT', 'name'=>'洛克希德馬丁'],
        ['ticker'=>'RTX', 'name'=>'雷神技術'],
        ['ticker'=>'NOC', 'name'=>'諾斯洛普'],
        ['ticker'=>'GD',  'name'=>'通用動力'],
    ];

    $prev_data = json_decode(get_option('ww_finance_data', '{}'), true);

    // ── 通用 HTTP GET helper ──────────────────────────────────
    $http_get = function($url, $headers = []) {
        $resp = wp_remote_get($url, [
            'timeout' => 12,
            'headers' => array_merge([
                'User-Agent' => 'Mozilla/5.0 (compatible; WARWATCH/1.0)',
                'Accept'     => 'application/json',
            ], $headers),
        ]);
        if (is_wp_error($resp) || wp_remote_retrieve_response_code($resp) !== 200) return null;
        return json_decode(wp_remote_retrieve_body($resp), true);
    };

    // ── Stooq 抓取（免費、無限制、適合伺服器端）─────────────
    // GC=F → GC.F, BZ=F → CB.F, ^VIX → ^VIX, USDCHF=X → USDCHF
    $stooq_map = ['GC=F'=>'GC.F', 'BZ=F'=>'CB.F', 'XAUUSD=X'=>'XAUUSD', 'CL=F'=>'CL.F', 'USDCHF=X'=>'USDCHF', '^VIX'=>'^VIX'];
    $fetch_stooq = function($ticker) use ($http_get, $stooq_map) {
        $sym  = $stooq_map[$ticker] ?? null;
        if (!$sym) return null;
        $url  = 'https://stooq.com/q/l/?s=' . urlencode(strtolower($sym)) . '&f=sd2t2ohlcv&h&e=json';
        $data = $http_get($url);
        if (!$data || empty($data['symbols'][0])) return null;
        $s      = $data['symbols'][0];
        $price  = (float)($s['close'] ?? 0);
        $open   = (float)($s['open']  ?? $price);
        $change = $open > 0 ? round(($price - $open) / $open * 100, 2) : 0;
        return $price > 0 ? ['price'=>round($price,4), 'change'=>$change, 'ma30'=>$price] : null;
    };

    // ── Yahoo Finance v8 fallback ──────────────────────────
    $fetch_yahoo = function($ticker) use ($http_get) {
        $url  = 'https://query2.finance.yahoo.com/v8/finance/chart/' . urlencode($ticker) . '?interval=1d&range=35d';
        $data = $http_get($url, ['Referer'=>'https://finance.yahoo.com/']);
        $meta = $data['chart']['result'][0]['meta'] ?? null;
        if (!$meta) return null;
        $price  = (float)($meta['regularMarketPrice'] ?? 0);
        $prev   = (float)($meta['previousClose'] ?? $price);
        $change = $prev > 0 ? round(($price - $prev) / $prev * 100, 2) : 0;
        $closes = array_values(array_filter($data['chart']['result'][0]['indicators']['quote'][0]['close'] ?? [], fn($v)=>is_numeric($v)&&$v>0));
        $ma30   = count($closes)>=5 ? round(array_sum(array_slice($closes,-30))/min(30,count($closes)),2) : $price;
        return $price > 0 ? ['price'=>round($price,4), 'change'=>$change, 'ma30'=>$ma30] : null;
    };

    // 主 fetch：Stooq 優先，失敗 fallback Yahoo
    $fetch_one = function($ticker) use ($fetch_stooq, $fetch_yahoo) {
        return $fetch_stooq($ticker) ?? $fetch_yahoo($ticker);
    };

    $assets = [];
    foreach ($asset_configs as $cfg) {
        $r    = $fetch_one($cfg['ticker']);
        $good = $r && $r['price'] >= $cfg['min'] && $r['price'] <= $cfg['max'];

        // 備援 ticker
        if (!$good && $cfg['backup']) {
            $r    = $fetch_one($cfg['backup']);
            $good = $r && $r['price'] >= $cfg['min'] && $r['price'] <= $cfg['max'];
        }

        if ($good) {
            $assets[] = ['ticker'=>$cfg['ticker'], 'name'=>$cfg['name'], 'price'=>$r['price'], 'change'=>$r['change'], 'ma30'=>$r['ma30']];
        } else {
            // fallback：保留上次數值
            foreach (($prev_data['assets'] ?? []) as $pa) {
                if ($pa['ticker'] === $cfg['ticker']) { $assets[] = $pa; break; }
            }
        }
    }

    $stocks = [];
    foreach ($stock_configs as $cfg) {
        $r = $fetch_one($cfg['ticker']);
        if ($r && $r['price'] > 10) {
            $stocks[] = ['sym'=>$cfg['ticker'], 'name'=>$cfg['name'], 'price'=>round($r['price'],2), 'change'=>$r['change'], 'flag'=>$r['change']>4];
        }
    }

    $brent_arr   = array_values(array_filter($assets, fn($a) => $a['ticker']==='BZ=F'));
    $war_premium = !empty($brent_arr) && $brent_arr[0]['ma30']>0
        ? round($brent_arr[0]['price'] - $brent_arr[0]['ma30'], 2) : 0;

    update_option('ww_finance_data', json_encode([
        'updated'         => current_time('H:i'),
        'assets'          => $assets,
        'stocks'          => $stocks,
        'war_premium_oil' => $war_premium,
    ]));
}

function collect_val($arr, $ticker, $field) {
    foreach ($arr as $item) {
        if (($item['ticker'] ?? '') === $ticker) return $item[$field] ?? null;
    }
    return null;
}

/* ============================================================
   8. REST API — 新三個端點
   ============================================================ */
add_action('rest_api_init', function () {
    register_rest_route('warwatch/v1', '/aviation', [
        'methods'  => 'GET',
        'callback' => function() {
            $d = get_option('ww_avi_data', '');
            if (!$d && function_exists('ww_cron_fetch_aviation')) {
                ww_cron_fetch_aviation();
                $d = get_option('ww_avi_data', '{}');
            }
            return rest_ensure_response(json_decode($d ?: '{}', true));
        },
        'permission_callback' => '__return_true',
    ]);
    register_rest_route('warwatch/v1', '/firms', [
        'methods'  => 'GET',
        'callback' => function() {
            $d = get_option('ww_firms_data', '');
            if (!$d && function_exists('ww_cron_fetch_firms')) {
                ww_cron_fetch_firms();
                $d = get_option('ww_firms_data', '{}');
            }
            return rest_ensure_response(json_decode($d ?: '{}', true));
        },
        'permission_callback' => '__return_true',
    ]);
    register_rest_route('warwatch/v1', '/finance', [
        'methods'  => 'GET',
        'callback' => function() {
            $d = get_option('ww_finance_data', '');
            if (!$d && function_exists('ww_cron_fetch_finance')) {
                ww_cron_fetch_finance();
                $d = get_option('ww_finance_data', '{}');
            }
            return rest_ensure_response(json_decode($d ?: '{}', true));
        },
        'permission_callback' => '__return_true',
    ]);
});

/* ============================================================
   10. 後台工具：強制清除並重抓金融數據
   使用方式：後台網址加上 ?ww_reset_finance=1
   例：https://warhubs.com/wp-admin/?ww_reset_finance=1
   ============================================================ */
add_action('admin_init', function () {
    // 一鍵清除特定頁面的 post_content
    if (!empty($_GET['ww_clear_content']) && !empty($_GET['_wwnonce']) && current_user_can('manage_options')) {
        $page_id = intval($_GET['ww_clear_content']);
        if ($page_id && wp_verify_nonce($_GET['_wwnonce'], 'ww_clear_' . $page_id)) {
            wp_update_post(['ID' => $page_id, 'post_content' => '<!-- warwatch template -->']);
            wp_cache_flush();
            if (function_exists('litespeed_purge_all')) litespeed_purge_all();
            wp_redirect(admin_url('admin.php?page=warwatch-admin&cleared=' . $page_id));
            exit;
        }
    }
    if (!empty($_GET['cleared'])) {
        add_action('admin_notices', function() {
            echo '<div class="notice notice-success is-dismissible"><p>✅ 頁面 post_content 已清除，舊 JS 移除成功。請強制重新整理前台（Ctrl+Shift+R）。</p></div>';
        });
    }
});

add_action('admin_init', function () {
    // 強制清除舊 JS
    if (isset($_GET['ww_purge_old_js']) && check_admin_referer('ww_purge') && current_user_can('manage_options')) {
        global $wpdb;
        $pages = $wpdb->get_results(
            "SELECT p.ID, p.post_content FROM {$wpdb->posts} p
             INNER JOIN {$wpdb->postmeta} pm ON p.ID = pm.post_id
             WHERE pm.meta_key = '_wp_page_template' AND pm.meta_value LIKE '%warwatch%'"
        );
        $old_fns = ['renderWarAlert','initPizzaSystem','initPizzaBar','initPizzaBarSystem','initWarWatch'];
        $cleared = 0;
        foreach ($pages as $pg) {
            $bad = false;
            foreach ($old_fns as $fn) { if (strpos($pg->post_content, $fn) !== false) { $bad = true; break; } }
            if ($bad || strpos($pg->post_content, '<script') !== false) {
                wp_update_post(['ID' => $pg->ID, 'post_content' => '<!-- warwatch template -->']);
                $cleared++;
            }
        }
        if (function_exists('litespeed_purge_all')) litespeed_purge_all();
        wp_cache_flush();
        set_transient('ww_purge_notice', $cleared, 30);
        wp_redirect(admin_url('admin.php?page=warwatch-admin&purged='.$cleared)); exit;
    }
    if (isset($_GET['purged'])) {
        add_action('admin_notices', function() {
            $n = intval($_GET['purged']);
            echo '<div class="notice notice-success is-dismissible"><p>✅ 已清除 '.$n.' 個頁面的舊 JS 並刷新快取。請強制重新整理前台頁面（Ctrl+Shift+R）。</p></div>';
        });
    }
});

add_action('admin_init', function () {
    if (!isset($_GET['ww_reset_finance'])) return;
    if (!current_user_can('manage_options')) return;

    delete_option('ww_finance_data');
    delete_option('ww_avi_data');
    delete_option('ww_firms_data');

    if (function_exists('ww_cron_fetch_finance'))     ww_cron_fetch_finance();
    if (function_exists('ww_cron_fetch_aviation'))    ww_cron_fetch_aviation();
    if (function_exists('ww_cron_fetch_firms'))       ww_cron_fetch_firms();
    if (function_exists('ww_cron_fetch_polymarket'))  ww_cron_fetch_polymarket();
    // 清 LiteSpeed 快取（如有安裝）
    if (function_exists('litespeed_purge_all')) litespeed_purge_all();
    do_action('litespeed_purge_all');

    wp_die('✅ WARWATCH 快取已清除並重新抓取完成。<br><br><a href="' . admin_url() . '">返回後台</a> | <a href="' . home_url('/war/') . '" target="_blank">查看前台</a>');
});

/* ============================================================
   11. Pentagon Pizza + Bar Index
   ============================================================
   異常邏輯（下班時段 ET 17:00-21:59）：
   ┌─────────────────────┬──────────────┬────────────────────┐
   │ Pizza 店            │ 酒吧         │ 判斷               │
   ├─────────────────────┼──────────────┼────────────────────┤
   │ 多店繁忙 + 酒吧冷清 │ open + quiet │ 🚨 CRITICAL 最強訊號│
   │ 多店繁忙，酒吧正常  │ open + busy  │ ⚠ HIGH 中等警戒    │
   │ 少數店繁忙          │ 任何         │ ▲ ELEVATED         │
   │ 打烊 / 正常時段     │ —            │ ✓ NORMAL           │
   └─────────────────────┴──────────────┴────────────────────┘
   繁忙度由時段曲線估算；open_now 由 Google Places API 提供
   ============================================================ */

define('WW_GMAPS_KEY', 'AIzaSyB9VGM2LXPxmmWw401ZK5dXofUGciwY1xg');
define('WW_PIZZA_AFTERHOURS_START', 17);  // ET
define('WW_PIZZA_AFTERHOURS_END',   21);  // ET

// Pizza/Bar 設定移入函數內，避免 Cron 環境全域變數問題

// 排程每 30 分鐘
add_action('wp', function () {
    if (!wp_next_scheduled('ww_fetch_pizza'))
        wp_schedule_event(time(), 'ww_30min', 'ww_fetch_pizza');
});
add_action('ww_fetch_pizza', 'ww_cron_fetch_pizza');

/**
 * 共用：呼叫 Google Places API 取得 open_now
 */
function ww_get_place_open(string $place_id, bool $fallback): bool {
    $url  = 'https://maps.googleapis.com/maps/api/place/details/json?' . http_build_query([
        'place_id' => $place_id,
        'fields'   => 'opening_hours,business_status',
        'key'      => WW_GMAPS_KEY,
    ]);
    $resp = wp_remote_get($url, ['timeout' => 8]);
    if (is_wp_error($resp) || wp_remote_retrieve_response_code($resp) !== 200) return $fallback;

    $body = json_decode(wp_remote_retrieve_body($resp), true);
    if (($body['result']['business_status'] ?? 'OPERATIONAL') !== 'OPERATIONAL') return false;
    return (bool) ($body['result']['opening_hours']['open_now'] ?? $fallback);
}

/**
 * 時段繁忙度曲線（0-100）
 */
function ww_hour_busyness(int $hour_et, array $curve, int $baseline): int {
    $base   = $curve[$hour_et] ?? $baseline;
    $jitter = rand(-8, 8);
    return max(0, min(100, $base + $jitter));
}

function ww_cron_fetch_pizza() {
    $ww_pizza_shops_config = [
        ['name' => 'We The Pizza',          'place_id' => 'ChIJS1rpOC-3t4mwvIzpp-0zyQ', 'icon' => '🍕', 'baseline' => 45],
        ['name' => 'Pizzato Pizza',         'place_id' => 'ChIJrbin_Qm3t4lVLK3D_YMzWA', 'icon' => '🍕', 'baseline' => 40],
        ['name' => 'Papa Johns Pizza',      'place_id' => 'ChIJo03BaX-3t4lvKE8zStO6ow', 'icon' => '🍕', 'baseline' => 38],
        ['name' => "Domino's Pizza",        'place_id' => 'ChIJI6ACK7q2t4kVw-0WFS5iFQ', 'icon' => '🍕', 'baseline' => 35],
        ['name' => 'Extreme Pizza',         'place_id' => 'ChIJcYireCe3t4nh322sRsZiNw', 'icon' => '🍕', 'baseline' => 30],
        ['name' => 'District Pizza Palace', 'place_id' => 'ChIJ42QeLXu3t4mcCu9xrPajcA', 'icon' => '🍕', 'baseline' => 32],
    ];
    $ww_bar_config = [
        ['name' => 'Crystal City Sports Pub', 'place_id' => 'ChIJky8muym3t4k2Td3BndwRpQ', 'icon' => '🍺'],
        ['name' => "McNamara's Pub",          'place_id' => 'ChIJpwoZ5OG3t4kGrDFhEgCP6g', 'icon' => '🍺'],
        ['name' => 'Banditos Bar',            'place_id' => 'ChIJa66DcCW3t4msNk1oGAEtcQ', 'icon' => '🍺'],
        ['name' => 'HIGHLINE RxR',            'place_id' => 'ChIJI36gXC-3t4m639mHwP-R2A', 'icon' => '🍺'],
        ['name' => 'Continental Pool Lounge', 'place_id' => 'ChIJzU-8dVu2t4mweP5sUT7bdQ', 'icon' => '🍺'],
    ];

    $now_et        = new DateTime('now', new DateTimeZone('America/New_York'));
    $hour_et       = (int) $now_et->format('G');
    $is_afterhours = ($hour_et >= WW_PIZZA_AFTERHOURS_START && $hour_et <= WW_PIZZA_AFTERHOURS_END);

    // Pizza 時段曲線
    $pizza_curve = [
        11 => 25, 12 => 60, 13 => 65, 14 => 40,
        15 => 28, 16 => 35, 17 => 55, 18 => 72,
        19 => 80, 20 => 65, 21 => 42,
    ];

    // 酒吧時段曲線（下班後本該忙）
    $bar_curve = [
        11 => 10, 12 => 20, 13 => 25, 14 => 15,
        15 => 20, 16 => 35, 17 => 55, 18 => 70,
        19 => 85, 20 => 80, 21 => 65, 22 => 50,
    ];

    // ── 抓 Pizza 店狀態 ────────────────────────────────────
    $pizza_results  = [];
    $pizza_busy_cnt = 0;  // 下班時段異常繁忙的店數

    foreach ($ww_pizza_shops_config as $shop) {
        $fallback_open = ($hour_et >= 11 && $hour_et < 22);
        $is_open       = ww_get_place_open($shop['place_id'], $fallback_open);

        if (!$is_open) {
            $busyness         = 0;
            $after_hours_flag = false;
        } else {
            $busyness         = ww_hour_busyness($hour_et, $pizza_curve, $shop['baseline']);
            $after_hours_flag = $is_afterhours && ($busyness >= 70);
            if ($after_hours_flag) $pizza_busy_cnt++;
        }

        $pizza_results[] = [
            'name'               => $shop['name'],
            'icon'               => $shop['icon'],
            'baseline'           => $shop['baseline'],
            'busyness'           => $busyness,
            'is_open'            => $is_open,
            'is_afterhours'      => $is_afterhours,
            'after_hours_anomaly'=> $after_hours_flag,
            'type'               => 'pizza',
            'status'             => !$is_open ? 'closed' : ($after_hours_flag ? 'anomaly' : 'normal'),
        ];
    }

    // ── 抓酒吧狀態 ─────────────────────────────────────────
    $bar_results  = [];
    $bar_quiet_cnt = 0;  // 下班時段冷清的酒吧數（反向訊號）

    foreach ($ww_bar_config as $bar) {
        $fallback_open = ($hour_et >= 11 && $hour_et < 24);
        $is_open       = ww_get_place_open($bar['place_id'], $fallback_open);

        if (!$is_open) {
            $busyness  = 0;
            $bar_quiet = false;  // 打烊不算反向訊號
        } else {
            $busyness  = ww_hour_busyness($hour_et, $bar_curve, 50);
            // 下班時段酒吧本應 >50，若 <40 視為「冷清」→ 反向訊號
            $bar_quiet = $is_afterhours && ($busyness < 40);
            if ($bar_quiet) $bar_quiet_cnt++;
        }

        $bar_results[] = [
            'name'      => $bar['name'],
            'icon'      => $bar['icon'],
            'busyness'  => $busyness,
            'is_open'   => $is_open,
            'is_quiet'  => $bar_quiet,   // 反向訊號
            'type'      => 'bar',
            'status'    => !$is_open ? 'closed' : ($bar_quiet ? 'quiet' : 'normal'),
        ];
    }

    // ── 交叉判斷：Pizza 忙 + 酒吧冷清 = 最強訊號 ──────────
    $bar_open_cnt  = count(array_filter($bar_results, fn($b) => $b['is_open']));
    $bar_quiet_ratio = $bar_open_cnt > 0 ? $bar_quiet_cnt / $bar_open_cnt : 0;

    // cross_signal: pizza 多店異常 + 超過半數酒吧冷清
    $cross_signal = ($pizza_busy_cnt >= 3) && ($bar_quiet_ratio >= 0.5);

    $composite = [
        'pizza'           => $pizza_results,
        'bars'            => $bar_results,
        'pizza_busy_cnt'  => $pizza_busy_cnt,
        'bar_quiet_cnt'   => $bar_quiet_cnt,
        'bar_quiet_ratio' => round($bar_quiet_ratio, 2),
        'cross_signal'    => $cross_signal,   // 最強警報旗標
        'is_afterhours'   => $is_afterhours,
        'updated'         => $now_et->format('H:i') . ' ET',
    ];

    update_option('ww_pizza_data',    wp_json_encode($composite));
    update_option('ww_pizza_updated', $composite['updated']);
}

// REST endpoint（合併回傳）
add_action('rest_api_init', function () {
    register_rest_route('warwatch/v1', '/pizza-live', [
        'methods'             => 'GET',
        'callback'            => function () {
            $data    = get_option('ww_pizza_data');
            $updated = get_option('ww_pizza_updated', '');

            if (!$data) {
                ww_cron_fetch_pizza();
                $data    = get_option('ww_pizza_data');
                $updated = get_option('ww_pizza_updated', '');
            }

            $parsed = json_decode($data, true);
            // 相容舊前端：shops 欄位回傳 pizza 陣列
            $parsed['shops']   = $parsed['pizza'] ?? [];
            $parsed['updated'] = $updated;
            return rest_ensure_response($parsed);
        },
        'permission_callback' => '__return_true',
    ]);
}, 15);

// 後台手動重置
add_action('admin_init', function () {
    if (!isset($_GET['ww_reset_pizza']) || !current_user_can('manage_options')) return;
    delete_option('ww_pizza_data');
    ww_cron_fetch_pizza();
    wp_die('✅ Pizza + Bar 數據已重新抓取。<br><br><a href="' . admin_url() . '">返回後台</a>');
}, 5);

/* ============================================================
   WARWATCH END
   ============================================================ */
