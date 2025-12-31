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
# CONSTANTS
# =============================================================================

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


# =============================================================================
# POSTER GENERATOR SERVICE
# =============================================================================


class PosterGenerator:
    """Generate collection posters using OpenAI gpt-image-1.5 and GPT-5.1."""

    # Package templates directory (fallback)
    PACKAGE_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

    def __init__(
        self,
        api_key: str,
        output_dir: Path,
        cache_dir: Optional[Path] = None,
        templates_dir: Optional[Path] = None,
        poster_history_limit: int = 5,
        prompt_history_limit: int = 10,
        logo_text: str = "NETFLEX",
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
            logo_text: Logo text for bottom of posters (default: NETFLEX)
        """
        self.client = AsyncOpenAI(api_key=api_key, timeout=API_TIMEOUT)
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Retention limits
        self.poster_history_limit = poster_history_limit
        self.prompt_history_limit = prompt_history_limit

        # Logo text for posters
        self.logo_text = logo_text

        # Cache directory (separate from output)
        self.cache_dir = cache_dir or output_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Templates directories: user overrides > package defaults
        self.templates_dir = templates_dir  # User overrides (config/templates)
        self.package_templates_dir = self.PACKAGE_TEMPLATES_DIR  # Package defaults

        # Load templates and configurations
        self._load_templates()

        # Load cached visual signatures
        self.signatures_cache_path = self.cache_dir / "visual_signatures_cache.json"
        self.signatures_cache = self._load_signatures_cache()

        logger.info(f"PosterGenerator initialized (output: {output_dir}, logo: {logo_text})")
        if templates_dir and templates_dir.exists():
            logger.info(f"Custom templates from: {templates_dir}")
        logger.info(f"Package templates from: {self.package_templates_dir}")
        logger.info(f"Retention: {poster_history_limit} posters, {prompt_history_limit} prompts")
        logger.debug(f"Loaded {len(self.signatures_cache)} cached visual signatures")
        if self.signatures_cache:
            logger.debug(f"Cache keys sample: {list(self.signatures_cache.keys())[:5]}")

    def _load_templates(self) -> None:
        """Load Jinja2 templates and YAML configurations.

        Priority: config/templates (user) > src/jfc/templates (package)
        """
        # Initialize Jinja2 environment with BaseLoader (we'll load manually)
        self.jinja_env = Environment(loader=BaseLoader(), autoescape=False)

        # Load YAML configurations (user override > package default)
        self.category_styles = self._load_yaml_config("category_styles.yaml")
        self.collection_themes = self._load_yaml_config("collection_themes.yaml")

    def _load_yaml_config(self, filename: str) -> dict:
        """Load a YAML configuration file.

        Priority: config/templates (user) > src/jfc/templates (package)
        """
        # 1. Try user override (config/templates)
        if self.templates_dir:
            user_path = self.templates_dir / filename
            if user_path.exists():
                try:
                    with open(user_path, encoding="utf-8") as f:
                        loaded = yaml.safe_load(f)
                        if loaded:
                            logger.debug(f"Loaded user config: {filename}")
                            return loaded
                except Exception as e:
                    logger.warning(f"Failed to load user {filename}: {e}")

        # 2. Fall back to package default (src/jfc/templates)
        package_path = self.package_templates_dir / filename
        if package_path.exists():
            try:
                with open(package_path, encoding="utf-8") as f:
                    loaded = yaml.safe_load(f)
                    if loaded:
                        logger.debug(f"Loaded package config: {filename}")
                        return loaded
            except Exception as e:
                logger.warning(f"Failed to load package {filename}: {e}")

        # 3. Return empty dict if nothing found
        logger.warning(f"No config found for {filename}")
        return {}

    def _get_template(self, name: str) -> str:
        """Get template content from file.

        Priority: config/templates (user) > src/jfc/templates (package)
        """
        # 1. Try user override (config/templates)
        if self.templates_dir:
            user_path = self.templates_dir / name
            if user_path.exists():
                try:
                    with open(user_path, encoding="utf-8") as f:
                        content = f.read()
                        logger.debug(f"Loaded user template: {name}")
                        return content
                except Exception as e:
                    logger.warning(f"Failed to load user template {name}: {e}")

        # 2. Fall back to package default (src/jfc/templates)
        package_path = self.package_templates_dir / name
        if package_path.exists():
            try:
                with open(package_path, encoding="utf-8") as f:
                    content = f.read()
                    logger.debug(f"Loaded package template: {name}")
                    return content
            except Exception as e:
                logger.warning(f"Failed to load package template {name}: {e}")

        # 3. Raise error if template not found
        raise FileNotFoundError(f"Template not found: {name}")

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

        # Clean collection name for display (remove "(Films)", emojis, etc.)
        display_name = self._clean_display_name(config.name)

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

        # Get template (user override > package default)
        template_content = self._get_template("scene_description.j2")
        template = self.jinja_env.from_string(template_content)
        base_prompt = template.render(
            collection_name=display_name,
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
        # Use top 8 items: 3 primary + 5 secondary references
        signature_data: list[tuple[str, str]] = []  # (title, signature)
        items_needing_generation = []

        for item in items[:8]:
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

            # Split into primary (top 3) and secondary references
            primary_refs = signature_data[:3]
            secondary_refs = signature_data[3:6]

            # Format based on explicit_refs setting
            if explicit_refs:
                # Structured format with show titles
                lines = ["PRIMARY VISUAL REFERENCES (dominant influence):"]
                for i, (title, sig) in enumerate(primary_refs, 1):
                    lines.append(f'  {i}. FROM "{title}":')
                    lines.append(f"     {sig}")

                if secondary_refs:
                    lines.append("")
                    lines.append("SECONDARY REFERENCES (subtle influence):")
                    for title, sig in secondary_refs:
                        lines.append(f'  - "{title}": {sig}')

                return "\n".join(lines)
            else:
                # Anonymous format with primary/secondary distinction
                lines = ["PRIMARY (dominant):"]
                for _, sig in primary_refs:
                    lines.append(f"  - {sig}")

                if secondary_refs:
                    lines.append("SECONDARY (subtle):")
                    for _, sig in secondary_refs:
                        lines.append(f"  - {sig}")

                return "\n".join(lines)

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

            # Get template (user override > package default)
            template_content = self._get_template("visual_signature.j2")
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

        # Clean collection name for display (remove "(Films)", emojis, etc.)
        display_name = self._clean_display_name(config.name)

        # Use color override for specific categories (e.g., CARTOONS)
        color_palette = style.get("color_override", theme.get("color_hint", "cinematic blues + warm highlights"))

        # For CARTOONS, add extra child-friendly instructions
        scene_prefix = f"Single {style.get('scene_context', 'cinematic scene')}"
        if category == "CARTOONS":
            scene_prefix = "Bright, colorful, family-friendly animated scene"

        # Get template (user override > package default)
        template_content = self._get_template("base_structure.j2")
        template = self.jinja_env.from_string(template_content)
        return template.render(
            poster_style=style.get("poster_style", "Cinematic"),
            category=category,
            collection_display_name=display_name,
            scene_description=f"{scene_prefix}: {scene_description}",
            color_palette=color_palette,
            mood_style=style.get("base_mood", "Dramatic and engaging"),
            lighting_style=style.get("lighting_style", "Dramatic cinematic lighting"),
            logo_text=self.logo_text,
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

    def _clean_display_name(self, name: str) -> str:
        """
        Clean collection name for display on poster.

        Removes:
        - Category suffixes: (Films), (Séries), (Cartoons), etc.

        Keeps:
        - Emojis (they add visual interest)

        Example: "🔥 Tendances (Films)" -> "🔥 Tendances"
        """
        import re

        # Remove category suffixes (case insensitive, with or without accents)
        suffixes_pattern = r'\s*\((Films?|Séries?|Series?|Cartoons?|TV|Shows?)\)\s*$'
        cleaned = re.sub(suffixes_pattern, '', name, flags=re.IGNORECASE)

        # Clean up whitespace
        cleaned = cleaned.strip()

        return cleaned if cleaned else name  # Fallback to original if empty


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
