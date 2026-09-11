// Vercel: 0 skips, 1 builds. Compare against the last successful deployment,
// not HEAD^, so an intervening data commit cannot hide an undeployed code edit.
const { execFileSync } = require('node:child_process');
const previous = process.env.VERCEL_GIT_PREVIOUS_SHA || '';
const liveFiles = new Set([
  'data/data.json', 'data/history.json', 'data/metrics_daily.json',
  'data/pla_adiz.json', 'data/food_history.json', 'data/strat_history.json',
]);
let skip = false;
try {
  if (/^[a-f0-9]{40}$/i.test(previous)) {
    const files = execFileSync('git', ['diff', '--name-only', '-z', previous, 'HEAD'],
      { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).split('\0').filter(Boolean);
    // Empty diff allows manual redeployment after environment-variable changes.
    skip = files.length > 0 && files.every(file => liveFiles.has(file));
  }
} catch {
  // Missing shallow-clone history or any git error: build safely.
}
console.log(skip ? 'Data-only change: live API serves updates; skip build.'
  : 'Build required: code, redeployment, or unknown deployment history.');
process.exit(skip ? 0 : 1);
