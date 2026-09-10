// ─────────────────────────────────────────────────────────────
// Vercel Serverless Function — 即時讀取 GitHub 上的最新 data/ 檔案
//
// 為什麼需要它：本站是靜態部署，data/*.json 會被凍結在「最後一次成功
// 部署」的快照。資料機器人每 15 分鐘 commit 一次，若每次都觸發 Vercel
// 重新部署，會用爆免費方案的每日部署上限（部署被 BLOCKED、網站就卡在
// 舊快照不再更新）。這支函式改為「即時」從 GitHub 讀最新檔案，前台打
// 這支 API 就永遠拿到最新資料，完全不需要為了資料更新而重新部署。
//
// 需要環境變數 GITHUB_TOKEN（fine-grained PAT，唯讀 Contents 權限；
// 私有 repo 必需）。未設定時會回 502，前台自動退回部署快照（較舊）。
// ─────────────────────────────────────────────────────────────
const REPO = 'virus11456/warhub';
const ALLOW = new Set([
  'data.json', 'history.json', 'metrics_daily.json',
  'pla_adiz.json', 'food_history.json', 'strat_history.json',
]);

export default async function handler(req, res) {
  const f = String((req.query && req.query.f) || 'data.json');
  if (!ALLOW.has(f)) { res.status(400).json({ error: 'file not allowed' }); return; }
  // 去掉貼上時常見的前後空白／換行（否則 Authorization 標頭失效 → GitHub 404）
  const raw = process.env.GITHUB_TOKEN || '';
  const token = raw.trim();
  try {
    const gh = await fetch(
      `https://api.github.com/repos/${REPO}/contents/data/${f}?ref=main`,
      { signal: AbortSignal.timeout(8000), headers: {
          'Accept': 'application/vnd.github.raw',
          'User-Agent': 'warhub-data-fn',
          'X-GitHub-Api-Version': '2022-11-28',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
      } }
    );
    if (!gh.ok) {
      res.setHeader('Cache-Control', 'no-store');
      res.status(502).json({ error: 'github ' + gh.status,
        hint: token ? '確認 GITHUB_TOKEN 對 warhub repo 具 Contents 讀取權' : 'GITHUB_TOKEN 未設定' });
      return;
    }
    const payload = await gh.json();
    if (f === "data.json" && (!payload || !payload.updated_at)) throw new Error("invalid data snapshot");
    const body = JSON.stringify(payload);
    res.setHeader("X-Warhub-Source", "github");
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    // CDN 快取 60 秒（避免每次請求都打 GitHub API），過期後背景更新
    res.setHeader('Cache-Control', 'public, max-age=0, s-maxage=60, stale-while-revalidate=300');
    res.status(200).send(body);
  } catch (e) {
    res.setHeader('Cache-Control', 'no-store');
    res.status(502).json({ error: 'data source unavailable' });
  }
}
