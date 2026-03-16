import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');

const fixes = [
  { slug: 'synonyms-for-awesome',
    from: 'Synonyms For Awesome: Other Words For Awesome &#8211; You Source For Alternative Awesoness',
    to:   'Synonyms For Awesome - Other Words For Awesome' },
  { slug: 'the-most-awesome-thing-ever',
    from: 'The Most Awesome Thing Ever Is Deep &#038; Changing The World',
    to:   'The Most Awesome Thing Ever Is Deep and Changing The World' },
  { slug: 'qi-gong-understanding-chi-energy',
    from: 'Qi Gong &#8211; Understanding Chi Energy Within Your Body',
    to:   'Qi Gong - Understanding Chi Energy Within Your Body' },
  { slug: 'ayahuasca-experience',
    from: 'The Near Death of My Ego &#8211; A Truly Personal Ayahuasca Experience',
    to:   'The Near Death of My Ego - A Truly Personal Ayahuasca Experience' },
  // also fix &#8230; (ellipsis) appearing in lightworkers post
  { slug: 'light-workers-communication-impacting-the-masses',
    from: '&#8230;',
    to:   '...' },
];

for (const { slug, from, to } of fixes) {
  const file = path.join(ROOT, 'static', 'blog', 'matt', 'posts', slug, 'index.html');
  if (!fs.existsSync(file)) { console.log('SKIP:', slug); continue; }
  let html = fs.readFileSync(file, 'utf8');
  const before = html;
  html = html.split(from).join(to);
  if (html !== before) {
    fs.writeFileSync(file, html, 'utf8');
    console.log('FIXED:', slug, '->', to.slice(0, 40));
  } else {
    console.log('NOOP (not found):', slug, from.slice(0, 40));
  }
}
