"""ClawHermes Gateway - Cron job routes (/cron/jobs)"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import clawhermes.gateway.app as _gw
from clawhermes.agent.scheduler import ScheduleMode, ScheduleSpec

router = APIRouter()


class CronJobRequest(BaseModel):
    name: str
    task: str
    mode: str = "interval"
    interval_seconds: int = 3600
    minute: str = "*"
    hour: str = "*"
    day_of_week: str = "*"
    delay_seconds: int = 0
    session_id: str = ""


@router.post("/cron/jobs")
def create_cron_job(req: CronJobRequest):
    if _gw._state.scheduler is None:
        raise HTTPException(500, "调度器未初始化")
    try:
        mode = ScheduleMode(req.mode)
        if mode == ScheduleMode.CRON:
            spec = ScheduleSpec.cron(req.minute, req.hour, req.day_of_week)
        elif mode == ScheduleMode.ONESHOT:
            spec = ScheduleSpec.oneshot(delay_seconds=req.delay_seconds)
        else:
            spec = ScheduleSpec.interval(req.interval_seconds)
        job = _gw._state.scheduler.create_job(req.name, req.task, spec, session_id=req.session_id)
        return {"status": "ok", "job": job.to_dict()}
    except ValueError as e:
        raise HTTPException(400, f"无效的调度模式: {e}")


@router.get("/cron/jobs")
def list_cron_jobs(status: str | None = None):
    if _gw._state.scheduler is None:
        return {"jobs": [], "count": 0}
    jobs = _gw._state.scheduler.list_jobs(status=status)
    return {"jobs": [j.to_dict() for j in jobs], "count": len(jobs)}


@router.get("/cron/jobs/{job_id}")
def get_cron_job(job_id: str):
    if _gw._state.scheduler is None:
        raise HTTPException(500, "调度器未初始化")
    job = _gw._state.scheduler.get_job(job_id)
    if job is None:
        raise HTTPException(404, f"任务不存在: {job_id}")
    return {"job": job.to_dict()}


@router.delete("/cron/jobs/{job_id}")
def delete_cron_job(job_id: str):
    if _gw._state.scheduler is None:
        raise HTTPException(500, "调度器未初始化")
    if _gw._state.scheduler.delete_job(job_id):
        return {"status": "ok"}
    raise HTTPException(404, f"任务不存在: {job_id}")


@router.post("/cron/jobs/{job_id}/pause")
def pause_cron_job(job_id: str):
    if _gw._state.scheduler is None:
        raise HTTPException(500, "调度器未初始化")
    if _gw._state.scheduler.pause_job(job_id):
        return {"status": "ok"}
    raise HTTPException(400, f"无法暂停任务: {job_id}")


@router.post("/cron/jobs/{job_id}/resume")
def resume_cron_job(job_id: str):
    if _gw._state.scheduler is None:
        raise HTTPException(500, "调度器未初始化")
    if _gw._state.scheduler.resume_job(job_id):
        return {"status": "ok"}
    raise HTTPException(400, f"无法恢复任务: {job_id}")
