// tests/automation/apply-queue.test.mjs — pure-function cover for the handoff exporter.
import { join } from 'path';
import { pathToFileURL } from 'url';
import { pass, fail, ROOT } from '../helpers.mjs';

console.log('\nAutomation — apply-queue');

const mod = await import(pathToFileURL(join(ROOT, 'automation/apply-queue.mjs')).href);
const { parseScore, reportNumOf, slugOf, hostOf, headerField, machineSummary,
        buildFacts, letterNamesCompany } = mod;

const eq = (actual, expected, label) =>
  (JSON.stringify(actual) === JSON.stringify(expected)
    ? pass(label)
    : fail(`${label} — got ${JSON.stringify(actual)}, expected ${JSON.stringify(expected)}`));

// --- parseScore: a sentinel must be null, NEVER 0, or it would clear any floor
eq(parseScore('4.0/5'), 4.0, 'parseScore reads "4.0/5"');
eq(parseScore('3.5/5'), 3.5, 'parseScore reads "3.5/5"');
eq(parseScore('N/A'), null, 'parseScore returns null for the N/A sentinel');
eq(parseScore('—'), null, 'parseScore returns null for the em-dash sentinel');
eq(parseScore('-'), null, 'parseScore returns null for the hyphen sentinel');
eq(parseScore(''), null, 'parseScore returns null for an empty cell');
eq(parseScore(undefined), null, 'parseScore returns null for a missing cell');
eq(parseScore('0/5'), 0, 'parseScore reads a genuine zero as 0, not null');

// --- reportNumOf: the tracker link is the only reliable report pointer
eq(reportNumOf({ report: '[011](../reports/011-x-2026-01-01.md)' }), '011', 'reportNumOf reads a padded link');
eq(reportNumOf({ report: '[7](../reports/007-x.md)' }), '007', 'reportNumOf pads an unpadded link');
eq(reportNumOf({ report: '' }), null, 'reportNumOf returns null for an empty cell');
eq(reportNumOf({ report: 'pending' }), null, 'reportNumOf returns null when there is no link');

// --- slugOf: bundle names come from the report filename
eq(slugOf('reports/011-queue-it-2026-09-10.md'), 'queue-it', 'slugOf strips number and date');
eq(slugOf('reports/013-blue-water-shipping-2026-09-10.md'), 'blue-water-shipping', 'slugOf keeps inner hyphens');

// --- hostOf
eq(hostOf('https://careers.queue-it.com/jobs/1'), 'careers.queue-it.com', 'hostOf reads the host');
eq(hostOf('not a url'), null, 'hostOf returns null rather than throwing');

// --- headerField
const header = '# Evaluation\n\n**Score:** 4.0/5\n**URL:** https://example.com/j/1\n';
eq(headerField(header, 'URL'), 'https://example.com/j/1', 'headerField reads **URL:**');
eq(headerField(header, 'PDF'), null, 'headerField returns null for an absent field');

// --- machineSummary: malformed YAML must degrade, not throw
const good = '## Machine Summary\n\n```yaml\ncompany: "Acme"\nscore: 4.0\n```\n';
eq(machineSummary(good).company, 'Acme', 'machineSummary parses a well-formed block');
eq(machineSummary('no summary here'), {}, 'machineSummary returns {} when the block is absent');
const bad = '## Machine Summary\n\n```yaml\njd_signal: "a"; "b"\n```\n';
try {
  eq(machineSummary(bad), {}, 'machineSummary returns {} on unparseable YAML instead of throwing');
} catch (err) {
  fail(`machineSummary threw on bad YAML — ${err.message}`);
}

// --- letterNamesCompany: the anti-crossing guard
const letter = 'Dear Templafy team, I am applying for the Product Manager role.';
eq(letterNamesCompany(letter, 'Templafy'), true, 'letterNamesCompany accepts a matching letter');
eq(letterNamesCompany(letter, 'Queue-it ApS'), false, 'letterNamesCompany REJECTS another company\'s letter');
eq(letterNamesCompany(letter, 'templafy'), true, 'letterNamesCompany is case-insensitive');
eq(letterNamesCompany('Dear Queue-it team', 'Queue-it ApS'), true,
   'letterNamesCompany matches the first token, so a legal suffix does not break it');
eq(letterNamesCompany(letter, ''), true, 'letterNamesCompany passes when company is unknown (cannot check)');

// --- buildFacts: mechanical derivation, never inference
const facts = buildFacts({
  full_name: 'A Person', email: 'a@example.com', portfolio_url: '',
  current_title: 'TODO: ask', resident_in_denmark: true,
});
(facts.includes('- Full name: A Person') ? pass : fail)('buildFacts emits a present field');
(!facts.includes('Portfolio') ? pass : fail)('buildFacts omits an empty field');
(!facts.includes('TODO') ? pass : fail)('buildFacts omits a TODO placeholder rather than leaking it');
(facts.includes('Currently resident in Denmark: true') ? pass : fail)('buildFacts emits a boolean field');
(facts.includes('Salary expectations') ? pass : fail)('buildFacts lists salary as never-guess');
(facts.includes('EEO') ? pass : fail)('buildFacts lists EEO questions as never-guess');

// --- importing the module must not run the CLI
pass('importing apply-queue.mjs did not execute main()');

// --- visa_status: authoritative in profile.yml, so it must reach the bundle.
// Omitting it made facts.md say "never guess work authorisation" while the only
// source left was cv.md prose — a contradiction the agent resolved correctly on
// a live Queue-it form, but by interpretation rather than design.
const withVisa = buildFacts({ full_name: 'A', visa_status: 'Danish citizen — no sponsorship needed' });
(withVisa.includes('Work authorisation: Danish citizen') ? pass : fail)(
  'buildFacts states work authorisation when profile.yml has it');
const noVisa = buildFacts({ full_name: 'A' });
(!noVisa.includes('Work authorisation:') ? pass : fail)(
  'buildFacts omits work authorisation when the profile does not state it');
(noVisa.includes('Work authorisation, visa status') ? pass : fail)(
  'buildFacts still forbids guessing work authorisation when it is unstated');

// --- cv.attach: which PDF is attached to an application.
// The tailored CV is still generated; this only decides what travels.
const { resolveAttachMode } = mod;
eq(resolveAttachMode({}, null).mode, 'tailored', 'attach defaults to the tailored CV');
eq(resolveAttachMode({ cv: { attach: 'tailored' } }, null).mode, 'tailored',
   'attach: tailored is explicit and valid');
eq(resolveAttachMode({ cv: {} }, null).mode, 'tailored', 'an empty cv block still defaults');
eq(resolveAttachMode({ cv: { attach: '  ' } }, null).mode, 'tailored', 'a blank value defaults');
// a real file in the repo, used only to prove a configured path resolves
eq(resolveAttachMode({ cv: { attach: 'cv.md' } }, null).mode, 'original',
   'a path that exists selects the fixed attachment');
eq(resolveAttachMode({ cv: { attach: 'tailored' } }, 'cv.md').mode, 'original',
   '--cv overrides the profile setting');
