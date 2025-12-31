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


async def ensure_trakt_auth(settings) -> bool:
    """
    Ensure Trakt is authenticated if configured.

    Automatically starts device code flow if not authenticated.
    Returns True if authenticated (or Trakt not configured), False if auth failed.
    """
    if not settings.trakt.client_id or not settings.trakt.client_secret:
        return True  # Trakt not configured, nothing to do

    from jfc.services.trakt_auth import TraktAuth

    auth = TraktAuth(
        client_id=settings.trakt.client_id,
        client_secret=settings.trakt.client_secret,
        data_dir=settings.get_data_path(),
    )

    # Try to get valid token (auto-refresh if expired)
    access_token = await auth.get_valid_token()

    if access_token:
        return True  # Already authenticated

    # Not authenticated - start device code flow
    console.print()
    console.print("[yellow]Trakt is configured but not authenticated.[/yellow]")
    console.print("[cyan]Starting automatic authentication...[/cyan]")
    console.print()

    def on_code_received(user_code: str, verification_url: str, expires_in: int):
        console.print("[cyan]═══════════════════════════════════════════════════════════[/cyan]")
        console.print("[cyan]                    TRAKT AUTHENTICATION                   [/cyan]")
        console.print("[cyan]═══════════════════════════════════════════════════════════[/cyan]")
        console.print()
        console.print(f"  1. Go to: [link={verification_url}]{verification_url}[/link]")
        console.print()
        console.print(f"  2. Enter code: [bold yellow]{user_code}[/bold yellow]")
        console.print()
        console.print(f"  [dim]Code expires in {expires_in // 60} minutes[/dim]")
        console.print()
        console.print("[cyan]═══════════════════════════════════════════════════════════[/cyan]")
        console.print()
        console.print("[dim]Waiting for authorization...[/dim]")

    tokens = await auth.device_code_flow(on_code_received=on_code_received)

    if tokens:
        console.print()
        console.print("[green]✓ Successfully authenticated with Trakt![/green]")
        console.print()
        return True
    else:
        console.print()
        console.print("[red]✗ Trakt authentication failed[/red]")
        console.print("[yellow]Continuing without Trakt...[/yellow]")
        console.print()
        return False


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
    force_posters: bool = typer.Option(
        False, "--force-posters", "-fp", help="Force regeneration of all posters"
    ),
) -> None:
    """Run collection updates."""
    settings = get_settings()

    if dry_run:
        settings.dry_run = True
    if config_path:
        settings.config_path = config_path

    # Setup logging with file output
    log_dir = settings.get_log_path()
    setup_logging(level=settings.log_level, log_dir=log_dir)

    from jfc.services.runner import Runner

    async def _run():
        # Ensure Trakt is authenticated if configured
        await ensure_trakt_auth(settings)

        runner = Runner(settings)
        try:
            report = await runner.run(
                libraries=libraries,
                collections=collections,
                scheduled=False,
                force_posters=force_posters,
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
    collections_cron: Optional[str] = typer.Option(
        None, "--collections-cron", help="Cron for collection sync (default: daily 3am)"
    ),
    posters_cron: Optional[str] = typer.Option(
        None, "--posters-cron", help="Cron for poster regeneration (default: 1st of month, empty=disabled)"
    ),
    no_run_on_start: bool = typer.Option(
        False, "--no-run-on-start", help="Skip initial run on startup"
    ),
) -> None:
    """Run with scheduler for periodic updates (daemon mode)."""
    settings = get_settings()
    log_dir = settings.get_log_path()
    setup_logging(level=settings.log_level, log_dir=log_dir)

    from loguru import logger
    from jfc.services.runner import Runner

    # Get cron expressions from args or settings
    col_cron = collections_cron or settings.scheduler.collections_cron
    post_cron = posters_cron if posters_cron is not None else settings.scheduler.posters_cron
    run_on_start = settings.scheduler.run_on_start and not no_run_on_start

    runner = Runner(settings)
    scheduler = Scheduler(timezone=settings.scheduler.timezone)

    async def collections_sync():
        """Daily collection sync (no poster regeneration)."""
        logger.info("Starting scheduled collection sync...")
        try:
            await runner.run(scheduled=True, force_posters=False)
        except Exception as e:
            logger.error(f"Scheduled collection sync failed: {e}")

    async def posters_regeneration():
        """Monthly poster regeneration - always forces regeneration of all posters.

        The scheduled job always regenerates all posters because collection content
        changes over time. Use the manual 'regenerate-posters --missing-only' command
        if you only want to generate missing posters.
        """
        logger.info("Starting scheduled poster regeneration (force all)...")
        try:
            await runner.run(
                scheduled=True,
                force_posters=True,  # Always force on scheduled runs
                posters_only=True,
            )
        except Exception as e:
            logger.error(f"Scheduled poster regeneration failed: {e}")

    async def _run_scheduler():
        """Main async scheduler loop."""
        # Ensure Trakt is authenticated if configured (at startup)
        await ensure_trakt_auth(settings)

        # Schedule collection sync job
        scheduler.add_cron_job(
            name="collection_sync",
            func=collections_sync,
            cron_expression=col_cron,
        )
        console.print(f"[green]✓[/green] Collection sync scheduled: [cyan]{col_cron}[/cyan]")

        # Schedule poster regeneration job (if enabled)
        if post_cron and post_cron.strip():
            scheduler.add_cron_job(
                name="poster_regeneration",
                func=posters_regeneration,
                cron_expression=post_cron,
            )
            console.print(f"[green]✓[/green] Poster regeneration scheduled: [cyan]{post_cron}[/cyan] (force all)")
        else:
            console.print("[yellow]![/yellow] Poster regeneration disabled (no cron set)")

        console.print(f"[dim]Timezone: {settings.scheduler.timezone}[/dim]")
        console.print()

        # Run immediately on startup if configured
        if run_on_start:
            console.print("[cyan]Running initial collection sync...[/cyan]")
            try:
                await collections_sync()
            except Exception as e:
                console.print(f"[red]Initial sync failed:[/red] {e}")

        console.print("\n[green]Scheduler running.[/green] Press Ctrl+C to stop")

        # List next run times
        jobs = scheduler.list_jobs()
        if jobs:
            console.print("\n[dim]Next runs:[/dim]")
            for job in jobs:
                next_run = job.get("next_run", "N/A")
                if next_run and next_run != "N/A":
                    from datetime import datetime
                    dt = datetime.fromisoformat(next_run.replace("Z", "+00:00"))
                    next_run = dt.strftime("%Y-%m-%d %H:%M")
                console.print(f"  [dim]- {job['name']}: {next_run}[/dim]")

        # Keep running until interrupted
        try:
            while True:
                await asyncio.sleep(3600)  # Sleep 1 hour
        except asyncio.CancelledError:
            pass

    try:
        asyncio.run(_run_scheduler())
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
            from jfc.services.trakt_auth import TraktAuth

            try:
                # Use TraktAuth to get valid token
                auth = TraktAuth(
                    client_id=settings.trakt.client_id,
                    client_secret=settings.trakt.client_secret,
                    data_dir=settings.get_data_path(),
                )
                access_token = await auth.get_valid_token()

                if not access_token:
                    results.append(("Trakt", "WARN", "Not authenticated (run: jfc trakt-auth)"))
                else:
                    client = TraktClient(
                        settings.trakt.client_id,
                        settings.trakt.client_secret,
                        access_token,
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

        # Test OpenAI (if enabled)
        if settings.openai.enabled and settings.openai.api_key:
            import httpx

            try:
                async with httpx.AsyncClient(timeout=10.0) as http_client:
                    # Check API key
                    response = await http_client.get(
                        "https://api.openai.com/v1/models",
                        headers={"Authorization": f"Bearer {settings.openai.api_key}"},
                    )
                    if response.status_code != 200:
                        results.append(("OpenAI", "FAIL", f"API error: {response.status_code}"))
                    else:
                        # Check credits with mini completion
                        response = await http_client.post(
                            "https://api.openai.com/v1/chat/completions",
                            headers={
                                "Authorization": f"Bearer {settings.openai.api_key}",
                                "Content-Type": "application/json",
                            },
                            json={
                                "model": "gpt-4o-mini",
                                "messages": [{"role": "user", "content": "Hi"}],
                                "max_tokens": 1,
                            },
                        )
                        if response.status_code == 200:
                            results.append(("OpenAI", "OK", "Credits OK"))
                        elif response.status_code in (429, 402):
                            results.append(("OpenAI", "FAIL", "No credits"))
                        else:
                            results.append(("OpenAI", "FAIL", f"Error: {response.status_code}"))
            except Exception as e:
                results.append(("OpenAI", "FAIL", str(e)))

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
def generate_poster(
    collection_name: str = typer.Argument(..., help="Collection name (e.g., 'Tendances')"),
    category: str = typer.Option(
        "FILMS", "--category", "-c", help="Category: FILMS, SÉRIES, or CARTOONS"
    ),
    library: str = typer.Option(
        "Films", "--library", "-l", help="Library name for folder organization"
    ),
    output_dir: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Output directory for generated posters"
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Regenerate even if poster exists"
    ),
) -> None:
    """Generate a poster for a collection using OpenAI gpt-image-1.5."""
    settings = get_settings()
    setup_logging(level=settings.log_level)

    # Check OpenAI configuration
    if not settings.openai.api_key:
        console.print("[red]Error:[/red] OPENAI_API_KEY not configured")
        console.print("Set OPENAI_API_KEY in your .env file")
        raise typer.Exit(1)

    if not settings.openai.enabled:
        console.print("[yellow]Warning:[/yellow] OpenAI is disabled (OPENAI_ENABLED=false)")
        console.print("Set OPENAI_ENABLED=true to enable poster generation")
        raise typer.Exit(1)

    # Validate category
    valid_categories = ["FILMS", "SÉRIES", "CARTOONS"]
    if category.upper() not in valid_categories:
        console.print(f"[red]Error:[/red] Invalid category. Choose from: {', '.join(valid_categories)}")
        raise typer.Exit(1)

    async def _generate():
        from jfc.services.poster_generator import PosterGenerator

        out_path = output_dir or settings.get_posters_path()
        generator = PosterGenerator(
            api_key=settings.openai.api_key,
            output_dir=out_path,
            cache_dir=settings.get_cache_path(),
            poster_history_limit=settings.openai.poster_history_limit,
            prompt_history_limit=settings.openai.prompt_history_limit,
        )

        console.print(f"[cyan]Generating poster for:[/cyan] {collection_name}")
        console.print(f"[cyan]Category:[/cyan] {category.upper()}")
        console.print(f"[cyan]Library:[/cyan] {library}")
        console.print(f"[cyan]Output:[/cyan] {out_path}/{library}/{collection_name}/")
        console.print()

        from jfc.models.collection import CollectionConfig

        config = CollectionConfig(
            name=collection_name,
            summary=f"Collection {collection_name}",
        )

        result = await generator.generate_poster(
            config=config,
            items=[],
            category=category.upper(),
            library=library,
            force_regenerate=force,
        )

        if result:
            console.print(f"\n[green]Poster generated:[/green] {result}")
        else:
            console.print("\n[red]Failed to generate poster[/red]")
            raise typer.Exit(1)

    asyncio.run(_generate())


@app.command()
def regenerate_posters(
    libraries: Optional[list[str]] = typer.Option(
        None, "--library", "-l", help="Libraries to process (can be repeated)"
    ),
    collections: Optional[list[str]] = typer.Option(
        None, "--collection", "-c", help="Collections to process (can be repeated)"
    ),
    missing_only: Optional[bool] = typer.Option(
        None, "--missing-only/--force-all", "-m/-f",
        help="Only generate missing posters, or force regenerate all"
    ),
) -> None:
    """Regenerate AI posters for collections.

    By default, uses the 'missing_only' setting from config.yml (openai.missing_only).
    Use --missing-only to only generate posters for collections that don't have one yet.
    Use --force-all to regenerate all posters regardless of existing ones.

    Note: The scheduled poster job always uses --force-all mode.
    """
    settings = get_settings()
    log_dir = settings.get_log_path()
    setup_logging(level=settings.log_level, log_dir=log_dir)

    # Check OpenAI configuration
    if not settings.openai.api_key or not settings.openai.enabled:
        console.print("[red]Error:[/red] OpenAI not configured or disabled")
        console.print("Set OPENAI_API_KEY and OPENAI_ENABLED=true in your .env")
        raise typer.Exit(1)

    # Use CLI flag if provided, otherwise use setting from config
    use_missing_only = missing_only if missing_only is not None else settings.openai.missing_only

    from jfc.services.runner import Runner

    async def _run():
        await ensure_trakt_auth(settings)

        runner = Runner(settings)
        try:
            if use_missing_only:
                console.print("[cyan]Generating missing posters only...[/cyan]")
            else:
                console.print("[cyan]Regenerating all posters (force)...[/cyan]")

            report = await runner.run(
                libraries=libraries,
                collections=collections,
                scheduled=False,
                force_posters=not use_missing_only,  # Force only if not missing_only
                posters_only=True,  # Skip collection sync, only do posters
            )
            console.print(
                f"\n[green]Completed![/green] "
                f"{report.successful_collections} collections processed"
            )
        finally:
            await runner.close()

    asyncio.run(_run())


@app.command()
def trakt_auth() -> None:
    """Authenticate with Trakt using OAuth Device Code flow."""
    settings = get_settings()
    setup_logging(level="WARNING")

    # Check if Trakt is configured
    if not settings.trakt.client_id or not settings.trakt.client_secret:
        console.print("[red]Error:[/red] TRAKT_CLIENT_ID and TRAKT_CLIENT_SECRET must be set")
        console.print("\nGet your credentials at: https://trakt.tv/oauth/applications")
        raise typer.Exit(1)

    from jfc.services.trakt_auth import TraktAuth

    auth = TraktAuth(
        client_id=settings.trakt.client_id,
        client_secret=settings.trakt.client_secret,
        data_dir=settings.get_data_path(),
    )

    # Check if already authenticated
    tokens = auth.load_tokens()
    if tokens and not tokens.is_expired():
        console.print("[green]Already authenticated with Trakt![/green]")
        console.print(f"Token expires: {tokens.expires_at.strftime('%Y-%m-%d %H:%M')}")

        reauth = typer.confirm("Do you want to re-authenticate?", default=False)
        if not reauth:
            raise typer.Exit(0)

    def on_code_received(user_code: str, verification_url: str, expires_in: int):
        console.print()
        console.print("[cyan]═══════════════════════════════════════════════════════════[/cyan]")
        console.print("[cyan]                    TRAKT AUTHENTICATION                   [/cyan]")
        console.print("[cyan]═══════════════════════════════════════════════════════════[/cyan]")
        console.print()
        console.print(f"  1. Go to: [link={verification_url}]{verification_url}[/link]")
        console.print()
        console.print(f"  2. Enter code: [bold yellow]{user_code}[/bold yellow]")
        console.print()
        console.print(f"  [dim]Code expires in {expires_in // 60} minutes[/dim]")
        console.print()
        console.print("[cyan]═══════════════════════════════════════════════════════════[/cyan]")
        console.print()
        console.print("[dim]Waiting for authorization...[/dim]")

    async def _auth():
        tokens = await auth.device_code_flow(on_code_received=on_code_received)

        if tokens:
            console.print()
            console.print("[green]✓ Successfully authenticated with Trakt![/green]")
            console.print(f"  Token saved to: {auth.token_path}")
            console.print(f"  Expires: {tokens.expires_at.strftime('%Y-%m-%d %H:%M')}")
        else:
            console.print()
            console.print("[red]✗ Authentication failed[/red]")
            raise typer.Exit(1)

    asyncio.run(_auth())


@app.command()
def trakt_status() -> None:
    """Check Trakt authentication status."""
    settings = get_settings()
    setup_logging(level="WARNING")

    if not settings.trakt.client_id:
        console.print("[yellow]Trakt not configured[/yellow]")
        console.print("Set TRAKT_CLIENT_ID and TRAKT_CLIENT_SECRET in your .env")
        raise typer.Exit(0)

    from jfc.services.trakt_auth import TraktAuth

    auth = TraktAuth(
        client_id=settings.trakt.client_id,
        client_secret=settings.trakt.client_secret,
        data_dir=settings.get_data_path(),
    )

    tokens = auth.load_tokens()

    if not tokens:
        console.print("[yellow]Not authenticated[/yellow]")
        console.print("Run: jfc trakt-auth")
        raise typer.Exit(0)

    if tokens.is_expired():
        console.print("[red]Token expired[/red]")
        console.print(f"Expired: {tokens.expires_at.strftime('%Y-%m-%d %H:%M')}")
        console.print("Run: jfc trakt-auth")
    else:
        console.print("[green]Authenticated[/green]")
        console.print(f"Expires: {tokens.expires_at.strftime('%Y-%m-%d %H:%M')}")


@app.command()
def trakt_logout() -> None:
    """Revoke Trakt authentication and delete tokens."""
    settings = get_settings()
    setup_logging(level="WARNING")

    if not settings.trakt.client_id:
        console.print("[yellow]Trakt not configured[/yellow]")
        raise typer.Exit(0)

    from jfc.services.trakt_auth import TraktAuth

    auth = TraktAuth(
        client_id=settings.trakt.client_id,
        client_secret=settings.trakt.client_secret,
        data_dir=settings.get_data_path(),
    )

    tokens = auth.load_tokens()
    if not tokens:
        console.print("[yellow]Not authenticated[/yellow]")
        raise typer.Exit(0)

    if typer.confirm("Are you sure you want to logout from Trakt?"):
        async def _logout():
            await auth.revoke_token()

        asyncio.run(_logout())
        console.print("[green]Logged out from Trakt[/green]")


@app.command()
def version() -> None:
    """Show version information."""
    from jfc import __version__

    console.print(f"Jellyfin Collection v{__version__}")


if __name__ == "__main__":
    app()
