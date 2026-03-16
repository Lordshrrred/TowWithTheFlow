import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');

const MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December'];

function monthLabel(dateStr) {
  const [, m] = dateStr.split('-');
  return MONTHS[parseInt(m, 10) - 1];
}
function yearLabel(dateStr) {
  return dateStr.split('-')[0];
}
function monthYearLabel(dateStr) {
  return `${monthLabel(dateStr)} ${yearLabel(dateStr)}`;
}

// Correct dates per user specification
const CORRECT_DATES = {
  'self-love-acceptance':                          '2015-08-28',
  'qi-gong-understanding-chi-energy':              '2015-05-08',
  'ayahuasca-experience':                          '2015-08-20',
  'the-ayahuasca-experience-is-it-your-time':     '2015-03-27',
  'how-to-find-happiness-without-a-partner':       '2015-04-15',
  'light-workers-communication-impacting-the-masses': '2015-02-10',
  'the-most-awesome-thing-ever':                   '2015-01-22',
  'synonyms-for-awesome':                          '2015-01-05',
  'law-of-attraction-manifesting-abundance':       '2015-03-10',
};

// --- 1. Update matt-posts.json ---
const jsonPath = path.join(ROOT, 'static', '_data', 'matt-posts.json');
const posts = JSON.parse(fs.readFileSync(jsonPath, 'utf8'));

for (const post of posts) {
  if (CORRECT_DATES[post.slug]) {
    post.date = CORRECT_DATES[post.slug];
  }
}

// Sort: non-archive first (newest to oldest), then archives (newest to oldest)
const current = posts.filter(p => !p.isArchive).sort((a, b) => b.date.localeCompare(a.date));
const archives = posts.filter(p => p.isArchive).sort((a, b) => b.date.localeCompare(a.date));
const sorted = [...current, ...archives];

fs.writeFileSync(jsonPath, JSON.stringify(sorted, null, 2), 'utf8');
console.log('Updated matt-posts.json');
sorted.forEach(p => console.log(' ', p.date, p.slug));

// --- 2. Update each archive post HTML ---
for (const [slug, correctDate] of Object.entries(CORRECT_DATES)) {
  const htmlPath = path.join(ROOT, 'static', 'blog', 'matt', 'posts', slug, 'index.html');
  if (!fs.existsSync(htmlPath)) {
    console.warn(`  MISSING: ${slug}`);
    continue;
  }

  let html = fs.readFileSync(htmlPath, 'utf8');
  const newMonthYear = monthYearLabel(correctDate);
  const newIso = `${correctDate}T00:00:00.000Z`;

  // Fix datePublished in JSON-LD (e.g. "datePublished":"2016-06-19T00:00:00.000Z")
  html = html.replace(/"datePublished":"[^"]*"/, `"datePublished":"${newIso}"`);

  // Fix archive-badge text: "Originally published Month YYYY"
  // Matches any "Originally published [Month] [YYYY]" pattern
  html = html.replace(
    /Originally published [A-Za-z]+ \d{4}/g,
    `Originally published ${newMonthYear}`
  );

  // Fix post-meta date span: standalone "Month YYYY" in a <span>
  // Pattern: <span>Month YYYY</span>  (first span in post-meta)
  html = html.replace(
    /(<div class="post-meta">[\s\S]*?<span>)[A-Za-z]+ \d{4}(<\/span>)/,
    `$1${newMonthYear}$2`
  );

  // Fix any "Jedi Light Warrior" references (author replacement)
  html = html.replace(/Jedi Light Warrior/g, 'Matt Dunn');

  fs.writeFileSync(htmlPath, html, 'utf8');
  console.log(`  Updated ${slug} -> ${newMonthYear}`);
}

console.log('\nDone.');
