#!/usr/bin/env node
/**
 * pipeline-to-batch.mjs — bridge data/pipeline.md "## Pending" into
 * batch/batch-input.tsv so batch-runner.sh can process a scan's output.
 *
 * FORK-LOCAL: declared in config/local-paths.txt. Not shipped upstream; the
 * updater will never touch it. If upstream ever ships an official bridge,
 * delete this and switch to theirs.
 *
 * THE GAP THIS CLOSES
 * scan.mjs appends discovered roles to data/pipeline.md. batch-runner.sh reads
 * batch/batch-input.tsv. Nothing upstream converts one to the other, so an
 * automated scan -> evaluate chain has no entry point. (reconcile-pipeline.mjs
 * closes the loop on the way back OUT, after a batch run; this is the way IN.)
 *
 * Idempotent: a URL already in batch-input.tsv or already recorded in
 * batch-state.tsv is skipped, so it is safe to run after every scan.
 * URLs are compared after normalization (tracking params stripped, host
 * lowercased, fragment + trailing slash dropped), matching how the rest of
 * the repo dedups URLs.
 *
 * Run: node automation/pipeline-to-batch.mjs [--dry-run] [--limit N]
 *      [--pipeline <path>] [--input <path>] [--state <path>]
 *
 * Exit 0 always on success (including "nothing to add") so cron stays quiet.
 */

import { readFileSync, writeFileSync, existsSync, appendFileSync } from 'fs';
import { dirname, join, resolve } from 'path';
import { fileURLToPath } from 'url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');

const argv = process.argv.slice(2);
const hasFlag = (f) => argv.includes(f);
const flagValue = (f, fallback) => {
  const i = argv.indexOf(f);
  return i !== -1 && argv[i + 1] ? argv[i + 1] : fallback;
};

const DRY_RUN = hasFlag('--dry-run');
const LIMIT = Number(flagValue('--limit', '0')) || 0;
const PIPELINE = resolve(ROOT, flagValue('--pipeline', 'data/pipeline.md'));
const INPUT = resolve(ROOT, flagValue('--input', 'batch/batch-input.tsv'));
const STATE = resolve(ROOT, flagValue('--state', 'batch/batch-state.tsv'));

const INPUT_HEADER = 'id\turl\tsource\tnotes';

/** Normalize a URL for dedup — mirrors merge-tracker.mjs's approach. */
function normalizeUrl(raw) {
  try {
    const u = new URL(raw.trim());
    u.hostname = u.hostname.toLowerCase();
    u.hash = '';
    for (const p of [...u.searchParams.keys()]) {
      if (/^(utm_|gh_src|ref$|source$|src$)/i.test(p)) u.searchParams.delete(p);
    }
    let s = u.toString();
    if (s.endsWith('/')) s = s.slice(0, -1);
    return s;
  } catch {
    return raw.trim();
  }
}

/** Read the "## Pending" section; tolerate EN/ES/DE/DA headings like the modes do. */
function readPending(path) {
  if (!existsSync(path)) return [];
  const lines = readFileSync(path, 'utf-8').split(/\r?\n/);
  const PENDING_RE = /^##\s+(Pending|Pendientes|Offen|Afventer)\b/i;
  const OTHER_SECTION_RE = /^##\s+/;

  const out = [];
  let inPending = false;
  for (const line of lines) {
    if (PENDING_RE.test(line)) { inPending = true; continue; }
    if (inPending && OTHER_SECTION_RE.test(line)) break;
    if (!inPending) continue;

    // Only unchecked entries: "- [ ] ..." ([x] done, [!] errored)
    const m = line.match(/^\s*-\s*\[\s\]\s*(.+)$/);
    if (!m) continue;

    const body = m[1];
    const urlMatch = body.match(/https?:\/\/\S+/);
    if (!urlMatch) continue;
    const url = urlMatch[0].replace(/[|,)\]]+$/, '');

    // "- [ ] <url> | Company | Role | Location | rank: ..." — fields optional.
    const parts = body.split('|').map((p) => p.trim());
    const company = parts[1] || '';
    const role = parts[2] || '';
    const rank = parts.find((p) => /^rank:/i.test(p)) || '';

    out.push({ url, company, role, rank });
  }
  return out;
}

/** Every URL already known to the batch layer (input rows + state rows). */
function knownUrls() {
  const seen = new Set();
  for (const file of [INPUT, STATE]) {
    if (!existsSync(file)) continue;
    for (const line of readFileSync(file, 'utf-8').split(/\r?\n/).slice(1)) {
      const url = line.split('\t')[1];
      if (url && /^https?:\/\//.test(url.trim())) seen.add(normalizeUrl(url));
    }
  }
  return seen;
}

function nextId() {
  if (!existsSync(INPUT)) return 1;
  let max = 0;
  for (const line of readFileSync(INPUT, 'utf-8').split(/\r?\n/).slice(1)) {
    const id = Number(line.split('\t')[0]);
    if (Number.isInteger(id) && id > max) max = id;
  }
  return max + 1;
}

// ── main ────────────────────────────────────────────────────────────────────
const pending = readPending(PIPELINE);
const known = knownUrls();

const fresh = [];
const seenThisRun = new Set();
for (const entry of pending) {
  const key = normalizeUrl(entry.url);
  if (known.has(key) || seenThisRun.has(key)) continue;
  seenThisRun.add(key);
  fresh.push(entry);
  if (LIMIT > 0 && fresh.length >= LIMIT) break;
}

if (fresh.length === 0) {
  console.log(`pipeline-to-batch: nothing new (${pending.length} pending, all already in batch layer)`);
  process.exit(0);
}

let id = nextId();
const rows = fresh.map((e) => {
  const notes = [e.company, e.role].filter(Boolean).join(' — ') + (e.rank ? ` (${e.rank})` : '');
  // Tabs/newlines in any field would shift columns — collapse defensively.
  const clean = (s) => String(s).replace(/[\t\r\n]+/g, ' ').trim();
  return `${id++}\t${clean(e.url)}\tpipeline\t${clean(notes)}`;
});

if (DRY_RUN) {
  console.log(`pipeline-to-batch: would add ${rows.length} offer(s):`);
  for (const r of rows) console.log('  ' + r);
  process.exit(0);
}

if (!existsSync(INPUT)) {
  writeFileSync(INPUT, INPUT_HEADER + '\n' + rows.join('\n') + '\n', 'utf-8');
} else {
  const existing = readFileSync(INPUT, 'utf-8');
  const sep = existing.endsWith('\n') ? '' : '\n';
  appendFileSync(INPUT, sep + rows.join('\n') + '\n', 'utf-8');
}

console.log(`pipeline-to-batch: added ${rows.length} offer(s) to ${INPUT.slice(ROOT.length + 1)}`);
for (const r of rows) console.log('  + ' + r.split('\t').slice(1, 2) + '  ' + r.split('\t')[3]);
