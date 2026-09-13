/**
 * jobindex.mjs — Jobindex.dk, Denmark's largest job board.
 *
 * Uses the public RSS feed the site advertises on every search page:
 *
 *   <link rel="alternate" type="application/rss+xml"
 *         href="https://www.jobindex.dk/jobsoegning.rss?q=...">
 *
 * so no HTML scraping and no browser. robots.txt (checked 2026-09-10) allows
 * /jobsoegning and /vis-job/; its Disallow list covers a competitor's listings,
 * a handful of specific job ids, and CMS paths — none of which this touches.
 *
 * TWO THINGS THE FEED DOES THAT WILL SURPRISE YOU:
 *
 * 1. A bare multi-word query is an OR search. `?q=product manager` returns
 *    "jobs containing at least one of the words product or manager" — the
 *    channel <title> says so in Danish — which is why an "Embedded software
 *    engineer" came back for it. Quoting the query switches to phrase
 *    matching, so every query here is quoted. Results are still fuzzy
 *    (Jobindex stems and expands), so career-ops' own title_filter is what
 *    actually decides; this just keeps the feed from being mostly noise.
 *
 * 2. There is NO server-side location filter. `/jobsoegning/storkoebenhavn.rss`
 *    404s, and `?geoareaid=` / `&format=rss` on the area path return the
 *    unscoped feed byte-for-byte. Location comes from each item instead, where
 *    it IS structurally marked:
 *      <span class="jix_robotjob--area">Vinderup</span>
 *    and career-ops' location_filter does the rest.
 */

import { decodeEntities } from './_html-entities.mjs';

const FEED_BASE = 'https://www.jobindex.dk/jobsoegning.rss';
const TRUSTED_HOST = 'jobindex.dk';
const DEFAULT_MAX_PAGES = 3;
const MAX_PAGES_CAP = 20;
const ITEMS_PER_PAGE = 20;

/** Queries to run, from the portals.yml entry. */
export function parseJobindexConfig(entry) {
  const raw = entry?.queries ?? entry?.query ?? [];
  const list = (Array.isArray(raw) ? raw : [raw])
    .filter(q => typeof q === 'string' && q.trim())
    .map(q => q.trim());

  const requested = Number(entry?.max_pages);
  const maxPages = Number.isFinite(requested) && requested > 0
    ? Math.min(Math.trunc(requested), MAX_PAGES_CAP)
    : DEFAULT_MAX_PAGES;

  return { queries: list, maxPages };
}

/** Phrase-quote a query unless the caller already quoted it (see note 1 above). */
export function feedUrlFor(query, page = 1) {
  const trimmed = String(query).trim();
  const quoted = /^".*"$/.test(trimmed) ? trimmed : `"${trimmed}"`;
  const url = new URL(FEED_BASE);
  url.searchParams.set('q', quoted);
  if (page > 1) url.searchParams.set('page', String(page));
  return url.href;
}

function tagText(block, tag) {
  const m = block.match(new RegExp(`<${tag}\\b[^>]*>([\\s\\S]*?)</${tag}>`, 'i'));
  if (!m) return '';
  const cdata = m[1].match(/^\s*<!\[CDATA\[([\s\S]*?)\]\]>\s*$/);
  return (cdata ? cdata[1] : decodeEntities(m[1])).trim();
}

function cleanUrl(value) {
  if (!value) return '';
  try {
    const parsed = new URL(value.trim());
    const host = parsed.hostname.toLowerCase();
    const trusted = host === TRUSTED_HOST || host.endsWith(`.${TRUSTED_HOST}`);
    return parsed.protocol === 'https:' && trusted ? parsed.href : '';
  } catch {
    return '';
  }
}

/**
 * Item <title> is "{Role}, {Company}" — split on the LAST comma, because a
 * role can contain one ("Advanced Technical Specialist, Sensors, Terma A/S").
 */
export function splitJobindexTitle(rawTitle) {
  const text = String(rawTitle || '').trim();
  const comma = text.lastIndexOf(',');
  if (comma <= 0) return { title: text, company: '' };
  const title = text.slice(0, comma).trim();
  const company = text.slice(comma + 1).trim();
  if (!title || !company) return { title: text, company: '' };
  return { title, company };
}

/**
 * Parse a Jobindex RSS feed. Exported for unit tests.
 *
 * The description is escaped HTML — twice, in the feed as served — carrying
 * the clean role in an <h4> anchor and the location in
 * <span class="jix_robotjob--area">. Both are preferred over the <title>
 * split, which is only a fallback.
 *
 * @param {string} xml raw RSS body
 * @returns {Array<{title,company,location,url,postedAt}>}
 */
export function parseJobindexFeed(xml) {
  if (typeof xml !== 'string') return [];
  const jobs = [];

  for (const item of xml.match(/<item\b[^>]*>[\s\S]*?<\/item>/gi) || []) {
    const url = cleanUrl(tagText(item, 'link'));
    if (!url) continue;

    const rawTitle = tagText(item, 'title');
    if (!rawTitle) continue;
    const split = splitJobindexTitle(rawTitle);

    // Served double-escaped: &amp;#x3C; -> &#x3C; -> '<'.
    const description = decodeEntities(decodeEntities(tagText(item, 'description')));

    const heading = description.match(/<h4[^>]*>\s*<a\b[^>]*>([\s\S]*?)<\/a>\s*<\/h4>/i);
    const title = heading ? decodeEntities(heading[1]).replace(/<[^>]+>/g, '').trim() : split.title;

    const area = description.match(/<span[^>]*class="[^"]*jix_robotjob--area[^"]*"[^>]*>([\s\S]*?)<\/span>/i);
    const location = area ? decodeEntities(area[1]).replace(/<[^>]+>/g, '').trim() : '';

    const posted = Date.parse(tagText(item, 'pubDate'));

    jobs.push({
      title: title || split.title,
      // A comma-less <title> ("Senior Product Manager") yields no company.
      // The anonymised listings Jobindex serves for recruiters are the common
      // case; '?' is career-ops' locale-invariant unknown-employer marker
      // (AGENTS.md, Optional Via field) rather than a blank cell.
      company: split.company || '?',
      location,
      url,
      postedAt: Number.isFinite(posted) ? posted : undefined,
    });
  }

  return jobs;
}

/** @type {Provider} */
export default {
  id: 'jobindex',

  detect(entry) {
    if (entry?.provider === 'jobindex') return { url: FEED_BASE };
    const target = entry?.careers_url || entry?.url;
    if (!target) return null;
    try {
      const host = new URL(target).hostname.toLowerCase();
      if (host === TRUSTED_HOST || host.endsWith(`.${TRUSTED_HOST}`)) return { url: FEED_BASE };
    } catch { /* not a URL — not ours */ }
    return null;
  },

  async fetch(entry, ctx) {
    const { queries, maxPages } = parseJobindexConfig(entry);
    if (queries.length === 0) {
      console.error(`⚠️  jobindex: "${entry?.name ?? 'entry'}" has no queries — add queries: ["product manager"]`);
      return [];
    }

    const byUrl = new Map();
    for (const query of queries) {
      for (let page = 1; page <= maxPages; page++) {
        let text;
        try {
          // redirect:'error' pins the request to jobindex.dk (no SSRF via redirect).
          text = await ctx.fetchText(feedUrlFor(query, page), { redirect: 'error' });
        } catch (err) {
          console.error(`⚠️  jobindex: ${query} page ${page} — ${err.message}`);
          break;
        }
        const jobs = parseJobindexFeed(text);
        for (const job of jobs) if (!byUrl.has(job.url)) byUrl.set(job.url, job);
        // A short page is the last page.
        if (jobs.length < ITEMS_PER_PAGE) break;
      }
    }
    return [...byUrl.values()];
  },
};
