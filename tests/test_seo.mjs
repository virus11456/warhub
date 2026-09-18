import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';

const ORIGIN = 'https://warhubs.com';

function publicCanonicals() {
  const pages = ['index.html', ...readdirSync('guides').filter((file) => file.endsWith('.html')).map((file) => `guides/${file}`)];
  const urls = [];
  for (const page of pages) {
    const html = readFileSync(page, 'utf8');
    const match = html.match(/<link rel="canonical" href="([^"]+)">/);
    assert.ok(match, `${page} is missing a canonical URL`);
    assert.ok(match[1].startsWith(`${ORIGIN}/`), `${page} canonical must be an absolute warhubs.com URL`);
    urls.push(match[1]);
  }
  return [...new Set(urls)].sort();
}

test('robots.txt allows crawlers and points at the sitemap', () => {
  const text = readFileSync('robots.txt', 'utf8').replace(/\r\n/g, '\n').trimEnd();
  assert.match(text, /^User-agent:\s*\*$/m);
  assert.match(text, /^Allow:\s*\/$/m);
  assert.match(text, /^Sitemap:\s*https:\/\/warhubs\.com\/sitemap\.xml$/m);
});

test('sitemap.xml lists only real public HTML canonicals', () => {
  const xml = readFileSync('sitemap.xml', 'utf8');
  assert.match(xml, /^<\?xml version="1.0" encoding="UTF-8"\?>/);
  assert.match(xml, /<urlset xmlns="http:\/\/www\.sitemaps\.org\/schemas\/sitemap\/0\.9">/);
  const locs = [...xml.matchAll(/<loc>([^<]+)<\/loc>/g)].map((match) => match[1]);
  assert.equal(new Set(locs).size, locs.length, 'sitemap must not repeat URLs');
  assert.ok(locs.includes(`${ORIGIN}/guides/cash-finance.html`));
  assert.deepEqual([...locs].sort(), publicCanonicals());
});
