#!/usr/bin/env python
"""Test poster generation with TV series."""

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
        # Fetch trending series from TMDb
        print("Fetching trending series from TMDb...")
        items = await tmdb.get_trending_series("week", limit=20)
        print(f"Got {len(items)} items:")
        for i, item in enumerate(items[:10], 1):
            print(f"  {i}. {item.title} ({item.year})")

        # Create collection config
        config = CollectionConfig(
            name="📺 Séries du Moment",
            summary="Les séries les plus populaires cette semaine",
        )

        # Generate poster
        print("\nGenerating poster for SÉRIES...")
        result = await poster_gen.generate_poster(
            config=config,
            items=items,
            category="SÉRIES",
            force_regenerate=True,
        )

        if result:
            print(f"\nPoster generated: {result}")
        else:
            print("\nFailed to generate poster")

    finally:
        await tmdb.close()


if __name__ == "__main__":
    asyncio.run(main())
