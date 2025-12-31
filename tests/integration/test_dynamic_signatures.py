#!/usr/bin/env python
"""Test dynamic signature generation with unknown movies."""

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

async def main():
    from jfc.clients.tmdb import TMDbClient
    from jfc.models.collection import CollectionConfig
    from jfc.services.poster_generator import PosterGenerator

    # Get API keys
    tmdb_key = os.getenv("TMDB_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")

    if not tmdb_key or not openai_key:
        print("Missing TMDB_API_KEY or OPENAI_API_KEY")
        return

    # Initialize clients
    tmdb = TMDbClient(api_key=tmdb_key, language="fr", region="FR")
    poster_gen = PosterGenerator(api_key=openai_key, output_dir=Path("config/posters"))

    try:
        # Fetch less popular movies (less likely to be in the DB)
        print("Fetching less popular movies (less likely to be in DB)...")
        items = await tmdb.discover_movies(
            sort_by="vote_count.asc",  # Less popular first
            vote_count_gte=10,  # At least some votes
            vote_average_gte=5.0,  # Decent quality
            limit=20,
        )

        # Filter out known franchises
        known_keywords = ["avatar", "wicked", "zootop", "freddy", "anaconda", "tron", "xxx",
                         "couteau", "éternité", "eternit", "insaisissable", "éponge"]
        unknown_items = [
            item for item in items
            if not any(kw in item.title.lower() for kw in known_keywords)
        ][:5]

        print(f"Got {len(unknown_items)} unknown items:")
        for i, item in enumerate(unknown_items, 1):
            genres = item.genres[:3] if item.genres else []
            print(f"  {i}. {item.title}")
            print(f"     Genres: {genres}")
            print(f"     Overview: {item.overview[:80] if item.overview else 'N/A'}...")

        if not unknown_items:
            print("No unknown items found, using trending instead")
            return

        # Create collection config
        config = CollectionConfig(
            name="🎬 À Venir",
            summary="Les prochaines sorties au cinéma",
        )

        # Generate poster - this should trigger dynamic signature generation
        print("\nGenerating poster with dynamic signatures...")
        result = await poster_gen.generate_poster(
            config=config,
            items=unknown_items,
            category="FILMS",
            force_regenerate=True,
        )

        if result:
            print(f"\nPoster generated: {result}")

            # Check the cache
            cache_path = Path("config/posters/visual_signatures_cache.json")
            if cache_path.exists():
                import json
                with open(cache_path) as f:
                    cache = json.load(f)
                print(f"\nCached signatures ({len(cache)} items):")
                for title, sig in list(cache.items())[:3]:
                    print(f"  - {title}: {sig[:60]}...")
        else:
            print("\nFailed to generate poster")

    finally:
        await tmdb.close()


if __name__ == "__main__":
    asyncio.run(main())
