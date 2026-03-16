import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');

const MONTHS = ['January','February','March','April','May','June',
                'July','August','September','October','November','December'];

function monthYear(dateStr) {
  const [, m] = dateStr.split('-');
  return `${MONTHS[parseInt(m, 10) - 1]} ${dateStr.split('-')[0]}`;
}
function isoDate(dateStr) {
  return `${dateStr}T00:00:00.000Z`;
}

// Canonical slug map: user-supplied name -> actual directory slug
// Correct dates per user specification (all unique)
const CORRECT_DATES = {
  'how-to-find-happiness-without-a-partner':          '2016-06-19',
  'light-workers-communication-impacting-the-masses': '2016-06-17',
  'self-love-acceptance':                             '2016-06-15',
  'qi-gong-understanding-chi-energy':                 '2016-06-12',
  'vibration-of-awesome':                             '2016-05-20',
  'paradigm-of-abundance':                            '2016-05-18',
  'empower-your-life':                                '2016-05-16',
  'synonyms-for-awesome':                             '2016-01-16',
  'law-of-attraction-manifesting-abundance':          '2015-12-07',
  'ayahuasca-experience':                             '2015-08-20',
  'the-most-awesome-thing-ever':                      '2015-07-18',
  'the-ayahuasca-experience-is-it-your-time':         '2015-03-27',
};

// ── 1. Update matt-posts.json ────────────────────────────────────────────────
const jsonPath = path.join(ROOT, 'static', '_data', 'matt-posts.json');
const posts = JSON.parse(fs.readFileSync(jsonPath, 'utf8'));

for (const post of posts) {
  if (CORRECT_DATES[post.slug] !== undefined) {
    post.date = CORRECT_DATES[post.slug];
  }
}

// Sort newest-first overall
posts.sort((a, b) => b.date.localeCompare(a.date));

fs.writeFileSync(jsonPath, JSON.stringify(posts, null, 2), 'utf8');
console.log('Updated matt-posts.json (sorted newest-first):');
posts.forEach(p => console.log(`  ${p.date}  ${p.slug}`));

// ── 2. Update each archive HTML ──────────────────────────────────────────────
let updated = 0, skipped = 0;

for (const [slug, correctDate] of Object.entries(CORRECT_DATES)) {
  const htmlPath = path.join(ROOT, 'static', 'blog', 'matt', 'posts', slug, 'index.html');
  if (!fs.existsSync(htmlPath)) {
    console.warn(`  MISSING: ${htmlPath}`);
    skipped++;
    continue;
  }

  let html = fs.readFileSync(htmlPath, 'utf8');
  const newMonthYear = monthYear(correctDate);

  // datePublished in JSON-LD
  html = html.replace(/"datePublished":"[^"]*"/, `"datePublished":"${isoDate(correctDate)}"`);

  // archive-badge: "Originally published Month YYYY"
  html = html.replace(
    /Originally published [A-Za-z]+ \d{4}/g,
    `Originally published ${newMonthYear}`
  );

  // First <span> inside .post-meta: the date display
  // Pattern anchored to the post-meta div to avoid touching author/read-time spans
  html = html.replace(
    /(<div class="post-meta">[\s\S]*?<span>)([A-Za-z]+ \d{4})(<\/span>)/,
    `$1${newMonthYear}$3`
  );

  // Belt-and-suspenders: any remaining stale "Jedi Light Warrior"
  html = html.replace(/Jedi Light Warrior/g, 'Matt Dunn');

  fs.writeFileSync(htmlPath, html, 'utf8');
  console.log(`  ${slug} -> ${newMonthYear}`);
  updated++;
}

console.log(`\nDone. Updated ${updated} HTML files, skipped ${skipped}.`);
