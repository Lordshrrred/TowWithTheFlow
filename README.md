# Vibration of Awesome

**vibrationofawesome.com** — Hugo static site deployed via Netlify.

Roots in the Earth, Crown in the Stars. The Future is Ours.

---

## Site Architecture

```
/                       → Hugo homepage (layouts/index.html)
/posts/                 → Hugo blog (content/posts/)
/blog/                  → Dual-blog hub (static/blog/index.html)
/blog/matt/             → From the Forest Temple — Matt Dunn's personal lane
/blog/boombot/          → Boom Frequency — Matty BoomBoom AI SEO lane
/art-store/             → Wieldable Art Store (static/art-store/index.html)
/aura/                  → Aura experience (static/aura/index.html)
```

---

## Dual-Blog Content Engine

### Quick Start

```bash
# Install dependencies
npm install

# Copy env template and fill in your API keys
cp .env.example .env
```

### Generate a Blog Post

```bash
# Matt lane — personal voice, raw + honest
node scripts/generate-post.js --lane matt --title "Why I Spent 20 Years Doing Internet Marketing Wrong"

# BoomBot lane — SEO-optimized, Matty BoomBoom voice
node scripts/generate-post.js --lane boombot --keyword "how to use claude api for musicians" --topic "AI tools for independent artists"
```

**What it does:**
1. Calls the Claude API with the appropriate system prompt for each lane
2. Generates full blog post as markdown
3. Converts to HTML and writes to `static/blog/[lane]/posts/[slug].html`
4. Updates `static/_data/[lane]-posts.json` with post metadata
5. Homepage feed (`/_data/`) auto-updates when you push

### Syndicate a Post to Social Media

```bash
node scripts/syndicate.js --lane boombot --slug "how-to-use-claude-api-for-musicians"
```

**What it does:**
- Calls Claude to generate platform-specific captions (Facebook, Instagram, Twitter thread)
- Posts to each platform via their APIs
- Logs success/failure per platform independently

### SEO Keyword Research

```bash
node scripts/seo-research.js --topic "AI tools for musicians"
```

**What it does:**
- Generates 20 long-tail keyword variations via Claude
- Outputs formatted list to terminal
- Saves results to `static/_data/topic-queue.json`

---

## Blog Lanes

### 🌿 From the Forest Temple (`/blog/matt/`)
- **Author:** Matt Dunn
- **Voice:** Raw, unfiltered, first person. Real experiences, real frustrations, real wins. No SEO agenda.
- **Aesthetic:** Forest green + deep amber
- **When to use:** Sharing personal stories, lessons from the trenches, Forest Temple system reflections

### ⚡ Boom Frequency (`/blog/boombot/`)
- **Author:** Matty BoomBoom (AI persona)
- **Voice:** Helpful, eccentric, transmission-style. Spiritual seekers + neurodivergent creators + AI-curious musicians.
- **Aesthetic:** Electric cyan on deep black, frequency/wave motifs
- **When to use:** SEO-targeted content, long-tail keyword posts, guides and how-tos

---

## Deployment

Netlify auto-deploys on every push to `main`. No manual deploy needed.

Hugo builds the site → static HTML served globally via Netlify CDN.

### Environment Variables Required

```
NETLIFY_AUTH_TOKEN    → In GitHub repo secrets (for Actions deploy)
NETLIFY_SITE_ID       → In GitHub repo secrets
```

---

## Local Development

```bash
# Run Hugo dev server
hugo server -D

# Site is available at http://localhost:1313
```

---

## Required API Keys (`.env`)

```env
ANTHROPIC_API_KEY=          # Required for post generation + syndication captions
FACEBOOK_PAGE_ID=           # Facebook page syndication
FACEBOOK_ACCESS_TOKEN=      # Facebook Graph API
INSTAGRAM_ACCOUNT_ID=       # Instagram account (via Meta Business)
TWITTER_API_KEY=            # Twitter/X API v2
TWITTER_API_SECRET=
TWITTER_ACCESS_TOKEN=
TWITTER_ACCESS_SECRET=
```

See `.env.example` for the full template.

---

## Post Index Format

`static/_data/matt-posts.json` and `static/_data/boombot-posts.json`:

```json
[
  {
    "title": "Post Title Here",
    "slug": "post-slug-here",
    "date": "2026-03-01",
    "excerpt": "First 150 characters of post body...",
    "url": "/blog/matt/posts/post-slug-here.html",
    "tags": ["tag1", "tag2"]
  }
]
```

Posts are stored newest-first. The homepage and lane index pages display the latest 3.

---

*© 2026 Vibration of Awesome*
