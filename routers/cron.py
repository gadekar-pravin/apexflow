"""Cron router -- thin wrapper around SchedulerService (now async)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.auth import get_user_id
from core.scheduler import JobDefinition, scheduler_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/cron", tags=["Scheduler"])


class CreateJobRequest(BaseModel):
    name: str
    cron: str
    agent_type: str = "PlannerAgent"
    query: str


@router.get("/jobs")
async def list_jobs(
    user_id: str = Depends(get_user_id),
) -> list[JobDefinition]:
    return await scheduler_service.list_jobs(user_id)


@router.post("/jobs")
async def create_job(
    request: CreateJobRequest,
    user_id: str = Depends(get_user_id),
) -> JobDefinition:
    try:
        return await scheduler_service.add_job(
            user_id=user_id,
            name=request.name,
            cron_expression=request.cron,
            agent_type=request.agent_type,
            query=request.query,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/jobs/{job_id}/trigger")
async def trigger_job(
    job_id: str,
    user_id: str = Depends(get_user_id),
) -> dict[str, str]:
    try:
        await scheduler_service.trigger_job(user_id, job_id)
        return {"status": "triggered", "id": job_id}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/jobs/{job_id}")
async def delete_job(
    job_id: str,
    user_id: str = Depends(get_user_id),
) -> dict[str, str]:
    await scheduler_service.delete_job(user_id, job_id)
    return {"status": "deleted", "id": job_id}
