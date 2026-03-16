import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const file = path.resolve(__dirname, '..', 'static', '_data', 'matt-posts.json');

function decodeEntities(str) {
  return str
    .replace(/&#8211;/g, '-')
    .replace(/&#8212;/g, '-')
    .replace(/&#038;/g, 'and')
    .replace(/&amp;/g, 'and')
    .replace(/&#8230;/g, '...')
    .replace(/&#8220;/g, '"')
    .replace(/&#8221;/g, '"')
    .replace(/&#8216;/g, "'")
    .replace(/&#8217;/g, "'")
    .replace(/&#160;/g, ' ')
    .replace(/&nbsp;/g, ' ');
}

// Also apply better titles where the extraction was awkward
const titleOverrides = {
  'synonyms-for-awesome':   'Synonyms For Awesome - Other Words For Awesome',
  'the-most-awesome-thing-ever': 'The Most Awesome Thing Ever Is Deep and Changing The World',
  'qi-gong-understanding-chi-energy': 'Qi Gong - Understanding Chi Energy Within Your Body',
  'ayahuasca-experience':   'The Near Death of My Ego - A Truly Personal Ayahuasca Experience',
};

const posts = JSON.parse(fs.readFileSync(file, 'utf8'));
for (const post of posts) {
  if (titleOverrides[post.slug]) {
    post.title = titleOverrides[post.slug];
  } else {
    post.title = decodeEntities(post.title);
  }
  post.excerpt = decodeEntities(post.excerpt);
}
fs.writeFileSync(file, JSON.stringify(posts, null, 2), 'utf8');
console.log('Cleaned matt-posts.json titles and excerpts');
posts.filter(p => p.isArchive).forEach(p => console.log(' ', p.date, p.title));
