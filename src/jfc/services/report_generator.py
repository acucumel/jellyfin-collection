"""Service for generating detailed run reports."""

from pathlib import Path
from typing import Optional

from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from jfc.models.report import CollectionReport, LibraryReport, RunReport


class ReportGenerator:
    """Generates and outputs detailed run reports."""

    def __init__(self, console: Optional[Console] = None, output_dir: Optional[Path] = None):
        """
        Initialize report generator.

        Args:
            console: Rich console for terminal output
            output_dir: Directory to save report files
        """
        self.console = console or Console()
        self.output_dir = output_dir

    def print_collection_report(self, report: CollectionReport) -> None:
        """Print a single collection report to console."""
        status_color = "green" if report.success else "red"
        status_icon = "[OK]" if report.success else "[FAIL]"

        # Header
        self.console.print(
            f"\n[bold {status_color}]{status_icon}[/] [bold cyan]{report.name}[/] "
            f"[dim]({report.library})[/]"
        )

        if not report.success:
            self.console.print(f"  [red]Error: {report.error_message}[/]")
            return

        # Stats table
        stats_table = Table(show_header=False, box=None, padding=(0, 2))
        stats_table.add_column("Label", style="dim")
        stats_table.add_column("Value", style="bold")

        stats_table.add_row("Source", report.source_provider)
        stats_table.add_row("Items fetched", str(report.items_fetched))
        stats_table.add_row("After filters", str(report.items_after_filter))
        stats_table.add_row(
            "Match rate",
            f"[green]{report.match_rate:.1f}%[/] ({report.items_matched}/{report.items_after_filter})"
        )

        if report.items_missing > 0:
            stats_table.add_row("Missing items", f"[yellow]{report.items_missing}[/]")

        if report.items_added_to_collection > 0:
            stats_table.add_row(
                "Added to collection",
                f"[green]+{report.items_added_to_collection}[/]"
            )

        if report.items_removed_from_collection > 0:
            stats_table.add_row(
                "Removed from collection",
                f"[red]-{report.items_removed_from_collection}[/]"
            )

        if report.items_sent_to_radarr > 0:
            stats_table.add_row(
                "Sent to Radarr",
                f"[blue]{report.items_sent_to_radarr}[/]"
            )

        if report.items_sent_to_sonarr > 0:
            stats_table.add_row(
                "Sent to Sonarr",
                f"[blue]{report.items_sent_to_sonarr}[/]"
            )

        self.console.print(stats_table)

        # Show lists if verbose
        if report.added_titles:
            self.console.print(f"  [green]Added:[/] {', '.join(report.added_titles[:5])}")
            if len(report.added_titles) > 5:
                self.console.print(f"    [dim]... and {len(report.added_titles) - 5} more[/]")

        if report.missing_titles:
            self.console.print(f"  [yellow]Missing:[/] {', '.join(report.missing_titles[:5])}")
            if len(report.missing_titles) > 5:
                self.console.print(f"    [dim]... and {len(report.missing_titles) - 5} more[/]")

    def print_library_report(self, report: LibraryReport) -> None:
        """Print a library report to console."""
        self.console.print(
            f"\n[bold blue]Library: {report.name}[/] [dim]({report.media_type})[/]"
        )
        self.console.print(
            f"Collections: {report.successful_collections}/{report.total_collections} successful"
        )

        for collection in report.collections:
            self.print_collection_report(collection)

    def print_run_report(self, report: RunReport) -> None:
        """Print complete run report to console."""
        self.console.print()
        self.console.rule("[bold]Run Report[/]")

        # Summary panel
        duration_str = f"{report.duration_seconds:.1f}s" if report.duration_seconds else "N/A"

        summary_lines = [
            f"Run ID: {report.run_id}",
            f"Start: {report.start_time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Duration: {duration_str}",
            f"Mode: {'Dry Run' if report.dry_run else 'Live'}",
            f"Scheduled: {'Yes' if report.scheduled else 'No'}",
        ]

        self.console.print(Panel("\n".join(summary_lines), title="Summary", border_style="blue"))

        # Stats table
        stats_table = Table(title="Results", show_header=True, header_style="bold")
        stats_table.add_column("Metric", style="cyan")
        stats_table.add_column("Value", justify="right")

        stats_table.add_row("Total collections", str(report.total_collections))
        stats_table.add_row(
            "Successful",
            f"[green]{report.successful_collections}[/]"
        )
        stats_table.add_row(
            "Failed",
            f"[red]{report.failed_collections}[/]" if report.failed_collections else "0"
        )
        stats_table.add_row("Items added", f"[green]+{report.total_items_added}[/]")
        stats_table.add_row("Items removed", f"[red]-{report.total_items_removed}[/]")

        if report.total_radarr_requests > 0:
            stats_table.add_row("Radarr requests", f"[blue]{report.total_radarr_requests}[/]")
        if report.total_sonarr_requests > 0:
            stats_table.add_row("Sonarr requests", f"[blue]{report.total_sonarr_requests}[/]")

        self.console.print(stats_table)

        # Library details
        for library in report.libraries:
            self.print_library_report(library)

        self.console.rule()

    def generate_markdown_report(self, report: RunReport) -> str:
        """Generate a markdown report string."""
        lines = []

        # Header
        lines.append("# Jellyfin Collection - Run Report")
        lines.append("")
        lines.append(f"**Run ID:** {report.run_id}")
        lines.append(f"**Start:** {report.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        if report.end_time:
            lines.append(f"**End:** {report.end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"**Duration:** {report.duration_seconds:.1f}s")
        lines.append(f"**Mode:** {'Dry Run' if report.dry_run else 'Live'}")
        lines.append("")

        # Summary
        lines.append("## Summary")
        lines.append("")
        lines.append(f"- **Collections processed:** {report.total_collections}")
        lines.append(f"- **Successful:** {report.successful_collections}")
        lines.append(f"- **Failed:** {report.failed_collections}")
        lines.append(f"- **Items added:** +{report.total_items_added}")
        lines.append(f"- **Items removed:** -{report.total_items_removed}")
        if report.total_radarr_requests > 0:
            lines.append(f"- **Radarr requests:** {report.total_radarr_requests}")
        if report.total_sonarr_requests > 0:
            lines.append(f"- **Sonarr requests:** {report.total_sonarr_requests}")
        lines.append("")

        # Library details
        for library in report.libraries:
            lines.append(f"## Library: {library.name}")
            lines.append("")

            for col in library.collections:
                status = "OK" if col.success else "FAIL"
                lines.append(f"### {col.name} [{status}]")
                lines.append("")

                if not col.success:
                    lines.append(f"**Error:** {col.error_message}")
                    lines.append("")
                    continue

                lines.append(f"- **Source:** {col.source_provider}")
                lines.append(f"- **Items fetched:** {col.items_fetched}")
                lines.append(f"- **After filters:** {col.items_after_filter}")
                lines.append(f"- **Match rate:** {col.match_rate:.1f}% ({col.items_matched}/{col.items_after_filter})")
                lines.append(f"- **Missing:** {col.items_missing}")

                if col.items_added_to_collection > 0:
                    lines.append(f"- **Added:** +{col.items_added_to_collection}")
                if col.items_removed_from_collection > 0:
                    lines.append(f"- **Removed:** -{col.items_removed_from_collection}")
                if col.items_sent_to_radarr > 0:
                    lines.append(f"- **Sent to Radarr:** {col.items_sent_to_radarr}")
                if col.items_sent_to_sonarr > 0:
                    lines.append(f"- **Sent to Sonarr:** {col.items_sent_to_sonarr}")

                if col.added_titles:
                    lines.append("")
                    lines.append("**Added titles:**")
                    for title in col.added_titles[:10]:
                        lines.append(f"- {title}")
                    if len(col.added_titles) > 10:
                        lines.append(f"- ... and {len(col.added_titles) - 10} more")

                if col.missing_titles:
                    lines.append("")
                    lines.append("**Missing titles:**")
                    for title in col.missing_titles[:10]:
                        lines.append(f"- {title}")
                    if len(col.missing_titles) > 10:
                        lines.append(f"- ... and {len(col.missing_titles) - 10} more")

                lines.append("")

        return "\n".join(lines)

    def save_report(self, report: RunReport, filename: Optional[str] = None) -> Path:
        """Save report to file."""
        if not self.output_dir:
            raise ValueError("No output directory configured")

        self.output_dir.mkdir(parents=True, exist_ok=True)

        if not filename:
            filename = f"report_{report.run_id}.md"

        filepath = self.output_dir / filename
        content = self.generate_markdown_report(report)

        filepath.write_text(content, encoding="utf-8")
        logger.info(f"Report saved to: {filepath}")

        return filepath
