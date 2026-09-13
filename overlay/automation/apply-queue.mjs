#!/usr/bin/env node
/**
 * apply-queue.mjs — export ready-to-fill application bundles for apply-runner.
 *
 *   node automation/apply-queue.mjs --min-score 3.5
 *   node automation/apply-queue.mjs --report 11
 *   node automation/apply-queue.mjs --dry-run
 *   node automation/apply-queue.mjs --out /path/to/handoff
 *
 * Reads the tracker and reports, writes one self-contained directory per job to
 * the handoff root (default ~/job-searcher/handoff, deliberately outside both
 * projects so neither owns the other's tree):
 *
 *   handoff/011-queue-it/
 *     job.json          company, role, url, score, sha256 of every file here
 *     cv.pdf            the tailored CV, copied under a generic name
 *     facts.md          identity facts, mechanically derived from profile.yml
 *     cover-letter.md   ONLY if one already exists (see below)
 *
 * Generic filenames are the point: exactly one candidate per slot exists, so
 * the runner never picks a file and can never pick the wrong one.
 *
 * READ-ONLY toward career-ops. It never edits the tracker, never sets a status,
 * never touches reports/. Moving a submitted bundle to handoff/done/ and running
 * set-status.mjs stays a human step, at the same moment.
 *
 * WHAT IT DELIBERATELY DOES NOT DO
 *
 * - Generate cover letters. generate-cover-letter.mjs RENDERS a payload to PDF;
 *   it does not compose one. Composition is `cover` mode's job, agent-driven and
 *   fact-gated, so the letter can be read before it reaches a form. A bundle
 *   without a letter records cover_letter: null and the runner leaves motivation
 *   fields empty — which is already its rule for anything it has no source for.
 * - Check liveness. That belongs at the runner's start, not here: an export can
 *   sit for days, and run-chain.sh stage 2 only ever checks unevaluated pipeline
 *   rows, never a row that already has a report.
 * - Decide whether to apply. --min-score is career-ops-side policy; the runner
 *   is threshold-blind and fills whatever it is handed. A bundle on disk is not
 *   an application: nothing is submitted without a human.
 */

import { createHash } from 'crypto';
import { copyFileSync, existsSync, mkdirSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from 'fs';
import { basename, dirname, join, resolve } from 'path';
import { fileURLToPath } from 'url';
import * as yaml from 'js-yaml';

import { parseTrackerRow, resolveColumns } from '../tracker-parse.mjs';
import { isMainModule } from '../lib/is-main-module.mjs';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const DEFAULT_MIN_SCORE = 4.0;   // AGENTS.md: below 4.0, recommend against applying
const DEFAULT_OUT = resolve(ROOT, '..', 'handoff');
const DONE_DIR = 'done';
const EXPORTABLE_STATUS = 'evaluated';

/** Categories no file here can answer. The runner must stop, never guess. */
const NEVER_GUESS = [
  'Work authorisation, visa status, or sponsorship needs beyond what is stated above',
  'Salary expectations or current salary',
  'Veteran, disability, ethnicity, or any other EEO/demographic question',
  'Notice period, availability date, or references',
  'Anything asking for an opinion, motivation, or a "why us" narrative',
];

// ---------------------------------------------------------------- reading

function fail(msg) {
  console.error(`apply-queue: ${msg}`);
  process.exit(1);
}

function readTrackerPath() {
  const env = process.env.CAREER_OPS_TRACKER;
  if (env) return resolve(ROOT, env);
  const nested = join(ROOT, 'data/applications.md');
  return existsSync(nested) ? nested : join(ROOT, 'applications.md');
}

function loadTrackerRows(trackerPath) {
  if (!existsSync(trackerPath)) fail(`no tracker at ${trackerPath}`);
  const lines = readFileSync(trackerPath, 'utf8').split('\n');
  const colmap = resolveColumns(lines);
  return lines
    .map((line) => parseTrackerRow(line, colmap))
    .filter((row) => row !== null);
}

/** "4.0/5" -> 4.0; a sentinel or junk -> null, never 0 (which would pass a floor). */
export function parseScore(cell) {
  const m = String(cell ?? '').match(/^(\d+(?:\.\d+)?)\s*\/\s*5$/);
  return m ? Number(m[1]) : null;
}

/** Report number from the tracker's report cell, e.g. "[011](../reports/...)". */
export function reportNumOf(row) {
  const m = String(row.report ?? '').match(/\[(\d+)\]/);
  return m ? m[1].padStart(3, '0') : null;
}

function findReportFile(num) {
  const dir = join(ROOT, 'reports');
  if (!existsSync(dir)) return null;
  const hit = readdirSync(dir).find((f) => f.startsWith(`${num}-`) && f.endsWith('.md'));
  return hit ? join(dir, hit) : null;
}

export function headerField(text, label) {
  const m = text.match(new RegExp(`^\\*\\*${label}:\\*\\*\\s*(.+)$`, 'm'));
  return m ? m[1].trim() : null;
}

export function machineSummary(text) {
  const m = text.match(/## Machine Summary\s*\n+```ya?ml\n([\s\S]*?)\n```/);
  if (!m) return {};
  try {
    return yaml.load(m[1]) ?? {};
  } catch (err) {
    console.error(`  warning: unparseable Machine Summary — ${err.message}`);
    return {};
  }
}

/**
 * The CV path. data/pdf-index.tsv is written by generate-pdf.mjs and is the
 * machine-maintained mapping; the report's **PDF:** header is agent-written, so
 * it is only the fallback.
 */
function resolveCvPath(num, reportText) {
  const index = join(ROOT, 'data/pdf-index.tsv');
  if (existsSync(index)) {
    for (const line of readFileSync(index, 'utf8').split('\n')) {
      if (line.startsWith('#') || !line.trim()) continue;
      const [rep, pdf] = line.split('\t');
      if (rep?.trim() === num && pdf?.trim()) {
        const abs = resolve(ROOT, pdf.trim());
        if (existsSync(abs)) return abs;
      }
    }
  }
  const header = headerField(reportText, 'PDF');
  if (!header || /not generated/i.test(header)) return null;
  const abs = resolve(ROOT, header);
  return existsSync(abs) ? abs : null;
}

/** A letter is used only if it already exists. Never composed here. */
function resolveCoverLetter(num, slug) {
  const candidates = [
    join(ROOT, 'output', `cover-letter-${slug}.md`),
    join(ROOT, 'output', `${num}-cover-letter.md`),
    join(ROOT, 'output', `${slug}-cover-letter.md`),
  ];
  return candidates.find((p) => existsSync(p)) ?? null;
}

// ---------------------------------------------------------------- building

export function slugOf(reportFile) {
  // reports/011-queue-it-2026-09-10.md -> queue-it
  return basename(reportFile, '.md').replace(/^\d+-/, '').replace(/-\d{4}-\d{2}-\d{2}$/, '');
}

export function hostOf(url) {
  try {
    return new URL(url).host;
  } catch {
    return null;
  }
}

function sha256(path) {
  return createHash('sha256').update(readFileSync(path)).digest('hex');
}

function loadProfileDoc() {
  const p = join(ROOT, 'config/profile.yml');
  if (!existsSync(p)) fail('no config/profile.yml');
  return yaml.load(readFileSync(p, 'utf8')) ?? {};
}

function loadProfile(doc) {
  // visa_status is not under candidate: in profile.yml, but it is an identity
  // fact a form asks for, so it is folded in here rather than special-cased at
  // every consumer.
  const candidate = { ...(doc.candidate ?? {}) };
  if (doc.visa_status && !candidate.visa_status) candidate.visa_status = doc.visa_status;
  if (doc.location?.visa_status && !candidate.visa_status) candidate.visa_status = doc.location.visa_status;
  return candidate;
}

/**
 * Which PDF gets attached: the per-role tailored CV, or one fixed file.
 *
 *   cv:
 *     attach: tailored                    # default — the pdf mode's output
 *     attach: "data/My_CV.pdf"            # always attach this one
 *
 * A configured path that does not exist is a HARD FAILURE, never a fall back to
 * the tailored CV. Silently attaching a different document than the one asked
 * for is the exact failure this whole handoff is built to prevent, and it would
 * be invisible: the bundle still contains a plausible cv.pdf.
 */
export function resolveAttachMode(doc, override) {
  const raw = override ?? doc?.cv?.attach ?? 'tailored';
  const value = String(raw).trim();
  if (!value || value.toLowerCase() === 'tailored') return { mode: 'tailored', path: null };
  const abs = resolve(ROOT, value);
  if (!existsSync(abs)) {
    fail(`cv.attach points at "${value}", which does not exist (resolved to ${abs}).\n` +
         '  Fix the path in config/profile.yml, or set it to "tailored".\n' +
         '  Refusing to fall back to the tailored CV: attaching a different document\n' +
         '  than the one configured would be invisible in the finished bundle.');
  }
  return { mode: 'original', path: abs };
}

/**
 * facts.md is mechanically derived from profile.yml — field to line, no
 * summarising, no inference. Anything not on this page is not a fact the runner
 * has, and NEVER_GUESS says so explicitly rather than leaving it implied.
 */
const FACT_FIELDS = [
  ['full_name', 'Full name'],
  ['email', 'Email'],
  ['phone', 'Phone'],
  ['location', 'Location'],
  ['linkedin', 'LinkedIn'],
  ['github', 'GitHub'],
  ['portfolio_url', 'Portfolio'],
  ['current_title', 'Current job title'],
  ['current_employer', 'Current employer'],
  ['resident_in_denmark', 'Currently resident in Denmark'],
  // visa_status is authoritative and lives in profile.yml. Omitting it forced
  // the agent to infer work authorisation from cv.md prose while facts.md told
  // it never to guess work authorisation — a contradiction it happened to
  // resolve correctly on the Queue-it form. The never-guess entry already reads
  // "beyond what is stated above", so stating it here settles the question
  // instead of leaving it to interpretation.
  ['visa_status', 'Work authorisation'],
];

/**
 * The usable facts, mechanically filtered. A TODO placeholder is treated as
 * absent: profile.yml's own header warns that TODO values must never reach
 * generated content, and a form field filled with "TODO: ask" is worse than an
 * empty one. facts.md and job.json's candidate block both derive from here, so
 * the two can never disagree.
 */
export function candidateFacts(candidate) {
  const out = {};
  for (const [key] of FACT_FIELDS) {
    const v = candidate?.[key];
    if (v === undefined || v === null || v === '' || /^TODO/i.test(String(v))) continue;
    out[key] = v;
  }
  return out;
}

export function buildFacts(candidate) {
  const usable = candidateFacts(candidate);
  const lines = FACT_FIELDS
    .filter(([key]) => key in usable)
    .map(([key, label]) => `- ${label}: ${usable[key]}`);

  return [
    '# Identity facts',
    '',
    'Copy these verbatim into matching form fields. Generated mechanically from',
    'config/profile.yml — every line restates a primary source.',
    '',
    ...lines,
    '',
    '# Do not answer from this file',
    '',
    'Nothing here answers the following. Leave the field empty and record the',
    'question in the run report instead of guessing:',
    '',
    ...NEVER_GUESS.map((s) => `- ${s}`),
    '',
  ].join('\n');
}

// ---------------------------------------------------------------- selecting

function collectCandidates(rows, opts) {
  const out = [];
  for (const row of rows) {
    const status = String(row.status ?? '').trim().toLowerCase();
    const num = reportNumOf(row);
    const score = parseScore(row.score);

    if (opts.only && num !== opts.only) continue;
    if (!opts.only && status !== EXPORTABLE_STATUS) continue;
    if (!num) continue;
    if (!opts.only && (score === null || score < opts.minScore)) continue;

    const reportFile = findReportFile(num);
    if (!reportFile) {
      console.error(`  skip ${num}: no report file in reports/`);
      continue;
    }
    const text = readFileSync(reportFile, 'utf8');
    const summary = machineSummary(text);
    const url = headerField(text, 'URL') ?? row.url ?? null;
    if (!url) {
      console.error(`  skip ${num}: report has no **URL:** header`);
      continue;
    }
    // With a fixed attachment configured, a missing tailored CV is not a reason
    // to skip the job — that CV is never going to be attached.
    const cv = opts.attach.mode === 'original' ? opts.attach.path : resolveCvPath(num, text);
    if (!cv) {
      console.error(`  skip ${num}: no CV PDF — run the pdf mode first`);
      continue;
    }
    // The tracker is the index a human reasons about; the Machine Summary is
    // machine-written. A disagreement means one of them was hand-edited.
    if (summary.score != null && score != null && Number(summary.score) !== score) {
      console.error(`  warning ${num}: tracker says ${score}, Machine Summary says ${summary.score}`);
    }
    out.push({ num, row, reportFile, text, summary, url, cv, score });
  }
  return out;
}

// ---------------------------------------------------------------- exporting

/**
 * Does this letter name this company? A sha256 proves a file is intact, not
 * that it is the right file, and the disaster worth preventing is company A's
 * letter inside company B's bundle. Matching the first token keeps "Queue-it
 * ApS" matching a letter that says "Queue-it"; an empty company cannot be
 * checked, so it passes rather than blocking every export on a missing field.
 */
export function letterNamesCompany(letterText, company) {
  const head = String(company ?? '').trim().split(/\s+/)[0];
  if (!head) return true;
  return letterText.toLowerCase().includes(head.toLowerCase());
}

function alreadyExported(outRoot, dirName) {
  return existsSync(join(outRoot, dirName)) || existsSync(join(outRoot, DONE_DIR, dirName));
}

function exportJob(job, outRoot, candidate, opts) {
  const slug = slugOf(job.reportFile);
  const dirName = `${job.num}-${slug}`;

  if (!opts.force && alreadyExported(outRoot, dirName)) {
    console.log(`  skip ${dirName} (already exported)`);
    return null;
  }

  const company = job.summary.company || job.row.company || '';
  const letterSrc = resolveCoverLetter(job.num, slug);

  // A checksum proves a file is intact, not that it is the RIGHT file. The
  // disaster this guards is company A's letter inside company B's bundle, so
  // assert the letter actually names the company before it can travel.
  if (letterSrc) {
    if (!letterNamesCompany(readFileSync(letterSrc, 'utf8'), company)) {
      fail(`${dirName}: cover letter ${basename(letterSrc)} never mentions "${company}" — refusing to export a bundle whose letter may belong to another application`);
    }
  }

  if (opts.dryRun) {
    console.log(`  would export ${dirName}  (cv.pdf + cv.md + facts${letterSrc ? ' + cover-letter' : ', no cover letter'})`);
    return dirName;
  }

  const dir = join(outRoot, dirName);
  // A --force re-export into a surviving directory used to hash whatever was
  // already there — including the PREVIOUS job.json, which the new one then
  // invalidated, so every re-exported bundle failed its own integrity check.
  // Caught by that check rather than by a test, which is the check earning its
  // keep; removing the directory also stops a stale file outliving its slot.
  if (existsSync(dir)) rmSync(dir, { recursive: true, force: true });
  mkdirSync(dir, { recursive: true });
  copyFileSync(job.cv, join(dir, 'cv.pdf'));
  writeFileSync(join(dir, 'facts.md'), buildFacts(candidate));
  // cv.md, not just the PDF: the runner answers factual questions about her
  // experience from the markdown, and a bundle that cannot answer them without
  // reaching back into career-ops is not self-contained.
  const cvMarkdown = join(ROOT, 'cv.md');
  if (!existsSync(cvMarkdown)) fail(`${dirName}: no cv.md at the career-ops root`);
  copyFileSync(cvMarkdown, join(dir, 'cv.md'));
  if (letterSrc) copyFileSync(letterSrc, join(dir, 'cover-letter.md'));

  const files = {};
  for (const name of readdirSync(dir)) {
    if (name === 'job.json') continue;   // the manifest cannot describe itself
    files[name] = { sha256: sha256(join(dir, name)), bytes: statSync(join(dir, name)).size };
  }

  const manifest = {
    report: job.num,
    company,
    role: job.summary.role || job.row.role || '',
    score: job.score,
    url: job.url,
    posting_host: hostOf(job.url),
    // The board hands off to the employer's real ATS, so the runner learns the
    // second host on first contact and writes it back. Restricting navigation
    // to posting_host alone would kill a run before it reaches a form.
    apply_host: null,
    work_auth: job.summary.work_auth ?? null,
    legitimacy_tier: job.summary.legitimacy_tier ?? null,
    final_decision: job.summary.final_decision ?? null,
    hard_stops: job.summary.hard_stops ?? [],
    cv_mode: opts.attach.mode,
    candidate: candidateFacts(candidate),
    cover_letter: letterSrc ? 'cover-letter.md' : null,
    exported_at: new Date().toISOString(),
    source: {
      tracker_row: job.row.num,
      report_file: `reports/${basename(job.reportFile)}`,
      cv_source: job.cv.startsWith(ROOT) ? job.cv.slice(ROOT.length + 1) : job.cv,
    },
    files,
  };
  writeFileSync(join(dir, 'job.json'), `${JSON.stringify(manifest, null, 2)}\n`);

  console.log(`  exported ${dirName}${letterSrc ? '' : '  (no cover letter)'}`);
  return dirName;
}

// ---------------------------------------------------------------- main

function parseFlags(argv) {
  const val = (f) => {
    const i = argv.indexOf(f);
    return i >= 0 ? argv[i + 1] : null;
  };
  const rawMin = val('--min-score');
  const min = rawMin === null ? DEFAULT_MIN_SCORE : Number(rawMin);
  if (Number.isNaN(min)) fail(`--min-score expects a number, got "${rawMin}"`);
  const rawReport = val('--report');
  return {
    attachOverride: val('--cv'),
    minScore: min,
    only: rawReport ? String(rawReport).padStart(3, '0') : null,
    out: val('--out') ? resolve(val('--out')) : DEFAULT_OUT,
    dryRun: argv.includes('--dry-run'),
    force: argv.includes('--force'),
  };
}

function main() {
  const argv = process.argv.slice(2);
  if (argv.includes('-h') || argv.includes('--help')) {
    console.log(readFileSync(fileURLToPath(import.meta.url), 'utf8').split('\n').slice(1, 46).join('\n'));
    return;
  }
  const opts = parseFlags(argv);
  const profileDoc = loadProfileDoc();
  const candidate = loadProfile(profileDoc);
  opts.attach = resolveAttachMode(profileDoc, opts.attachOverride);
  const rows = loadTrackerRows(readTrackerPath());
  const jobs = collectCandidates(rows, opts);

  const scope = opts.only ? `report ${opts.only}` : `status Evaluated, score >= ${opts.minScore}`;
  if (opts.attach.mode === 'original') {
    const rel = opts.attach.path.startsWith(ROOT) ? opts.attach.path.slice(ROOT.length + 1) : opts.attach.path;
    console.log(`apply-queue: attaching the SAME CV to every application: ${rel}`);
  }
  console.log(`apply-queue: ${jobs.length} candidate(s) (${scope})`);
  if (jobs.length === 0) return;

  if (!opts.dryRun) mkdirSync(opts.out, { recursive: true });
  const written = jobs.map((j) => exportJob(j, opts.out, candidate, opts)).filter(Boolean);

  console.log(`\n${opts.dryRun ? 'would export' : 'exported'} ${written.length} bundle(s) to ${opts.out}`);
  if (written.length > 0 && !opts.dryRun) {
    console.log('Review each bundle, then: cd apply-runner && uv run python run.py <dir>');
    console.log(`After a real submit, move the dir to ${join(opts.out, DONE_DIR)} and run set-status.mjs.`);
  }
}

if (isMainModule(import.meta.url)) main();
