// tests/providers/jobindex.test.mjs
import { pass, fail, ROOT } from '../helpers.mjs';
import { join } from 'path';
import { pathToFileURL } from 'url';

console.log('\nProvider — jobindex');

// A trimmed real feed item: description is DOUBLE-escaped as Jobindex serves it.
const FEED = `<?xml version="1.0"?><rss><channel>
<title>Jobindex - Ledige job indeholdende ordet product manager</title>
<item>
  <title>Advanced Technical Specialist, Sensors, Terma A/S</title>
  <link>https://www.jobindex.dk/vis-job/h1682964</link>
  <pubDate>Mon, 7 Sep 2026 00:00:00 +0200</pubDate>
  <description>&amp;#x3C;h4&amp;#x3E;&amp;#x3C;A HREF=&amp;#x22;x&amp;#x22;&amp;#x3E;Advanced Technical Specialist, Sensors&amp;#x3C;/a&amp;#x3E;&amp;#x3C;/h4&amp;#x3E;&amp;#x3C;span class=&amp;#x22;jix_robotjob--area&amp;#x22;&amp;#x3E;Lystrup&amp;#x3C;/span&amp;#x3E;</description>
</item>
<item>
  <title>Produktchef, ROSE POULTRY A/S</title>
  <link>http://insecure.example.com/vis-job/h1</link>
  <description>x</description>
</item>
</channel></rss>`;

try {
  const mod = await import(pathToFileURL(join(ROOT, 'providers/jobindex.mjs')).href);
  const jobindex = mod.default;
  const { parseJobindexFeed, splitJobindexTitle, feedUrlFor, parseJobindexConfig } = mod;

  if (jobindex.id === 'jobindex') pass('jobindex.id is "jobindex"');
  else fail(`jobindex.id is ${JSON.stringify(jobindex.id)}`);

  // detect()
  if (jobindex.detect({ name: 'Jobindex', provider: 'jobindex' })) pass('detect() claims explicit provider config');
  else fail('detect() missed explicit provider config');

  if (jobindex.detect({ name: 'x', careers_url: 'https://www.jobindex.dk/jobsoegning' })) pass('detect() claims a jobindex.dk careers_url');
  else fail('detect() missed a jobindex.dk careers_url');

  if (!jobindex.detect({ name: 'x', careers_url: 'https://jobs.ashbyhq.com/pleo' })) pass('detect() ignores another vendor');
  else fail('detect() wrongly claimed an ashby board');

  // A bare multi-word query is an OR search on Jobindex, so it must be quoted.
  const url = feedUrlFor('product manager', 2);
  if (url.includes('q=%22product+manager%22')) pass('feedUrlFor() phrase-quotes the query');
  else fail(`feedUrlFor() did not quote: ${url}`);
  if (url.includes('page=2')) pass('feedUrlFor() paginates');
  else fail(`feedUrlFor() lost the page: ${url}`);
  if (!feedUrlFor('product manager', 1).includes('page=')) pass('feedUrlFor() omits page=1');
  else fail('feedUrlFor() emitted a redundant page=1');
  if (feedUrlFor('"already quoted"').includes('q=%22already+quoted%22')) pass('feedUrlFor() does not double-quote');
  else fail('feedUrlFor() double-quoted an already-quoted query');

  // Title splits on the LAST comma — roles contain commas.
  const s = splitJobindexTitle('Advanced Technical Specialist, Sensors, Terma A/S');
  if (s.title === 'Advanced Technical Specialist, Sensors' && s.company === 'Terma A/S') pass('splitJobindexTitle() splits on the last comma');
  else fail(`splitJobindexTitle() = ${JSON.stringify(s)}`);

  const nc = splitJobindexTitle('Produktchef');
  if (nc.title === 'Produktchef' && nc.company === '') pass('splitJobindexTitle() handles a comma-less title');
  else fail(`splitJobindexTitle() comma-less = ${JSON.stringify(nc)}`);

  // Anonymised recruiter listings carry no ", Company" suffix; they must not
  // reach the pipeline with a blank company cell.
  const anon = parseJobindexFeed(FEED.replace('Advanced Technical Specialist, Sensors, Terma A/S', 'Senior Product Manager'));
  if (anon[0]?.company === '?') pass('a comma-less title yields the "?" unknown-employer marker');
  else fail(`anonymous listing company = ${JSON.stringify(anon[0]?.company)}`);

  // Feed parsing
  const jobs = parseJobindexFeed(FEED);
  if (jobs.length === 1) pass('parseJobindexFeed() drops the non-https item (SSRF guard)');
  else fail(`parseJobindexFeed() returned ${jobs.length} jobs, expected 1`);

  const j = jobs[0];
  if (j?.title === 'Advanced Technical Specialist, Sensors') pass('title comes from the description <h4>');
  else fail(`title = ${JSON.stringify(j?.title)}`);
  if (j?.company === 'Terma A/S') pass('company comes from the <title> suffix');
  else fail(`company = ${JSON.stringify(j?.company)}`);
  if (j?.location === 'Lystrup') pass('location comes from span.jix_robotjob--area');
  else fail(`location = ${JSON.stringify(j?.location)}`);
  if (j?.url === 'https://www.jobindex.dk/vis-job/h1682964') pass('url is the item <link>');
  else fail(`url = ${JSON.stringify(j?.url)}`);
  if (Number.isFinite(j?.postedAt)) pass('postedAt parsed from <pubDate>');
  else fail(`postedAt = ${JSON.stringify(j?.postedAt)}`);

  if (parseJobindexFeed(null).length === 0 && parseJobindexFeed('').length === 0) pass('parseJobindexFeed() tolerates junk input');
  else fail('parseJobindexFeed() threw or returned rows for junk input');

  // Config
  const cfg = parseJobindexConfig({ queries: ['product manager', ' '], max_pages: 999 });
  if (cfg.queries.length === 1 && cfg.maxPages === 20) pass('parseJobindexConfig() drops blanks and caps max_pages');
  else fail(`parseJobindexConfig() = ${JSON.stringify(cfg)}`);

  if (parseJobindexConfig({}).queries.length === 0) pass('parseJobindexConfig() returns no queries when unconfigured');
  else fail('parseJobindexConfig() invented a query');
} catch (err) {
  fail(`jobindex provider tests threw: ${err.stack}`);
}
