"""Scheduler service -- v2 port from v1, DB-backed via stores.

Replaces filesystem (data/system/jobs.json) with JobStore + JobRunStore.
All methods are async. Uses APScheduler for cron scheduling.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from pydantic import BaseModel

from core.event_bus import event_bus
from core.stores.job_run_store import JobRunStore
from core.stores.job_store import JobStore
from core.stores.notification_store import NotificationStore

logger = logging.getLogger(__name__)


class JobDefinition(BaseModel):
    id: str
    user_id: str = "dev-user"
    name: str
    cron_expression: str
    agent_type: str = "PlannerAgent"
    query: str
    skill_id: str | None = None
    enabled: bool = True
    last_run: str | None = None
    next_run: str | None = None
    last_output: str | None = None


class SchedulerService:
    _instance: SchedulerService | None = None
    scheduler: AsyncIOScheduler
    jobs: dict[str, JobDefinition]
    initialized: bool
    _user_id: str

    def __new__(cls) -> SchedulerService:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.scheduler = AsyncIOScheduler()
            cls._instance.jobs = {}
            cls._instance.initialized = False
            cls._instance._user_id = "dev-user"
        return cls._instance

    # -- stores (injected or default) -----------------------------------------

    @property
    def job_store(self) -> JobStore:
        if not hasattr(self, "_job_store"):
            self._job_store = JobStore()
        return self._job_store

    @property
    def job_run_store(self) -> JobRunStore:
        if not hasattr(self, "_job_run_store"):
            self._job_run_store = JobRunStore()
        return self._job_run_store

    @property
    def notification_store(self) -> NotificationStore:
        if not hasattr(self, "_notification_store"):
            self._notification_store = NotificationStore()
        return self._notification_store

    # -- lifecycle ------------------------------------------------------------

    async def initialize(self, user_id: str = "dev-user") -> None:
        if self.initialized:
            return
        self._user_id = user_id
        try:
            await self.load_jobs()
        except Exception as e:
            logger.error("Failed to load jobs during init: %s", e)
            # Start scheduler anyway (empty) but allow re-init
        self.scheduler.start()
        logger.info("Scheduler Service started")
        self.initialized = True

    async def load_jobs(self) -> None:
        """Load jobs from DB and schedule enabled ones."""
        rows = await self.job_store.load_all(self._user_id)
        for row in rows:
            job_def = JobDefinition(
                id=row["id"],
                user_id=row.get("user_id", self._user_id),
                name=row["name"],
                cron_expression=row["cron_expression"],
                agent_type=row.get("agent_type", "PlannerAgent"),
                query=row["query"],
                skill_id=row.get("skill_id"),
                enabled=row.get("enabled", True),
                last_run=row["last_run"].isoformat() if row.get("last_run") else None,
                next_run=row["next_run"].isoformat() if row.get("next_run") else None,
                last_output=row.get("last_output"),
            )
            self.jobs[job_def.id] = job_def
            if job_def.enabled:
                self._schedule_job(job_def)
        logger.info("Loaded %d jobs from DB", len(self.jobs))

    def _schedule_job(self, job: JobDefinition) -> None:
        """Add job to APScheduler."""
        owner_id = job.user_id

        async def job_wrapper() -> None:
            from routers.runs import process_run

            run_id = f"auto_{job.id}_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
            # Truncate to minute for dedup (all workers firing the same cron
            # tick produce the same key regardless of sub-second differences).
            scheduled_for = datetime.now(UTC).replace(second=0, microsecond=0)

            # Dedup: try_claim before execution
            claimed = await self.job_run_store.try_claim(owner_id, job.id, scheduled_for)
            if not claimed:
                logger.info("Job %s already claimed for %s, skipping", job.id, scheduled_for)
                return

            log_msg = f"Triggering Scheduled Job: {job.name} ({run_id})"
            logger.info(log_msg)
            await event_bus.publish(
                "log",
                "scheduler",
                {"message": log_msg, "metadata": {"job_id": job.id, "run_id": run_id}},
            )

            # Update last run
            job.last_run = datetime.now(UTC).isoformat()
            await self.job_store.update(owner_id, job.id, last_run=datetime.now(UTC))

            try:
                # Skill lifecycle
                skill = None
                effective_query = job.query
                if job.skill_id:
                    try:
                        from core.skills.manager import skill_manager

                        skill = skill_manager.get_skill(job.skill_id)
                        if skill:
                            skill.context.run_id = run_id
                            skill.context.agent_id = job.agent_type
                            skill.context.config = {"query": job.query}
                            effective_query = await skill.on_run_start(job.query)
                    except Exception as e:
                        logger.warning("Skill loading failed: %s", e)

                result = await process_run(run_id, effective_query, user_id=owner_id)

                # Skill post-processing
                skill_result = None
                if skill and result:
                    skill_result = await skill.on_run_success(
                        result if isinstance(result, dict) else {"output": str(result)}
                    )

                await event_bus.publish(
                    "success",
                    "scheduler",
                    {"message": f"Job '{job.name}' completed", "metadata": {"job_id": job.id}},
                )

                output_summary = (
                    skill_result.get("summary") if skill_result else (result.get("summary") if result else "Success")
                )
                job.last_output = output_summary
                await self.job_store.update(owner_id, job.id, last_output=output_summary)

                # Mark job run complete
                await self.job_run_store.complete(owner_id, job.id, scheduled_for, "completed", output=output_summary)

                # Send notification
                notif_body = f"Job '{job.name}' finished.\n\n"
                if output_summary:
                    notif_body += f"**Summary**: {output_summary[:200]}\n\n"
                notif_body += f"*Run ID: {run_id}*"

                await self.notification_store.create(
                    owner_id,
                    source="Scheduler",
                    title=f"Completed: {job.name}",
                    body=notif_body,
                    priority=1,
                    metadata={"job_id": job.id, "run_id": run_id},
                )

            except Exception as e:
                error_msg = f"Job {job.name} failed: {e}"
                logger.error(error_msg)
                await event_bus.publish("error", "scheduler", {"message": error_msg})

                await self.job_run_store.complete(owner_id, job.id, scheduled_for, "failed", error=str(e))

                await self.notification_store.create(
                    owner_id,
                    source="Scheduler",
                    title=f"Job Failed: {job.name}",
                    body=f"Error: {e!s}",
                    priority=2,
                )

                if skill:
                    await skill.on_run_failure(str(e))

        try:
            self.scheduler.add_job(
                job_wrapper,
                CronTrigger.from_crontab(job.cron_expression),
                id=job.id,
                name=job.name,
                replace_existing=True,
            )
            aps_job = self.scheduler.get_job(job.id)
            if aps_job and aps_job.next_run_time:
                job.next_run = aps_job.next_run_time.isoformat()
        except Exception as e:
            logger.error("Invalid cron expression for %s: %s", job.name, e)

    async def add_job(
        self,
        user_id: str,
        name: str,
        cron_expression: str,
        agent_type: str,
        query: str,
    ) -> JobDefinition:
        """Add a new scheduled job."""
        skill_id = None
        try:
            from core.skills.manager import skill_manager

            if not skill_manager.skill_classes:
                skill_manager.initialize()
            skill_id = skill_manager.match_intent(query)
            if skill_id:
                logger.info("Smart Scheduler: Matched '%s' to Skill '%s'", query, skill_id)
        except Exception as e:
            logger.debug("Skill intent matching skipped: %s", e)

        job_id = uuid.uuid4().hex[:16]
        job = JobDefinition(
            id=job_id,
            user_id=user_id,
            name=name,
            cron_expression=cron_expression,
            agent_type=agent_type,
            query=query,
            skill_id=skill_id,
        )

        await self.job_store.create(
            user_id,
            job_id,
            name=name,
            cron_expression=cron_expression,
            query=query,
            agent_type=agent_type,
            skill_id=skill_id,
        )

        self.jobs[job_id] = job
        self._schedule_job(job)
        return job

    async def trigger_job(self, user_id: str, job_id: str) -> None:
        """Force a job to run immediately."""
        if job_id not in self.jobs or self.jobs[job_id].user_id != user_id:
            raise KeyError(f"Job {job_id} not found for user {user_id}")
        if self.scheduler.get_job(job_id):
            self.scheduler.modify_job(job_id, next_run_time=datetime.now(UTC))
        else:
            self._schedule_job(self.jobs[job_id])
            self.scheduler.modify_job(job_id, next_run_time=datetime.now(UTC))

    async def delete_job(self, user_id: str, job_id: str) -> None:
        """Remove a job."""
        if job_id in self.jobs and self.jobs[job_id].user_id == user_id:
            if self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)
            del self.jobs[job_id]
            await self.job_store.delete(user_id, job_id)

    async def list_jobs(self, user_id: str) -> list[JobDefinition]:
        """List jobs for a specific user with updated next-run times."""
        result: list[JobDefinition] = []
        for job_id, job in self.jobs.items():
            if job.user_id != user_id:
                continue
            aps_job = self.scheduler.get_job(job_id)
            if aps_job and aps_job.next_run_time:
                job.next_run = aps_job.next_run_time.isoformat()
            result.append(job)
        return result


# Global singleton
scheduler_service = SchedulerService()
