"""Automatic poster generation using OpenAI gpt-image-1.5 and GPT-5.1."""

import base64
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import httpx
import yaml
from jinja2 import Environment, FileSystemLoader, BaseLoader, ChoiceLoader
from loguru import logger
from openai import AsyncOpenAI

from jfc.models.collection import CollectionConfig
from jfc.models.media import MediaItem


# =============================================================================
# CONSTANTS
# =============================================================================

MODEL_GPT_5_1 = "gpt-5.1"  # For scene descriptions and visual signatures
MODEL_GPT_IMAGE_1_5 = "gpt-image-1.5"
MODEL_DALL_E_3 = "dall-e-3"

# Timeout pour les appels API
API_TIMEOUT = httpx.Timeout(
    timeout=300.0,  # 5 minutes global
    connect=30.0,
)


# =============================================================================
# JINJA2 TEMPLATES - DEFAULT FALLBACKS
# =============================================================================

# Default Jinja2 environment (will be overridden if external templates exist)
_default_jinja_env = Environment(loader=BaseLoader(), autoescape=False)

# Base structure (IMMUTABLE) - applies to ALL posters
# This is the DEFAULT template - can be overridden by config/templates/base_structure.j2
DEFAULT_BASE_STRUCTURE_TEMPLATE = """{{ poster_style }} poster, vertical 2:3 ratio, photorealistic cinematic quality.

=== TYPOGRAPHY (CRITICAL - MUST BE EXACT) ===

TOP TEXT BLOCK - horizontally centered, positioned at exactly 12% from top edge:

Line 1: "{{ category }}" in BOLD UPPERCASE - STYLIZED TITLE
- Font: Heavy condensed sans-serif (like Bebas Neue or Impact)
- Size: 144pt equivalent, MASSIVE and dominant (bigger than everything else)
- Color: Vertical gradient from bright white (#FFFFFF) at top to light silver/gray (#C0C0C0) at bottom
- Subtle 3D effect: thin black outline/stroke (2px) + soft drop shadow (not too heavy)
- Metallic sheen effect for premium look
- Letter-spacing: wide tracking for cinematic impact
- Style like a Hollywood blockbuster movie title card

Line 2: "{{ collection_display_name }}" directly below, small gap (8px equivalent)
- Font: Same font family, medium weight
- Size: 72pt equivalent (60% of category size) - MUST BE CLEARLY READABLE
- Color: White with subtle orange/gold outer glow effect
- Black drop shadow for contrast
- Add a small thematic emoji icon before the text

BOTTOM LOGO - horizontally centered, positioned at exactly 92% from top (8% from bottom):
- Text "NETFLEX" only - NO background box
- Font: Bold condensed sans-serif, 48pt equivalent
- Color: Bright red (#E50914) like Netflix red
- Strong black drop shadow and black outline for readability
- Styled like the Netflix wordmark but with "NETFLEX"

=== SCENE ===

{{ scene_description }}

CRITICAL SCENE RULES:
- All objects must be grounded (on floor, held by characters, on surfaces)
- NO floating objects, NO items suspended in mid-air
- Scene must look like a real photograph or movie still
- Characters should be walking, standing, or interacting naturally

Color palette: {{ color_palette }}.
{{ mood_style }}

=== PHOTOREALISTIC RENDERING ===
- Shot with professional cinema camera, 35mm anamorphic lens
- Shallow depth of field with cinematic bokeh
- {{ lighting_style }}
- Real textures: skin pores, fabric weave, surface imperfections
- Subtle film grain for cinematic feel
- Natural color grading, no oversaturation

=== STRICT LAYOUT INVARIANTS ===
- Text positioning MUST be identical across all generated images
- Category text at 12% from top, collection name immediately below with 8px gap
- NETFLEX logo at 92% from top (8% from bottom)
- All text horizontally centered on the poster
- Subtle dark vignette/gradient at top and bottom for text readability
- Single coherent scene, NO collage or grid of images
- NO extra text, NO watermarks, NO additional logos besides NETFLEX"""

# TMDb genre ID to name mapping
TMDB_GENRES = {
    28: "Action", 12: "Adventure", 16: "Animation", 35: "Comedy",
    80: "Crime", 99: "Documentary", 18: "Drama", 10751: "Family",
    14: "Fantasy", 36: "History", 27: "Horror", 10402: "Music",
    9648: "Mystery", 10749: "Romance", 878: "Science Fiction",
    10770: "TV Movie", 53: "Thriller", 10752: "War", 37: "Western",
    10759: "Action & Adventure", 10762: "Kids", 10763: "News",
    10764: "Reality", 10765: "Sci-Fi & Fantasy", 10766: "Soap",
    10767: "Talk", 10768: "War & Politics",
}

# Prompt for generating visual signatures from metadata (not titles)
# This is the DEFAULT template - can be overridden by config/templates/visual_signature.j2
DEFAULT_VISUAL_SIGNATURE_TEMPLATE = """You are a visual design expert. Based on this movie/series metadata, create an ICONIC VISUAL SIGNATURE - the visual elements that would make a striking poster scene.

Metadata:
- Genres: {{ genres }}
- Overview: {{ overview }}

Create a visual signature with:
1. Signature color palette (2-3 colors that evoke the mood)
2. Environment type (where the scene takes place)
3. Character silhouette style (anonymous figures, no names)
4. Iconic visual motifs (props, lighting, atmosphere)

Output format (ONE LINE, comma-separated):
[colors], [environment], [silhouette style], [motifs]

Example: "deep crimson and midnight blue, rain-soaked neon city streets, trenchcoat-wearing detective silhouette, flickering neon signs and wet reflections"

Output ONLY the visual signature, nothing else."""

# Scene description prompt template - uses visual signatures
# This is the DEFAULT template - can be overridden by config/templates/scene_description.j2
DEFAULT_SCENE_PROMPT_TEMPLATE = """You are a cinematic poster designer creating a visually striking scene.

Collection theme: "{{ collection_name }}"
Category: {{ category }}
Mood: {{ mood_hint }}
Color palette: {{ color_hint }}

VISUAL ELEMENTS TO INCORPORATE (from top media in this collection):
{{ visual_signatures }}

Create a dramatic cinematic scene that NATURALLY BLENDS these visual elements into ONE coherent environment.

RULES:
1. Describe ONE unified cinematic scene - NOT a collage
2. The TOP visual elements (first 2-3) should be PROMINENT in the foreground
3. Secondary elements can appear as subtle background details
4. Use SILHOUETTES and ANONYMOUS FIGURES - no character names
5. Focus on ATMOSPHERE, LIGHTING, and ENVIRONMENT
6. All elements must be GROUNDED (on floor, held, on surfaces) - NO floating objects
7. Keep it 2-3 sentences max

GOOD example: "A tall silhouette with pointed ears stands in a bioluminescent jungle clearing, cyan light from glowing plants reflecting off their skin, while in the distance emerald green magical sparks swirl around a cloaked figure on a golden brick path, both gazing at a towering crystalline city where orange flames lick the skyline."

Output ONLY the scene description, nothing else."""

# Artistic direction per category
# This is the DEFAULT configuration - can be overridden by config/templates/category_styles.yaml
DEFAULT_CATEGORY_STYLES = {
    "FILMS": {
        "poster_style": "Cinematic blockbuster",
        "base_mood": "Ultra-detailed, dramatic lighting, epic scale, modern Hollywood spectacle.",
        "scene_context": "cinematic movie scene",
        "lighting_style": "Dramatic three-point lighting with rim light, golden hour ambiance or moody blue hour",
    },
    "SÉRIES": {
        "poster_style": "Prestige TV",
        "base_mood": "Ultra-detailed, binge-worthy, prestige TV aesthetics.",
        "scene_context": "prestige TV scene",
        "lighting_style": "Soft diffused lighting with dramatic shadows, intimate atmosphere",
    },
    "CARTOONS": {
        "poster_style": "Bright and colorful Pixar/Disney-style 3D animated",
        "base_mood": "Vibrant saturated colors, joyful atmosphere, family-friendly, whimsical and magical, 100% child-safe.",
        "scene_context": "cheerful animated adventure scene",
        "lighting_style": "Bright sunny lighting with rainbow-colored accents, magical sparkles and warm glows",
        "color_override": "bright primary colors (red, blue, yellow) + candy pastels + golden sunshine",
    },
}

# Collection type themes (for color palette and mood hints)
# This is the DEFAULT configuration - can be overridden by config/templates/collection_themes.yaml
DEFAULT_COLLECTION_THEMES = {
    # Trending/Popular
    "tendances": {
        "color_hint": "fiery orange + electric blue",
        "mood_hint": "high-energy, trending, viral sensation",
        "scene_hint": "dynamic action with multiple genre references",
    },
    "populaires": {
        "color_hint": "gold + orange + deep blue",
        "mood_hint": "crowd-pleasing, mainstream success",
        "scene_hint": "confident heroes and spectacular moments",
    },
    # Quality
    "top": {
        "color_hint": "deep blacks + gold accents + subtle blues",
        "mood_hint": "refined, prestigious, award-worthy",
        "scene_hint": "elegant composition with symbolic elements",
    },
    "mieux": {
        "color_hint": "warm tones + gold highlights",
        "mood_hint": "celebrated, acclaimed, top-rated",
        "scene_hint": "proud characters with stars and recognition symbols",
    },
    # Discovery
    "pépites": {
        "color_hint": "dark teal + crystal glow",
        "mood_hint": "intimate, discovery, hidden treasure",
        "scene_hint": "lone viewer discovering something precious",
    },
    "cachées": {
        "color_hint": "midnight blue + amber highlights",
        "mood_hint": "secret, underground, cult favorite",
        "scene_hint": "mysterious discovery atmosphere",
    },
    # New/Recent
    "nouveautés": {
        "color_hint": "neon blue + purple + warm orange",
        "mood_hint": "fresh, just released, contemporary",
        "scene_hint": "modern premiere atmosphere with recent release energy",
    },
    "récent": {
        "color_hint": "neon blue + purple + glossy reflections",
        "mood_hint": "current, fresh off the press",
        "scene_hint": "cinema foyer with new release posters",
    },
    # Status
    "cours": {
        "color_hint": "deep blues + warm signal glow",
        "mood_hint": "ongoing, unfolding, anticipation",
        "scene_hint": "characters walking forward, story continues",
    },
    "complètes": {
        "color_hint": "warm sunset tones",
        "mood_hint": "satisfying conclusion, bingeable",
        "scene_hint": "peaceful resolution, symbolic endings",
    },
    # Episodes
    "épisodes": {
        "color_hint": "electric blue + orange accents",
        "mood_hint": "suspenseful, cliffhanger, must-watch",
        "scene_hint": "frozen action moment, notification motifs",
    },
    "regardé": {
        "color_hint": "gold spotlights + midnight blue",
        "mood_hint": "global phenomenon, everyone watching",
        "scene_hint": "screens showing iconic moments",
    },
    # Genres
    "action": {
        "color_hint": "neon blue + fiery orange + metallic",
        "mood_hint": "explosive, kinetic, adrenaline",
        "scene_hint": "rain-soaked action with sparks and motion",
    },
    "comédie": {
        "color_hint": "warm sunshine + candy accents",
        "mood_hint": "joyful, fun, crowd-pleaser",
        "scene_hint": "bright comedic chase with exaggerated expressions",
    },
    "horreur": {
        "color_hint": "cold blues + sickly green + ember glow",
        "mood_hint": "dread-filled, tension, suspense",
        "scene_hint": "foggy corridor with unsettling silhouettes",
    },
    "science": {
        "color_hint": "deep space blue + teal neon + sand gold",
        "mood_hint": "epic scale, awe, wonder",
        "scene_hint": "vast sci-fi vista with colossal ships",
    },
    "français": {
        "color_hint": "navy + warm streetlamp gold",
        "mood_hint": "stylish, elegant, unmistakably French",
        "scene_hint": "Parisian night with classic cinema facade",
    },
    "cinéma": {
        "color_hint": "cinematic red + warm gold + deep blacks",
        "mood_hint": "glamorous, premiere, opening night",
        "scene_hint": "red carpet with spotlights and theater entrance",
    },
    # Kids
    "nina": {
        "color_hint": "pastel rainbow colors",
        "mood_hint": "joyful, magical, child-friendly",
        "scene_hint": "smiling characters in soft fantasy world",
    },
}


# =============================================================================
# POSTER GENERATOR SERVICE
# =============================================================================


class PosterGenerator:
    """Generate collection posters using OpenAI gpt-image-1.5 and GPT-5.1."""

    def __init__(
        self,
        api_key: str,
        output_dir: Path,
        cache_dir: Optional[Path] = None,
        templates_dir: Optional[Path] = None,
        poster_history_limit: int = 5,
        prompt_history_limit: int = 10,
    ):
        """
        Initialize poster generator.

        Args:
            api_key: OpenAI API key
            output_dir: Directory to save generated posters (data/posters)
            cache_dir: Directory for cache files (data/cache)
            templates_dir: Directory for custom templates (config/templates)
            poster_history_limit: Number of old posters to keep (0=unlimited)
            prompt_history_limit: Number of prompt JSON files to keep (0=unlimited)
        """
        self.client = AsyncOpenAI(api_key=api_key, timeout=API_TIMEOUT)
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Retention limits
        self.poster_history_limit = poster_history_limit
        self.prompt_history_limit = prompt_history_limit

        # Cache directory (separate from output)
        self.cache_dir = cache_dir or output_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Templates directory for external customization
        self.templates_dir = templates_dir

        # Load external templates and configurations
        self._load_external_templates()

        # Load cached visual signatures
        self.signatures_cache_path = self.cache_dir / "visual_signatures_cache.json"
        self.signatures_cache = self._load_signatures_cache()

        logger.info(f"PosterGenerator initialized (output: {output_dir})")
        if templates_dir and templates_dir.exists():
            logger.info(f"Custom templates loaded from: {templates_dir}")
        logger.info(f"Retention: {poster_history_limit} posters, {prompt_history_limit} prompts")
        logger.debug(f"Loaded {len(self.signatures_cache)} cached visual signatures")
        if self.signatures_cache:
            logger.debug(f"Cache keys sample: {list(self.signatures_cache.keys())[:5]}")

    def _load_external_templates(self) -> None:
        """Load external Jinja2 templates and YAML configurations."""
        # Initialize Jinja2 environment
        if self.templates_dir and self.templates_dir.exists():
            # Use FileSystemLoader for external templates with fallback to strings
            self.jinja_env = Environment(
                loader=FileSystemLoader(str(self.templates_dir)),
                autoescape=False
            )
            logger.debug(f"Jinja2 environment using templates from: {self.templates_dir}")
        else:
            # Use default string-based templates
            self.jinja_env = Environment(loader=BaseLoader(), autoescape=False)
            logger.debug("Jinja2 environment using embedded default templates")

        # Load YAML configurations with fallback to defaults
        self.category_styles = self._load_yaml_config(
            "category_styles.yaml", DEFAULT_CATEGORY_STYLES
        )
        self.collection_themes = self._load_yaml_config(
            "collection_themes.yaml", DEFAULT_COLLECTION_THEMES
        )
        # Note: visual_signatures_db is no longer used - signatures are generated
        # by GPT and cached in visual_signatures_cache.json

    def _load_yaml_config(self, filename: str, default: dict) -> dict:
        """Load a YAML configuration file with fallback to default."""
        if self.templates_dir:
            config_path = self.templates_dir / filename
            if config_path.exists():
                try:
                    with open(config_path, encoding="utf-8") as f:
                        loaded = yaml.safe_load(f)
                        if loaded:
                            logger.debug(f"Loaded external config: {filename}")
                            return loaded
                except Exception as e:
                    logger.warning(f"Failed to load {filename}: {e}, using defaults")
        return default

    def _get_template(self, name: str, default: str) -> str:
        """Get template content from file or return default."""
        if self.templates_dir:
            template_path = self.templates_dir / name
            if template_path.exists():
                try:
                    with open(template_path, encoding="utf-8") as f:
                        content = f.read()
                        logger.debug(f"Loaded external template: {name}")
                        return content
                except Exception as e:
                    logger.warning(f"Failed to load template {name}: {e}")
        return default

    def _load_signatures_cache(self) -> dict[str, str]:
        """Load cached visual signatures from JSON file."""
        if self.signatures_cache_path.exists():
            try:
                with open(self.signatures_cache_path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load signatures cache: {e}")
        return {}

    def _save_signatures_cache(self) -> None:
        """Save visual signatures cache to JSON file."""
        try:
            with open(self.signatures_cache_path, "w", encoding="utf-8") as f:
                json.dump(self.signatures_cache, f, indent=2, ensure_ascii=False)
            logger.debug(f"Saved {len(self.signatures_cache)} signatures to cache")
        except Exception as e:
            logger.warning(f"Failed to save signatures cache: {e}")

    def _get_collection_dir(self, library: str, collection: str) -> Path:
        """
        Get/create directory for a collection's posters.

        Structure: {output_dir}/{library}/{collection}/
            - poster.png (current poster)
            - history/ (timestamped old posters)
            - prompts/ (timestamped JSON files)
        """
        safe_lib = self._safe_filename(library)
        safe_col = self._safe_filename(collection)
        col_dir = self.output_dir / safe_lib / safe_col
        col_dir.mkdir(parents=True, exist_ok=True)
        (col_dir / "history").mkdir(exist_ok=True)
        (col_dir / "prompts").mkdir(exist_ok=True)
        return col_dir

    def _cleanup_history(self, col_dir: Path) -> None:
        """
        Apply retention limits to history and prompts.

        Keeps only the N most recent files based on configured limits.
        """
        # Cleanup poster history
        if self.poster_history_limit > 0:
            history_dir = col_dir / "history"
            files = sorted(history_dir.glob("*.png"))
            for f in files[:-self.poster_history_limit]:
                try:
                    f.unlink()
                    logger.debug(f"Deleted old poster: {f.name}")
                except Exception as e:
                    logger.warning(f"Failed to delete {f}: {e}")

        # Cleanup prompt history
        if self.prompt_history_limit > 0:
            prompts_dir = col_dir / "prompts"
            files = sorted(prompts_dir.glob("*.json"))
            for f in files[:-self.prompt_history_limit]:
                try:
                    f.unlink()
                    logger.debug(f"Deleted old prompt: {f.name}")
                except Exception as e:
                    logger.warning(f"Failed to delete {f}: {e}")

    async def generate_poster(
        self,
        config: CollectionConfig,
        items: list[MediaItem],
        category: str,  # "FILMS", "SÉRIES", or "CARTOONS"
        library: str = "default",
        force_regenerate: bool = False,
        use_dalle3: bool = False,
        explicit_refs: bool = False,
    ) -> Optional[Path]:
        """
        Generate a poster for a collection.

        Args:
            config: Collection configuration
            items: Items in the collection (for context)
            category: Category type (FILMS, SÉRIES, CARTOONS)
            library: Library name for folder organization
            force_regenerate: Regenerate even if poster exists
            use_dalle3: Use DALL-E 3 instead of gpt-image-1.5
            explicit_refs: Include show titles in visual signatures

        Returns:
            Path to generated poster, or None if failed
        """
        # Get collection directory (creates structure if needed)
        col_dir = self._get_collection_dir(library, config.name)
        output_path = col_dir / "poster.png"
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")

        # Skip if exists and not forcing
        if output_path.exists() and not force_regenerate:
            logger.debug(f"Poster already exists: {output_path}")
            return output_path

        logger.info(f"Generating poster for '{config.name}' in '{library}'...")
        start_time = time.perf_counter()

        try:
            # Step 1: Extract visual signatures (DB -> cache -> generate from metadata)
            visual_signatures = await self._extract_visual_signatures(
                items[:5], explicit_refs=explicit_refs
            )
            logger.debug(f"Visual signatures: {visual_signatures[:100]}...")

            # Step 2: Generate scene description using GPT-5.1
            scene_prompt = self._build_scene_prompt(config, category, visual_signatures)
            scene_description = await self._generate_scene_description(
                scene_prompt, visual_signatures
            )
            logger.debug(f"Scene description: {scene_description[:200]}...")

            # Step 3: Build the full prompt
            full_prompt = self._build_prompt(config, category, scene_description)
            logger.debug(f"Full prompt length: {len(full_prompt)} chars")

            # Step 4: Move existing poster to history (if exists)
            if output_path.exists():
                history_poster = col_dir / "history" / f"{timestamp}.png"
                import shutil
                shutil.move(str(output_path), str(history_poster))
                logger.debug(f"Moved old poster to history: {timestamp}.png")

            # Step 5: Generate image
            image_path = await self._generate_image(full_prompt, output_path, use_dalle3)

            elapsed = time.perf_counter() - start_time

            if image_path:
                # Step 6: Save prompt to collection's prompts folder
                self._save_prompt_to_collection(
                    col_dir=col_dir,
                    timestamp=timestamp,
                    config=config,
                    category=category,
                    library=library,
                    items=items,
                    visual_signatures=visual_signatures,
                    scene_prompt=scene_prompt,
                    scene_description=scene_description,
                    image_prompt=full_prompt,
                )

                # Step 7: Apply retention limits
                self._cleanup_history(col_dir)

                logger.success(
                    f"Generated poster: {library}/{config.name}/poster.png ({elapsed:.1f}s)"
                )
                return image_path

        except Exception as e:
            logger.error(f"Failed to generate poster for '{config.name}': {e}")

        return None

    def _build_scene_prompt(
        self,
        config: CollectionConfig,
        category: str,
        visual_signatures: str,
    ) -> str:
        """Build the scene description prompt with visual signatures."""
        # Get theme hints
        theme = self._get_collection_theme(config.name)
        style = self.category_styles.get(category, self.category_styles.get("FILMS", {}))

        # Override mood and colors for CARTOONS
        if category == "CARTOONS":
            mood_hint = "joyful, magical, whimsical, family-friendly, colorful adventure"
            color_hint = style.get("color_override", "bright rainbow colors + golden sunshine")
            # Add special instructions for cartoons
            extra_rules = """
IMPORTANT FOR CARTOONS:
- Scene must be BRIGHT, SUNNY, and CHEERFUL
- Use VIBRANT saturated colors (no dark or scary elements)
- Characters should look CUTE and FRIENDLY (big eyes, round shapes)
- Include magical sparkles, rainbows, or whimsical elements
- Think Pixar/Disney style: warm, inviting, family-friendly"""
        else:
            mood_hint = theme.get("mood_hint", "dramatic and engaging")
            color_hint = theme.get("color_hint", "cinematic colors")
            extra_rules = ""

        # Get template (external file or default)
        template_content = self._get_template(
            "scene_description.j2", DEFAULT_SCENE_PROMPT_TEMPLATE
        )
        template = self.jinja_env.from_string(template_content)
        base_prompt = template.render(
            collection_name=config.name,
            category=category,
            mood_hint=mood_hint,
            color_hint=color_hint,
            visual_signatures=visual_signatures,
        )

        return base_prompt + extra_rules

    async def _extract_visual_signatures(
        self, items: list[MediaItem], explicit_refs: bool = False
    ) -> str:
        """
        Extract visual signatures from media items.

        Priority:
        1. Local database (known franchises)
        2. Cached signatures (previously generated)
        3. Generate from metadata using GPT (then cache)

        Args:
            items: List of media items to extract signatures from
            explicit_refs: Include show titles for better context
        """
        if not items:
            return "Dynamic action scenes with dramatic lighting"

        # Collect signatures with their source titles
        signature_data: list[tuple[str, str]] = []  # (title, signature)
        items_needing_generation = []

        for item in items[:5]:
            signature = None

            # Check cache (signatures generated by GPT and cached)
            logger.debug(f"[Cache lookup] title='{item.title}', in_cache={item.title in self.signatures_cache}")
            if item.title in self.signatures_cache:
                signature = self.signatures_cache[item.title]
                logger.debug(f"[Cache] Found signature for '{item.title}'")

            if signature:
                signature_data.append((item.title, signature))
            else:
                # Need to generate from metadata
                items_needing_generation.append(item)

        # 3. Generate missing signatures from metadata
        if items_needing_generation:
            new_signatures = await self._generate_signatures_from_metadata(
                items_needing_generation
            )
            for item, sig in zip(items_needing_generation, new_signatures):
                signature_data.append((item.title, sig))

        if signature_data:
            logger.debug(f"Total {len(signature_data)} visual signatures")

            # Format based on explicit_refs setting
            if explicit_refs:
                # Structured format with show titles
                lines = []
                for i, (title, sig) in enumerate(signature_data[:3], 1):
                    lines.append(f'{i}. FROM "{title}":')
                    lines.append(f"   {sig}")
                return "\n".join(lines)
            else:
                # Original format (anonymous)
                return "\n".join(f"- {sig}" for _, sig in signature_data[:3])

        # Fallback
        logger.debug("No visual signatures found, using default")
        return "Epic cinematic environments with dramatic silhouettes, mixed genre visual styles"

    async def _generate_signatures_from_metadata(
        self, items: list[MediaItem]
    ) -> list[str]:
        """
        Generate visual signatures from item metadata using GPT.

        Uses genres and overview (not title) to avoid copyright issues.
        """
        signatures = []

        for item in items:
            # Build metadata context (no title!)
            # Convert genre IDs to names if needed
            genre_names = []
            for g in item.genres or []:
                if isinstance(g, int):
                    genre_names.append(TMDB_GENRES.get(g, "Drama"))
                else:
                    genre_names.append(str(g))
            genres = ", ".join(genre_names) if genre_names else "Drama"
            overview = item.overview or "A compelling story"

            # Truncate overview to avoid token limits
            if len(overview) > 200:
                overview = overview[:200] + "..."

            # Get template (external file or default)
            template_content = self._get_template(
                "visual_signature.j2", DEFAULT_VISUAL_SIGNATURE_TEMPLATE
            )
            template = self.jinja_env.from_string(template_content)
            prompt = template.render(genres=genres, overview=overview)

            try:
                logger.debug(f"[GPT] Generating signature for '{item.title}' from metadata...")
                response = await self.client.chat.completions.create(
                    model=MODEL_GPT_5_1,
                    messages=[{"role": "user", "content": prompt}],
                    max_completion_tokens=150,
                    reasoning_effort="low",
                )

                content = response.choices[0].message.content
                if content:
                    signature = content.strip()
                    signatures.append(signature)
                    # Cache for future use
                    self.signatures_cache[item.title] = signature
                    logger.debug(f"[GPT] Generated and cached: '{signature[:50]}...'")

            except Exception as e:
                logger.warning(f"Failed to generate signature for '{item.title}': {e}")

        # Save cache after generating new signatures
        if signatures:
            self._save_signatures_cache()

        return signatures

    async def _generate_scene_description(
        self,
        prompt: str,
        visual_signatures: str,
    ) -> str:
        """Generate a scene description using GPT-5.1 and visual signatures."""
        logger.debug("Calling GPT-5.1 for scene description...")
        start_time = time.perf_counter()

        # CRITICAL: reasoning_effort MUST be "low" - "medium" causes GPT-5.1 to return empty content
        response = await self.client.chat.completions.create(
            model=MODEL_GPT_5_1,
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=500,
            reasoning_effort="low",
        )

        elapsed = time.perf_counter() - start_time
        logger.debug(f"GPT-5.1 response in {elapsed:.1f}s")

        message = response.choices[0].message
        content = message.content
        refusal = getattr(message, "refusal", None)

        if refusal:
            logger.warning(f"GPT-5.1 refusal: {refusal}")
        if not content:
            logger.warning("GPT-5.1 returned empty content - using fallback")
            return "A dramatic cinematic scene with silhouetted figures walking toward a glowing horizon, mixing fantasy and sci-fi elements in a visually striking composition."

        logger.debug(f"GPT-5.1 scene: {content[:80]}...")
        return content.strip()

    def _save_prompt_to_collection(
        self,
        col_dir: Path,
        timestamp: str,
        config: CollectionConfig,
        category: str,
        library: str,
        items: list[MediaItem],
        visual_signatures: str,
        scene_prompt: str,
        scene_description: str,
        image_prompt: str,
    ) -> None:
        """
        Save prompt data to the collection's prompts folder.

        Args:
            col_dir: Collection directory path
            timestamp: Timestamp for the filename
            config: Collection configuration
            category: Category type
            library: Library name
            items: Media items used for context
            visual_signatures: Visual signatures extracted from titles
            scene_prompt: Prompt sent to GPT-5.1
            scene_description: Response from GPT-5.1
            image_prompt: Final prompt sent to gpt-image-1.5
        """
        prompt_file = col_dir / "prompts" / f"{timestamp}.json"

        prompt_data = {
            "timestamp": datetime.now().isoformat(),
            "library": library,
            "collection": {
                "name": config.name,
                "summary": config.summary,
            },
            "category": category,
            "items_context": [
                {"title": item.title, "year": item.year}
                for item in items[:10]
            ],
            "prompts": {
                "visual_signatures": visual_signatures,
                "scene_prompt": scene_prompt,
                "scene_description": scene_description,
                "image_prompt": image_prompt,
            },
            "models": {
                "scene_model": MODEL_GPT_5_1,
                "image_model": MODEL_GPT_IMAGE_1_5,
            },
        }

        try:
            with open(prompt_file, "w", encoding="utf-8") as f:
                json.dump(prompt_data, f, indent=2, ensure_ascii=False)
            logger.debug(f"Prompt saved to: {col_dir.name}/prompts/{timestamp}.json")
        except Exception as e:
            logger.warning(f"Failed to save prompt: {e}")

    def _build_prompt(
        self,
        config: CollectionConfig,
        category: str,
        scene_description: str,
    ) -> str:
        """Build the full image generation prompt using Jinja2 template."""
        style = self.category_styles.get(category, self.category_styles.get("FILMS", {}))
        theme = self._get_collection_theme(config.name)

        # Use color override for specific categories (e.g., CARTOONS)
        color_palette = style.get("color_override", theme.get("color_hint", "cinematic blues + warm highlights"))

        # For CARTOONS, add extra child-friendly instructions
        scene_prefix = f"Single {style.get('scene_context', 'cinematic scene')}"
        if category == "CARTOONS":
            scene_prefix = "Bright, colorful, family-friendly animated scene"

        # Get template (external file or default)
        template_content = self._get_template(
            "base_structure.j2", DEFAULT_BASE_STRUCTURE_TEMPLATE
        )
        template = self.jinja_env.from_string(template_content)
        return template.render(
            poster_style=style.get("poster_style", "Cinematic"),
            category=category,
            collection_display_name=config.name,
            scene_description=f"{scene_prefix}: {scene_description}",
            color_palette=color_palette,
            mood_style=style.get("base_mood", "Dramatic and engaging"),
            lighting_style=style.get("lighting_style", "Dramatic cinematic lighting"),
        )

    async def _generate_image(
        self,
        prompt: str,
        output_path: Path,
        use_dalle3: bool = False,
    ) -> Optional[Path]:
        """
        Generate image using gpt-image-1.5 or DALL-E 3.

        Args:
            prompt: The image generation prompt
            output_path: Path to save the generated image
            use_dalle3: If True, use DALL-E 3 instead of gpt-image-1.5
        """
        model = MODEL_DALL_E_3 if use_dalle3 else MODEL_GPT_IMAGE_1_5
        logger.debug(f"Calling {model} for image generation...")
        start_time = time.perf_counter()

        try:
            if use_dalle3:
                # DALL-E 3 parameters (different API)
                response = await self.client.images.generate(
                    model=MODEL_DALL_E_3,
                    prompt=prompt,
                    n=1,
                    size="1024x1792",  # Vertical format for DALL-E 3
                    quality="hd",  # HD quality
                    style="vivid",  # More vivid/dramatic style
                    response_format="b64_json",
                )
            else:
                # gpt-image-1.5 parameters
                response = await self.client.images.generate(
                    model=MODEL_GPT_IMAGE_1_5,
                    prompt=prompt,
                    n=1,
                    size="1024x1536",  # Vertical 2:3 ratio for posters
                    quality="high",  # Maximum detail for photorealism
                    output_format="png",  # Lossless quality
                    background="opaque",  # Solid background for poster
                )

            elapsed = time.perf_counter() - start_time
            logger.debug(f"{model} response in {elapsed:.1f}s")

            # Decode and save image
            image_data = response.data[0].b64_json
            image_bytes = base64.b64decode(image_data)

            with open(output_path, "wb") as f:
                f.write(image_bytes)

            return output_path

        except Exception as e:
            logger.error(f"Image generation failed ({model}): {e}")
            return None

    def _get_collection_theme(self, collection_name: str) -> dict[str, str]:
        """Get theme hints based on collection name."""
        name_lower = collection_name.lower()

        for key, theme in self.collection_themes.items():
            if key in name_lower:
                return theme

        # Default theme
        return {
            "color_hint": "deep blues + warm highlights",
            "mood_hint": "cinematic and engaging",
            "scene_hint": "dramatic cinematic composition",
        }

    def _safe_filename(self, name: str) -> str:
        """Convert collection name to safe filename."""
        # Remove emojis and special chars
        safe = "".join(c for c in name if c.isalnum() or c in " _-")
        return safe.strip().replace(" ", "_").lower()


# =============================================================================
# CLI FUNCTION FOR TESTING
# =============================================================================


async def generate_test_poster(
    collection_name: str,
    category: str,
    api_key: str,
    output_dir: Path,
    library: str = "test",
) -> Optional[Path]:
    """
    Generate a test poster for quick validation.

    Args:
        collection_name: Name of the collection (e.g., "🔥 Tendances")
        category: Category (FILMS, SÉRIES, CARTOONS)
        api_key: OpenAI API key
        output_dir: Output directory
        library: Library name for folder organization

    Returns:
        Path to generated poster
    """
    from jfc.models.collection import CollectionConfig

    config = CollectionConfig(
        name=collection_name,
        summary=f"Test collection for {collection_name}",
    )

    generator = PosterGenerator(api_key, output_dir)
    return await generator.generate_poster(
        config=config,
        items=[],  # No items for test
        category=category,
        library=library,
        force_regenerate=True,
    )
