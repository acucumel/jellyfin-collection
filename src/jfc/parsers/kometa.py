"""Parser for Kometa (Plex Meta Manager) YAML configuration files."""

from datetime import date
from pathlib import Path
from typing import Any, Optional

import yaml
from loguru import logger

from jfc.models.collection import (
    CollectionConfig,
    CollectionFilter,
    CollectionOrder,
    CollectionSchedule,
    CollectionTemplate,
    SyncMode,
)


class KometaParser:
    """Parser for Kometa YAML configuration files."""

    def __init__(self, config_path: Path):
        """
        Initialize parser.

        Args:
            config_path: Path to config directory or main config file
        """
        self.config_path = config_path
        self._templates: dict[str, CollectionTemplate] = {}

    def parse_config(self, file_path: Optional[Path] = None) -> dict[str, Any]:
        """
        Parse main config.yml file.

        Args:
            file_path: Path to config file (uses config_path/config.yml if None)

        Returns:
            Parsed configuration dictionary
        """
        path = file_path or self.config_path / "config.yml"

        if not path.exists():
            logger.warning(f"Config file not found: {path}")
            return {}

        with open(path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        logger.info(f"Parsed config from {path}")
        return config or {}

    def parse_library_config(self, library_config: dict[str, Any]) -> dict[str, Any]:
        """
        Parse library configuration from main config.

        Args:
            library_config: Library section from config.yml

        Returns:
            Parsed library configuration
        """
        result = {
            "collection_files": [],
            "operations": library_config.get("operations", {}),
            "radarr": library_config.get("radarr"),
            "sonarr": library_config.get("sonarr"),
        }

        # Parse collection files
        for cf in library_config.get("collection_files", []):
            if isinstance(cf, dict) and "file" in cf:
                result["collection_files"].append(cf["file"])
            elif isinstance(cf, str):
                result["collection_files"].append(cf)

        return result

    def parse_collection_file(self, file_path: Path) -> list[CollectionConfig]:
        """
        Parse a collection YAML file (e.g., Films.yml, Series.yml).

        Args:
            file_path: Path to collection file

        Returns:
            List of parsed collection configurations
        """
        if not file_path.exists():
            logger.warning(f"Collection file not found: {file_path}")
            return []

        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data:
            return []

        # Parse templates first
        self._parse_templates(data.get("templates", {}))

        # Parse collections
        collections = []
        for name, config in data.get("collections", {}).items():
            try:
                collection = self._parse_collection(name, config)
                collections.append(collection)
            except Exception as e:
                logger.error(f"Failed to parse collection '{name}': {e}")

        logger.info(f"Parsed {len(collections)} collections from {file_path}")
        return collections

    def _parse_templates(self, templates: dict[str, Any]) -> None:
        """Parse template definitions."""
        for name, config in templates.items():
            self._templates[name] = CollectionTemplate(
                name=name,
                sync_mode=SyncMode(config.get("sync_mode", "sync")),
                visible_library=config.get("visible_library", True),
                visible_home=config.get("visible_home", False),
                visible_shared=config.get("visible_shared", False),
                filters=self._parse_filters(config.get("filters", {})),
                schedule=CollectionSchedule.from_kometa(config.get("schedule")),
            )

    def _parse_collection(self, name: str, config: dict[str, Any]) -> CollectionConfig:
        """Parse a single collection configuration."""
        # Apply template defaults if specified
        template_config = config.get("template", {})
        template_name = template_config.get("name") if isinstance(template_config, dict) else None
        template = self._templates.get(template_name) if template_name else None

        # Start with template defaults
        base_filters = template.filters if template else CollectionFilter()
        base_schedule = template.schedule if template else CollectionSchedule()

        # Override with collection-specific values
        filters = self._parse_filters(config.get("filters", {}), base_filters)
        schedule = CollectionSchedule.from_kometa(config.get("schedule")) or base_schedule

        # Parse tmdb_discover if present
        tmdb_discover = None
        if "tmdb_discover" in config:
            tmdb_discover = self._normalize_tmdb_discover(config["tmdb_discover"])

        # Parse trakt_chart if present
        trakt_chart = None
        if "trakt_chart" in config:
            trakt_chart = config["trakt_chart"]

        # Parse plex_search (will work with Jellyfin)
        plex_search = config.get("plex_search")

        # Parse collection_order
        collection_order = self._parse_collection_order(config.get("collection_order"))

        return CollectionConfig(
            name=name,
            summary=config.get("summary"),
            sort_title=config.get("sort_title"),
            poster=config.get("poster"),
            collection_order=collection_order,
            visible_library=config.get("visible_library", template.visible_library if template else True),
            visible_home=config.get("visible_home", template.visible_home if template else False),
            visible_shared=config.get("visible_shared", template.visible_shared if template else False),
            sync_mode=SyncMode(config.get("sync_mode", template.sync_mode.value if template else "sync")),
            minimum_items=config.get("minimum_items", 1),
            delete_not_scheduled=config.get("delete_not_scheduled", False),
            schedule=schedule,
            filters=filters,
            # Builder sources
            tmdb_trending_weekly=config.get("tmdb_trending_weekly"),
            tmdb_trending_daily=config.get("tmdb_trending_daily"),
            tmdb_popular=config.get("tmdb_popular"),
            tmdb_discover=tmdb_discover,
            trakt_trending=config.get("trakt_trending"),
            trakt_popular=config.get("trakt_popular"),
            trakt_chart=trakt_chart,
            trakt_list=config.get("trakt_list"),
            mdblist_list=config.get("mdblist_list"),
            imdb_list=config.get("imdb_list"),
            plex_search=plex_search,
            # Tags
            item_radarr_tag=config.get("item_radarr_tag"),
            item_sonarr_tag=config.get("item_sonarr_tag"),
            # Limit
            limit=tmdb_discover.get("limit") if tmdb_discover else config.get("limit"),
            # Template reference
            template=template_name,
        )

    def _parse_filters(
        self,
        filters: dict[str, Any],
        base: Optional[CollectionFilter] = None,
    ) -> CollectionFilter:
        """Parse filter configuration."""
        if base:
            # Start with base filter values
            result = base.model_copy()
        else:
            result = CollectionFilter()

        # Year filters
        if "year.gte" in filters:
            result.year_gte = filters["year.gte"]
        if "year.lte" in filters:
            result.year_lte = filters["year.lte"]

        # Rating filters
        if "vote_average.gte" in filters:
            result.vote_average_gte = filters["vote_average.gte"]
        if "critic_rating.gte" in filters:
            result.critic_rating_gte = filters["critic_rating.gte"]

        # Vote count filters
        if "tmdb_vote_count.gte" in filters:
            result.tmdb_vote_count_gte = filters["tmdb_vote_count.gte"]

        # Country filters
        if "country.not" in filters:
            result.country_not = filters["country.not"]
        if "origin_country.not" in filters:
            result.origin_country_not = filters["origin_country.not"]

        # Language filter (e.g., exclude Japanese: ["ja"])
        if "original_language.not" in filters:
            lang = filters["original_language.not"]
            if isinstance(lang, str):
                result.original_language_not = [lang]
            else:
                result.original_language_not = lang

        # Genre filters (for post-filtering, TMDb discover handles these separately)
        if "without_genres" in filters:
            genres = filters["without_genres"]
            if isinstance(genres, int):
                result.without_genres = [genres]
            elif isinstance(genres, str):
                result.without_genres = [int(g) for g in genres.split(",")]
            else:
                result.without_genres = genres

        if "with_genres" in filters:
            genres = filters["with_genres"]
            if isinstance(genres, int):
                result.with_genres = [genres]
            elif isinstance(genres, str):
                result.with_genres = [int(g) for g in genres.split(",")]
            else:
                result.with_genres = genres

        return result

    def _parse_collection_order(self, value: str | None) -> CollectionOrder:
        """Parse collection_order value to enum."""
        if not value:
            return CollectionOrder.CUSTOM

        value_lower = value.lower().strip()

        # Map common names to enum values
        order_mapping = {
            # Custom (keep source order)
            "custom": CollectionOrder.CUSTOM,
            # Alphabetical
            "alpha": CollectionOrder.SORT_NAME,
            "alphabetical": CollectionOrder.SORT_NAME,
            "sortname": CollectionOrder.SORT_NAME,
            "name": CollectionOrder.SORT_NAME,
            # Release date
            "release": CollectionOrder.PREMIERE_DATE,
            "premieredate": CollectionOrder.PREMIERE_DATE,
            "release_date": CollectionOrder.PREMIERE_DATE,
            "date": CollectionOrder.PREMIERE_DATE,
            # Date added
            "added": CollectionOrder.DATE_CREATED,
            "datecreated": CollectionOrder.DATE_CREATED,
            "date_added": CollectionOrder.DATE_CREATED,
            # Community rating
            "rating": CollectionOrder.COMMUNITY_RATING,
            "communityrating": CollectionOrder.COMMUNITY_RATING,
            "audience_rating": CollectionOrder.COMMUNITY_RATING,
            # Critic rating
            "critic": CollectionOrder.CRITIC_RATING,
            "criticrating": CollectionOrder.CRITIC_RATING,
            "critic_rating": CollectionOrder.CRITIC_RATING,
            # Random
            "random": CollectionOrder.RANDOM,
        }

        if value_lower in order_mapping:
            return order_mapping[value_lower]

        logger.warning(f"Unknown collection_order '{value}', defaulting to 'custom'")
        return CollectionOrder.CUSTOM

    def _normalize_tmdb_discover(self, discover: dict[str, Any]) -> dict[str, Any]:
        """Normalize TMDb discover parameters."""
        result = {}

        # Direct mappings
        direct_fields = [
            "sort_by",
            "vote_average.gte",
            "vote_average.lte",
            "vote_count.gte",
            "vote_count.lte",
            "watch_region",
            "with_watch_monetization_types",
            "with_original_language",
            "with_release_type",
            "region",
            "limit",
            "with_status",
        ]

        for field in direct_fields:
            if field in discover:
                result[field] = discover[field]

        # Handle genres (can be comma-separated or list)
        if "with_genres" in discover:
            genres = discover["with_genres"]
            if isinstance(genres, str):
                result["with_genres"] = [int(g) for g in genres.split(",")]
            elif isinstance(genres, int):
                result["with_genres"] = [genres]
            else:
                result["with_genres"] = genres

        if "without_genres" in discover:
            genres = discover["without_genres"]
            if isinstance(genres, int):
                result["without_genres"] = [genres]
            else:
                result["without_genres"] = genres

        # Handle watch providers (pipe-separated in Kometa)
        if "with_watch_providers" in discover:
            providers = discover["with_watch_providers"]
            if isinstance(providers, str):
                result["with_watch_providers"] = [int(p) for p in providers.split("|")]
            elif isinstance(providers, int):
                result["with_watch_providers"] = [providers]
            else:
                result["with_watch_providers"] = providers

        # Handle dates
        date_fields = [
            "primary_release_date.gte",
            "primary_release_date.lte",
            "first_air_date.gte",
            "first_air_date.lte",
        ]

        for field in date_fields:
            if field in discover:
                value = discover[field]
                if isinstance(value, str):
                    try:
                        result[field] = date.fromisoformat(value)
                    except ValueError:
                        logger.warning(f"Invalid date format for {field}: {value}")
                elif isinstance(value, date):
                    result[field] = value

        return result

    def get_all_collections(self) -> dict[str, list[CollectionConfig]]:
        """
        Parse all collections from config.

        Returns:
            Dictionary mapping library names to their collections
        """
        config = self.parse_config()
        result = {}

        for library_name, library_config in config.get("libraries", {}).items():
            parsed = self.parse_library_config(library_config)
            collections = []

            for cf_path in parsed["collection_files"]:
                # Handle relative paths
                if cf_path.startswith("config/"):
                    cf_path = cf_path.replace("config/", "")

                full_path = self.config_path / cf_path
                collections.extend(self.parse_collection_file(full_path))

            # Apply library-level Sonarr/Radarr settings to each collection
            sonarr_config = parsed.get("sonarr") or {}
            radarr_config = parsed.get("radarr") or {}

            for collection in collections:
                # Sonarr overrides
                if sonarr_config.get("root_folder_path"):
                    collection.sonarr_root_folder = sonarr_config["root_folder_path"]
                if sonarr_config.get("tag"):
                    collection.sonarr_tag = sonarr_config["tag"]
                if sonarr_config.get("quality_profile"):
                    collection.sonarr_quality_profile = sonarr_config["quality_profile"]

                # Radarr overrides
                if radarr_config.get("root_folder_path"):
                    collection.radarr_root_folder = radarr_config["root_folder_path"]
                if radarr_config.get("tag"):
                    collection.radarr_tag = radarr_config["tag"]
                if radarr_config.get("quality_profile"):
                    collection.radarr_quality_profile = radarr_config["quality_profile"]

            result[library_name] = collections
            logger.info(f"Library '{library_name}': {len(collections)} collections")

        return result
