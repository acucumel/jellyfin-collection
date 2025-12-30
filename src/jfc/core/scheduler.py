"""Task scheduler using APScheduler."""

from datetime import datetime
from typing import Callable, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger


class Scheduler:
    """Task scheduler for periodic collection updates."""

    def __init__(self, timezone: str = "Europe/Paris"):
        """
        Initialize scheduler.

        Args:
            timezone: Timezone for cron expressions
        """
        self.timezone = timezone
        self._scheduler: Optional[AsyncIOScheduler] = None
        self._jobs: dict[str, str] = {}  # job_name -> job_id

    def start(self) -> None:
        """Start the scheduler."""
        if self._scheduler is None:
            self._scheduler = AsyncIOScheduler(timezone=self.timezone)

        if not self._scheduler.running:
            self._scheduler.start()
            logger.info(f"Scheduler started with timezone: {self.timezone}")

    def stop(self) -> None:
        """Stop the scheduler."""
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("Scheduler stopped")

    def add_cron_job(
        self,
        name: str,
        func: Callable,
        cron_expression: str,
        **kwargs,
    ) -> str:
        """
        Add a cron-scheduled job.

        Args:
            name: Job name for identification
            func: Async function to execute
            cron_expression: Cron expression (e.g., "0 3 * * *")
            **kwargs: Additional arguments passed to the job

        Returns:
            Job ID
        """
        if self._scheduler is None:
            self.start()

        # Parse cron expression
        parts = cron_expression.split()
        if len(parts) != 5:
            raise ValueError(f"Invalid cron expression: {cron_expression}")

        minute, hour, day, month, day_of_week = parts

        trigger = CronTrigger(
            minute=minute,
            hour=hour,
            day=day,
            month=month,
            day_of_week=day_of_week,
            timezone=self.timezone,
        )

        # Remove existing job with same name
        if name in self._jobs:
            self.remove_job(name)

        job = self._scheduler.add_job(
            func,
            trigger=trigger,
            id=name,
            name=name,
            replace_existing=True,
            **kwargs,
        )

        self._jobs[name] = job.id
        next_run = job.next_run_time.strftime("%Y-%m-%d %H:%M:%S") if job.next_run_time else "N/A"
        logger.info(f"Job '{name}' scheduled with cron '{cron_expression}'. Next run: {next_run}")

        return job.id

    def remove_job(self, name: str) -> bool:
        """
        Remove a scheduled job.

        Args:
            name: Job name

        Returns:
            True if job was removed
        """
        if name in self._jobs and self._scheduler:
            try:
                self._scheduler.remove_job(self._jobs[name])
                del self._jobs[name]
                logger.info(f"Job '{name}' removed")
                return True
            except Exception as e:
                logger.warning(f"Failed to remove job '{name}': {e}")
        return False

    def get_next_run(self, name: str) -> Optional[datetime]:
        """
        Get next run time for a job.

        Args:
            name: Job name

        Returns:
            Next run datetime or None
        """
        if name in self._jobs and self._scheduler:
            job = self._scheduler.get_job(self._jobs[name])
            if job:
                return job.next_run_time
        return None

    def list_jobs(self) -> list[dict]:
        """
        List all scheduled jobs.

        Returns:
            List of job info dictionaries
        """
        jobs = []
        if self._scheduler:
            for job in self._scheduler.get_jobs():
                jobs.append(
                    {
                        "id": job.id,
                        "name": job.name,
                        "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                        "trigger": str(job.trigger),
                    }
                )
        return jobs

    async def run_job_now(self, name: str) -> bool:
        """
        Trigger immediate execution of a job.

        Args:
            name: Job name

        Returns:
            True if job was triggered
        """
        if name in self._jobs and self._scheduler:
            job = self._scheduler.get_job(self._jobs[name])
            if job:
                logger.info(f"Triggering immediate run of job '{name}'")
                await job.func()
                return True
        return False
