# AI Poster Generation

JFC can automatically generate unique collection posters using OpenAI's image generation API.

## Overview

AI posters are generated based on:
- Collection name and category
- Visual signatures of items in the collection
- Consistent artistic style per category (Films, Series, Cartoons)

## Setup

### 1. Get OpenAI API Key

1. Go to [OpenAI Platform](https://platform.openai.com/)
2. Create an account or sign in
3. Navigate to API Keys
4. Create a new API key
5. Add credits to your account

### 2. Configure Environment

```bash
# .env
OPENAI_API_KEY=sk-proj-your-api-key-here
OPENAI_ENABLED=true
```

### 3. Test Connection

```bash
jfc test-connections
```

Expected output:
```
┃ OpenAI     │ OK     │ Credits OK      │
```

## How It Works

### Generation Process

1. **Fetch Collection Items** - Get movies/shows in the collection
2. **Build Visual Signatures** - Create descriptions of visual elements
3. **Generate Prompt** - AI creates a detailed prompt based on:
   - Collection theme
   - Category style guide
   - Visual signatures of items
4. **Generate Image** - OpenAI creates the poster
5. **Upload to Jellyfin** - Poster is set for the collection

### Visual Signatures

Visual signatures describe the "look and feel" of each item:

```json
{
  "title": "Blade Runner 2049",
  "signature": "Neon-lit dystopian cityscape, blue and orange color palette,
                rain-soaked streets, holographic advertisements,
                brutalist architecture, moody atmospheric lighting"
}
```

### Category Styles

Each category has a distinct visual style:

| Category | Style |
|----------|-------|
| **FILMS** | Cinematic, dramatic lighting, movie poster aesthetic |
| **SÉRIES** | TV show promotional art, character-focused |
| **CARTOONS** | Animated, colorful, family-friendly |

## Configuration Options

```bash
# Enable AI generation
OPENAI_ENABLED=true

# Include item titles in signatures (better context, more tokens)
OPENAI_EXPLICIT_REFS=false

# Keep N old posters in history
OPENAI_POSTER_HISTORY_LIMIT=5

# Keep N prompt JSON files
OPENAI_PROMPT_HISTORY_LIMIT=10
```

## File Structure

Generated posters are organized by library and collection:

```
/data/posters/
├── Films/
│   └── Trending_Movies/
│       ├── poster.png          # Current poster
│       ├── history/            # Old versions
│       │   ├── 2024-01-01_120000.png
│       │   └── 2024-02-01_120000.png
│       └── prompts/            # Generation prompts
│           ├── 2024-01-01_120000.json
│           └── 2024-02-01_120000.json
├── Séries/
│   └── ...
└── Cartoons/
    └── ...
```

## Manual Poster Generation

Generate a poster for a specific collection:

```bash
# Basic usage
jfc generate-poster "Trending Movies" --category FILMS --library Films

# Force regeneration
jfc generate-poster "Trending Movies" --category FILMS --library Films --force
```

## Scheduled Regeneration

By default, all posters are regenerated monthly:

```bash
# Cron: 1st of each month at 4am
SCHEDULER_POSTERS_CRON=0 4 1 * *

# Disable automatic regeneration
SCHEDULER_POSTERS_CRON=
```

Force immediate regeneration:

```bash
jfc run --force-posters
```

## Manual Posters

You can also use manual posters instead of AI-generated ones:

```yaml
# In your collection YAML
collections:
  "My Collection":
    tmdb_trending_weekly: 20
    poster: my_custom_poster.png    # Path relative to posters directory
```

Place the file in `/data/posters/my_custom_poster.png`.

If the manual poster doesn't exist, JFC will fall back to AI generation.

## Cost Considerations

OpenAI image generation has costs:
- ~$0.04 per image (1024x1024)
- Monthly regeneration of 10 collections = ~$0.40/month

Tips to reduce costs:
- Set `SCHEDULER_POSTERS_CRON=` to disable auto-regeneration
- Use `--force-posters` only when needed
- Use manual posters for static collections

## Troubleshooting

### "No credits" Error

```
OpenAI: FAIL - No credits
```

Add credits to your OpenAI account at [platform.openai.com/account/billing](https://platform.openai.com/account/billing)

### Poor Quality Posters

Try:
1. Enable explicit refs: `OPENAI_EXPLICIT_REFS=true`
2. Ensure collection has enough items for context
3. Check the generated prompt in `/data/posters/.../prompts/`

### Poster Not Uploaded

Check logs for errors:
```bash
grep -i "poster" logs/jfc.log
```

Common issues:
- Jellyfin API permissions
- File size too large
- Network timeout

## Prompt Files

Each generation saves its prompt for debugging:

```json
{
  "collection": "Trending Movies",
  "category": "FILMS",
  "items_count": 20,
  "visual_signatures": [...],
  "generated_prompt": "Create a cinematic movie poster...",
  "timestamp": "2024-01-01T12:00:00"
}
```

## Template Customization

JFC uses Jinja2 templates for prompt generation. You can customize these templates to change the visual style of generated posters.

### Template Files

Templates are stored in `config/templates/`:

| File | Description |
|------|-------------|
| `base_structure.j2` | Main poster layout (text positioning, scene format) |
| `visual_signature.j2` | Prompt for generating visual signatures from metadata |
| `scene_description.j2` | Prompt for generating scene descriptions |
| `category_styles.yaml` | Artistic styles per category (FILMS, SERIES, CARTOONS) |
| `collection_themes.yaml` | Color palettes and moods based on collection keywords |

### Quick Start

1. Copy example templates:
   ```bash
   cp docs/examples/templates/*.j2 config/templates/
   cp docs/examples/templates/*.yaml config/templates/
   ```

2. Edit the templates in `config/templates/`

3. Restart JFC to apply changes

### Category Styles

Edit `category_styles.yaml` to add or modify categories:

```yaml
FILMS:
  poster_style: "Cinematic blockbuster"
  base_mood: "Ultra-detailed, dramatic lighting, epic scale."
  scene_context: "cinematic movie scene"
  lighting_style: "Dramatic three-point lighting with rim light"

# Add custom category
ANIME:
  poster_style: "Japanese anime"
  base_mood: "Dynamic, vibrant, stylized action."
  scene_context: "anime action scene"
  lighting_style: "Dramatic rim lighting with speed lines"
```

### Collection Themes

Edit `collection_themes.yaml` to define color palettes based on collection name keywords:

```yaml
# When collection name contains "horror"
horror:
  color_hint: "cold blues + sickly green + ember glow"
  mood_hint: "dread-filled, tension, suspense"
  scene_hint: "foggy corridor with unsettling silhouettes"

# Add custom theme
anime:
  color_hint: "neon pink + electric blue + vibrant orange"
  mood_hint: "dynamic, energetic, Japanese animation style"
  scene_hint: "stylized action with speed lines"
```

### Visual Signatures

Visual signatures are generated by GPT from movie/series metadata and cached in `data/cache/visual_signatures_cache.json`. This allows for consistent posters across regenerations.

To customize the signature generation, edit `visual_signature.j2`:

```jinja2
You are a visual design expert. Based on this movie/series metadata,
create an ICONIC VISUAL SIGNATURE.

Metadata:
- Genres: {{ genres }}
- Overview: {{ overview }}

Output format (ONE LINE, comma-separated):
[colors], [environment], [silhouette style], [motifs]
```

### Fallback Behavior

If a template file is missing from `config/templates/`, JFC uses built-in defaults. This allows you to:

- Only customize templates you need
- Update JFC without losing customizations
- Reset a template by deleting it from `config/templates/`

See [docs/examples/templates/](../examples/templates/) for complete examples.

## Next Steps

- [Configuration Guide](configuration.md) - Full settings reference
- [API Reference](api-reference.md) - Technical details
