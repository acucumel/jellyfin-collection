"""Command-line interface for Jellyfin Collection."""

import asyncio
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from jfc.core.config import get_settings
from jfc.core.logger import setup_logging
from jfc.core.scheduler import Scheduler

app = typer.Typer(
    name="jfc",
    help="Jellyfin Collection - Kometa-compatible collection manager",
    add_completion=False,
)

# Force UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

console = Console(force_terminal=True)


@app.command()
def run(
    libraries: Optional[list[str]] = typer.Option(
        None, "--library", "-l", help="Libraries to process (can be repeated)"
    ),
    collections: Optional[list[str]] = typer.Option(
        None, "--collection", "-c", help="Collections to process (can be repeated)"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", "-n", help="Simulate run without making changes"
    ),
    config_path: Optional[Path] = typer.Option(
        None, "--config", help="Path to Kometa config directory"
    ),
) -> None:
    """Run collection updates."""
    settings = get_settings()

    if dry_run:
        settings.dry_run = True
    if config_path:
        settings.config_path = config_path

    # Setup logging with file output
    log_dir = settings.config_path / "logs"
    setup_logging(level=settings.log_level, log_dir=log_dir)

    from jfc.services.runner import Runner

    async def _run():
        runner = Runner(settings)
        try:
            report = await runner.run(
                libraries=libraries,
                collections=collections,
                scheduled=False,
            )
            console.print(
                f"\n[green]Completed![/green] "
                f"{report.successful_collections}/{report.total_collections} collections, "
                f"+{report.total_items_added} -{report.total_items_removed} items"
            )
        finally:
            await runner.close()

    asyncio.run(_run())


@app.command()
def schedule(
    cron: Optional[str] = typer.Option(
        None, "--cron", help="Cron expression (e.g., '0 3 * * *')"
    ),
) -> None:
    """Run with scheduler for periodic updates."""
    settings = get_settings()
    log_dir = settings.config_path / "logs"
    setup_logging(level=settings.log_level, log_dir=log_dir)

    cron_expr = cron or settings.scheduler.cron

    from jfc.services.runner import Runner

    runner = Runner(settings)
    scheduler = Scheduler(timezone=settings.scheduler.timezone)

    async def scheduled_run():
        await runner.run(scheduled=True)

    scheduler.add_cron_job(
        name="collection_update",
        func=scheduled_run,
        cron_expression=cron_expr,
    )

    console.print(f"[green]Scheduler started[/green] with cron: {cron_expr}")
    console.print("Press Ctrl+C to stop")

    try:
        asyncio.get_event_loop().run_forever()
    except KeyboardInterrupt:
        scheduler.stop()
        asyncio.run(runner.close())
        console.print("\n[yellow]Scheduler stopped[/yellow]")


@app.command()
def list_collections(
    config_path: Optional[Path] = typer.Option(
        None, "--config", help="Path to Kometa config directory"
    ),
) -> None:
    """List all configured collections."""
    settings = get_settings()

    if config_path:
        settings.config_path = config_path

    from jfc.parsers.kometa import KometaParser

    parser = KometaParser(settings.config_path)
    all_collections = parser.get_all_collections()

    for library_name, collections in all_collections.items():
        table = Table(title=f"Library: {library_name}")
        table.add_column("Collection", style="cyan")
        table.add_column("Schedule", style="green")
        table.add_column("Sources", style="yellow")

        for config in collections:
            sources = []
            if config.tmdb_trending_weekly:
                sources.append(f"TMDb Trending ({config.tmdb_trending_weekly})")
            if config.tmdb_popular:
                sources.append(f"TMDb Popular ({config.tmdb_popular})")
            if config.tmdb_discover:
                sources.append("TMDb Discover")
            if config.trakt_trending:
                sources.append(f"Trakt Trending ({config.trakt_trending})")
            if config.trakt_chart:
                sources.append(f"Trakt Chart ({config.trakt_chart.get('chart', 'unknown')})")
            if config.plex_search:
                sources.append("Library Search")

            table.add_row(
                config.name,
                config.schedule.schedule_type.value,
                ", ".join(sources) or "None",
            )

        console.print(table)
        console.print()


@app.command()
def validate(
    config_path: Optional[Path] = typer.Option(
        None, "--config", help="Path to Kometa config directory"
    ),
) -> None:
    """Validate configuration files."""
    settings = get_settings()

    if config_path:
        settings.config_path = config_path

    from jfc.parsers.kometa import KometaParser

    console.print(f"Validating config at: {settings.config_path}")

    try:
        parser = KometaParser(settings.config_path)
        config = parser.parse_config()

        if not config:
            console.print("[red]Error:[/red] Could not parse config.yml")
            raise typer.Exit(1)

        console.print("[green]config.yml:[/green] OK")

        # Validate libraries
        libraries = config.get("libraries", {})
        console.print(f"Found {len(libraries)} libraries")

        # Parse all collections
        all_collections = parser.get_all_collections()

        total = sum(len(c) for c in all_collections.values())
        console.print(f"[green]Total collections:[/green] {total}")

        for lib, cols in all_collections.items():
            console.print(f"  - {lib}: {len(cols)} collections")

        console.print("\n[green]Configuration is valid![/green]")

    except Exception as e:
        console.print(f"[red]Validation error:[/red] {e}")
        raise typer.Exit(1)


@app.command()
def test_connections() -> None:
    """Test connections to all configured services."""
    settings = get_settings()
    setup_logging(level="WARNING")

    async def _test():
        results = []

        # Test Jellyfin
        from jfc.clients.jellyfin import JellyfinClient

        try:
            client = JellyfinClient(settings.jellyfin.url, settings.jellyfin.api_key)
            libraries = await client.get_libraries()
            results.append(("Jellyfin", "OK", f"{len(libraries)} libraries"))
            await client.close()
        except Exception as e:
            results.append(("Jellyfin", "FAIL", str(e)))

        # Test TMDb
        from jfc.clients.tmdb import TMDbClient

        try:
            client = TMDbClient(settings.tmdb.api_key)
            movies = await client.get_popular_movies(1)
            results.append(("TMDb", "OK", "Connected"))
            await client.close()
        except Exception as e:
            results.append(("TMDb", "FAIL", str(e)))

        # Test Trakt (if configured)
        if settings.trakt.client_id:
            from jfc.clients.trakt import TraktClient

            try:
                client = TraktClient(
                    settings.trakt.client_id,
                    settings.trakt.client_secret,
                    settings.trakt.access_token,
                )
                movies = await client.get_trending_movies(1)
                results.append(("Trakt", "OK", "Connected"))
                await client.close()
            except Exception as e:
                results.append(("Trakt", "FAIL", str(e)))

        # Test Radarr (if configured)
        if settings.radarr.api_key:
            from jfc.clients.radarr import RadarrClient

            try:
                client = RadarrClient(settings.radarr.url, settings.radarr.api_key)
                healthy = await client.health_check()
                status = "OK" if healthy else "FAIL"
                results.append(("Radarr", status, "Connected" if healthy else "Health check failed"))
                await client.close()
            except Exception as e:
                results.append(("Radarr", "FAIL", str(e)))

        # Test Sonarr (if configured)
        if settings.sonarr.api_key:
            from jfc.clients.sonarr import SonarrClient

            try:
                client = SonarrClient(settings.sonarr.url, settings.sonarr.api_key)
                healthy = await client.health_check()
                status = "OK" if healthy else "FAIL"
                results.append(("Sonarr", status, "Connected" if healthy else "Health check failed"))
                await client.close()
            except Exception as e:
                results.append(("Sonarr", "FAIL", str(e)))

        # Display results
        table = Table(title="Connection Tests")
        table.add_column("Service", style="cyan")
        table.add_column("Status")
        table.add_column("Details", style="dim")

        for service, status, details in results:
            status_style = "green" if status == "OK" else "red"
            table.add_row(service, f"[{status_style}]{status}[/{status_style}]", details)

        console.print(table)

    asyncio.run(_test())


@app.command()
def version() -> None:
    """Show version information."""
    from jfc import __version__

    console.print(f"Jellyfin Collection v{__version__}")


if __name__ == "__main__":
    app()
