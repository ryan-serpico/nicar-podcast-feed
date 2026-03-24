> **[Support investigative journalism — donate to IRE](https://www.ire.org/donate/)**

# NICAR 2026 Podcast Feed

A podcast RSS feed for audio recordings from the [NICAR 2026](https://www.ire.org/training/conferences/nicar-2026/) data journalism conference (Indianapolis, March 5–8, 2026).

If you'd like me to go farther back in time, show your interest by giving this repo a star ⭐.

## Subscribe

Copy this feed URL into your podcast app:

```
https://ryan-serpico.github.io/nicar-podcast-feed/feed.xml
```

## How it works

A Python script (`generate_feed.py`) fetches session data from IRE's public JSON endpoints, joins audio recordings with session descriptions and speaker bios, and generates a standard podcast RSS feed. GitHub Actions runs the script daily to pick up newly posted recordings.

## Local development

```bash
python3 generate_feed.py
# Output: docs/feed.xml
```

No dependencies beyond Python 3.10+ stdlib.
