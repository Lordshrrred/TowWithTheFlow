# Personal Photos

Drop your personal photos here to use as fallback images when Pexels is unavailable or
when you want a more personal, authentic visual for syndicated posts.

## How it works

When a post is syndicated, `scripts/select-image.js` first tries to fetch a relevant image
from the Pexels API using the post's keyword or topic. If Pexels fails (missing API key,
no results, network error), it falls back to a **random image from this folder**.

## Supported formats

`.jpg` · `.jpeg` · `.png` · `.webp` · `.gif` · `.avif`

## Recommendations

- Add 10–20 photos that represent the vibe of the site — EarthStar performances, studio
  shots, nature/forest scenes, keyboard/gear photos, cosmic/space imagery, etc.
- Use landscape orientation (wider than tall) for best results across platforms.
- Aim for 1200×630px or larger for quality social media display.
- Name files descriptively: `earthstar-live-2024.jpg`, `forest-temple-desk.jpg`, etc.

## Notes

- Files starting with `.` are ignored.
- Photos are served at `https://vibrationofawesome.com/personal-photos/<filename>` once deployed.
- This folder is committed to git (photos included), so keep file sizes reasonable.
  Compress images before adding. Target ≤ 500KB per photo.
