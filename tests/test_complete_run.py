#!/usr/bin/env python
"""Test a complete poster generation run with all categories."""

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

    # Initialize clients - single run_id for all posters
    tmdb = TMDbClient(api_key=tmdb_key, language="fr", region="FR")
    poster_gen = PosterGenerator(api_key=openai_key, output_dir=Path("config/posters"))

    print(f"\n{'='*60}")
    print(f"COMPLETE RUN - {poster_gen.run_id}")
    print(f"{'='*60}\n")

    results = []

    try:
        # =====================================================================
        # 1. FILMS - Trending Movies
        # =====================================================================
        print("\n[1/3] FILMS - Tendances Films")
        print("-" * 40)

        movies = await tmdb.get_trending_movies("week", limit=20)
        print(f"Fetched {len(movies)} trending movies")
        for i, item in enumerate(movies[:5], 1):
            print(f"  {i}. {item.title} ({item.year})")

        config_films = CollectionConfig(
            name="🔥 Tendances",
            summary="Les films les plus populaires du moment",
        )

        result = await poster_gen.generate_poster(
            config=config_films,
            items=movies,
            category="FILMS",
            force_regenerate=True,
        )
        results.append(("FILMS", "🔥 Tendances", result))

        # =====================================================================
        # 2. SÉRIES - Trending Series
        # =====================================================================
        print("\n[2/3] SÉRIES - Séries du Moment")
        print("-" * 40)

        series = await tmdb.get_trending_series("week", limit=20)
        print(f"Fetched {len(series)} trending series")
        for i, item in enumerate(series[:5], 1):
            print(f"  {i}. {item.title} ({item.year})")

        config_series = CollectionConfig(
            name="📺 Séries du Moment",
            summary="Les séries les plus populaires cette semaine",
        )

        result = await poster_gen.generate_poster(
            config=config_series,
            items=series,
            category="SÉRIES",
            force_regenerate=True,
        )
        results.append(("SÉRIES", "📺 Séries du Moment", result))

        # =====================================================================
        # 3. CARTOONS - Animated Movies
        # =====================================================================
        print("\n[3/3] CARTOONS - Dessins Animés")
        print("-" * 40)

        cartoons = await tmdb.discover_movies(
            with_genres=[16],  # Animation
            sort_by="popularity.desc",
            limit=20,
        )
        print(f"Fetched {len(cartoons)} animated movies")
        for i, item in enumerate(cartoons[:5], 1):
            print(f"  {i}. {item.title} ({item.year})")

        config_cartoons = CollectionConfig(
            name="🎨 Dessins Animés",
            summary="Les meilleurs films d'animation pour toute la famille",
        )

        result = await poster_gen.generate_poster(
            config=config_cartoons,
            items=cartoons,
            category="CARTOONS",
            force_regenerate=True,
        )
        results.append(("CARTOONS", "🎨 Dessins Animés", result))

        # =====================================================================
        # Summary
        # =====================================================================
        print(f"\n{'='*60}")
        print("RESULTS")
        print(f"{'='*60}")

        for category, name, path in results:
            status = "✅" if path else "❌"
            print(f"{status} [{category}] {name}")
            if path:
                print(f"   → {path}")

        print(f"\n📁 History folder: config/posters/history/{poster_gen.run_id}/")

        # List history files
        history_files = list(poster_gen.history_dir.glob("*"))
        print(f"   Contains {len(history_files)} files:")
        for f in sorted(history_files):
            print(f"   - {f.name}")

    finally:
        await tmdb.close()


if __name__ == "__main__":
    asyncio.run(main())
