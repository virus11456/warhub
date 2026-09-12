import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { execFileSync, spawnSync } from 'node:child_process';

test('deployment gate preserves code updates and fresh data without unnecessary builds', () => {
  const cwd = mkdtempSync(join(tmpdir(), 'warhub-deploy-'));
  const config = JSON.parse(readFileSync('vercel.json', 'utf8'));
  const scriptPath = config.ignoreCommand.replace(/^node /, '');
  const script = resolve(scriptPath);
  const git = (...args) => execFileSync('git', args, { cwd, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim();
  const gate = (sha) => spawnSync(process.execPath, [script], {
    cwd, env: { ...process.env, VERCEL_GIT_PREVIOUS_SHA: sha },
  }).status;
  const commit = () => { git('add', '.'); git('commit', '-m', 'fixture'); return git('rev-parse', 'HEAD'); };
  try {
    git('init');
    // Vercel filters files before running ignoreCommand. Verify the configured
    // executable survives the repository's actual ignore patterns.
    const ignoreFile = join(cwd, 'vercel-patterns');
    writeFileSync(ignoreFile, readFileSync('.vercelignore'));
    const ignored = spawnSync('git', ['-c', `core.excludesfile=${ignoreFile}`, 'check-ignore', '--no-index', scriptPath], { cwd });
    assert.equal(ignored.status, 1, 'ignoreCommand script must survive .vercelignore filtering');
    git('config' , 'user.name', 'Test'); git('config', 'user.email', 'test@example.invalid');
    mkdirSync(join(cwd, 'data'));
    writeFileSync(join(cwd, 'index.html'), 'initial');
    writeFileSync(join(cwd, 'data/data.json'), '{}');
    const deployed = commit();
    assert.equal(gate(''), 1, 'initial deployment builds');
    assert.equal(gate(deployed), 1, 'manual redeploy with no file changes builds');
    writeFileSync(join(cwd, 'data/data.json'), '{"updated":1}'); commit();
    assert.equal(gate(deployed), 0, 'only API-backed data skips');
    assert.equal(gate('f'.repeat(40)), 1, 'unavailable shallow history builds');
    mkdirSync(join(cwd, 'archives/2026/09'), { recursive: true });
    const archive = `archives/2026/09/20260911T060211_${'a'.repeat(64)}.json.gz`;
    writeFileSync(join(cwd, archive), 'compressed snapshot fixture'); commit();
    assert.equal(gate(deployed), 0, 'archive and data changes skip deployment');
    mkdirSync(join(cwd,'archives/gdelt-events'),{recursive:true});
    writeFileSync(join(cwd,`archives/gdelt-events/20260912141500_${'b'.repeat(64)}.json.gz`),'source fixture'); commit();
    assert.equal(gate(deployed),0,'GDELT source archives skip deployment');
    const archiveIgnored = spawnSync('git', ['-c', `core.excludesfile=${ignoreFile}`, 'check-ignore', '--no-index', archive], { cwd });
    assert.equal(archiveIgnored.status, 0, 'archives stay out of the public deployment');
    mkdirSync(join(cwd, '.agents/skills/warhub-news'), { recursive: true });
    const skill = '.agents/skills/warhub-news/SKILL.md';
    writeFileSync(join(cwd, skill), 'collector skill');
    writeFileSync(join(cwd, 'AGENTS.md'), 'collector maintenance'); commit();
    assert.equal(gate(deployed), 0, 'agent instructions do not rebuild the public site');
    const skillIgnored = spawnSync('git', ['-c', `core.excludesfile=${ignoreFile}`, 'check-ignore', '--no-index', skill], { cwd });
    assert.equal(skillIgnored.status, 0, 'skills stay out of the public deployment');
    writeFileSync(join(cwd, 'index.html'), 'new code'); commit();
    writeFileSync(join(cwd, 'data/data.json'), '{"updated":2}'); commit();
    assert.equal(gate(deployed), 1, 'later data commit cannot hide undeployed code');
    const newDeployed = git('rev-parse', 'HEAD');
    writeFileSync(join(cwd, 'data/static-only.json'), '{}'); commit();
    assert.equal(gate(newDeployed), 1, 'unknown static data must deploy');
  } finally { rmSync(cwd, { recursive: true, force: true }); }
});
