"""
ClawHermes - Cron 调度器
基于 asyncio 的轻量级任务调度，支持 cron / interval / oneshot 三种模式
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


class ScheduleMode(str, Enum):
    CRON = "cron"
    INTERVAL = "interval"
    ONESHOT = "oneshot"


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"
    CANCELLED = "cancelled"


@dataclass
class ScheduleSpec:
    mode: ScheduleMode
    minute: str = "*"
    hour: str = "*"
    day_of_week: str = "*"
    interval_seconds: int = 0
    run_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "mode": self.mode.value,
            "minute": self.minute,
            "hour": self.hour,
            "day_of_week": self.day_of_week,
            "interval_seconds": self.interval_seconds,
            "run_at": self.run_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ScheduleSpec:
        return cls(
            mode=ScheduleMode(d["mode"]),
            minute=d.get("minute", "*"),
            hour=d.get("hour", "*"),
            day_of_week=d.get("day_of_week", "*"),
            interval_seconds=d.get("interval_seconds", 0),
            run_at=d.get("run_at", 0.0),
        )

    @classmethod
    def cron(cls, minute: str = "*", hour: str = "*", day_of_week: str = "*") -> ScheduleSpec:
        return cls(mode=ScheduleMode.CRON, minute=minute, hour=hour, day_of_week=day_of_week)

    @classmethod
    def interval(cls, seconds: int) -> ScheduleSpec:
        return cls(mode=ScheduleMode.INTERVAL, interval_seconds=seconds)

    @classmethod
    def oneshot(cls, delay_seconds: int = 0, run_at: float = 0.0) -> ScheduleSpec:
        target = run_at if run_at > 0 else time.time() + delay_seconds
        return cls(mode=ScheduleMode.ONESHOT, run_at=target)


@dataclass
class ScheduledJob:
    job_id: str
    name: str
    spec: ScheduleSpec
    task: str
    session_id: str = ""
    status: JobStatus = JobStatus.PENDING
    created_at: float = field(default_factory=time.time)
    last_run: float = 0.0
    next_run: float = 0.0
    run_count: int = 0
    error_count: int = 0
    last_error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "name": self.name,
            "spec": self.spec.to_dict(),
            "task": self.task,
            "session_id": self.session_id,
            "status": self.status.value,
            "created_at": self.created_at,
            "last_run": self.last_run,
            "next_run": self.next_run,
            "run_count": self.run_count,
            "error_count": self.error_count,
            "last_error": self.last_error,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ScheduledJob:
        return cls(
            job_id=d["job_id"],
            name=d["name"],
            spec=ScheduleSpec.from_dict(d["spec"]),
            task=d["task"],
            session_id=d.get("session_id", ""),
            status=JobStatus(d.get("status", "pending")),
            created_at=d.get("created_at", 0.0),
            last_run=d.get("last_run", 0.0),
            next_run=d.get("next_run", 0.0),
            run_count=d.get("run_count", 0),
            error_count=d.get("error_count", 0),
            last_error=d.get("last_error", ""),
            metadata=d.get("metadata", {}),
        )


class CronScheduler:
    """基于 asyncio 的任务调度器"""

    def __init__(self, data_dir: str | Path):
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._data_dir / "schedules.json"
        self._jobs: dict[str, ScheduledJob] = {}
        self._lock = asyncio.Lock()
        self._running = False
        self._task: asyncio.Task[Any] | None = None
        self._executor: Callable[[str, str], str] | None = None
        self._load_jobs()

    def set_executor(self, executor: Callable[[str, str], str]) -> None:
        """设置任务执行器，签名为 (task: str, session_id: str) -> result: str"""
        self._executor = executor

    def create_job(
        self,
        name: str,
        task: str,
        spec: ScheduleSpec,
        session_id: str = "",
        metadata: dict | None = None,
    ) -> ScheduledJob:
        job = ScheduledJob(
            job_id=f"job_{uuid.uuid4().hex[:10]}",
            name=name,
            spec=spec,
            task=task,
            session_id=session_id,
            metadata=metadata or {},
        )
        job.next_run = self._compute_next_run(job)
        self._jobs[job.job_id] = job
        self._save_jobs()
        logger.info("Job created: %s (%s)", job.job_id, job.name)
        return job

    def get_job(self, job_id: str) -> ScheduledJob | None:
        return self._jobs.get(job_id)

    def list_jobs(self, status: str | None = None) -> list[ScheduledJob]:
        jobs = list(self._jobs.values())
        if status:
            jobs = [j for j in jobs if j.status.value == status]
        return jobs

    def pause_job(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if not job:
            return False
        if job.status == JobStatus.PENDING:
            job.status = JobStatus.PAUSED
            self._save_jobs()
            return True
        return False

    def resume_job(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if not job:
            return False
        if job.status == JobStatus.PAUSED:
            job.status = JobStatus.PENDING
            job.next_run = self._compute_next_run(job)
            self._save_jobs()
            return True
        return False

    def delete_job(self, job_id: str) -> bool:
        if job_id in self._jobs:
            del self._jobs[job_id]
            self._save_jobs()
            return True
        return False

    async def start(self) -> None:
        """启动调度器（异步）"""
        if self._running:
            return
        self._running = True

        # 为所有 PENDING 任务计算下次运行时间
        async with self._lock:
            for job in self._jobs.values():
                if job.status == JobStatus.PENDING:
                    job.next_run = self._compute_next_run(job)
                elif job.status == JobStatus.PAUSED:
                    job.next_run = float("inf")

        self._task = asyncio.create_task(self._run_loop())
        logger.info("CronScheduler started (%d jobs)", len(self._jobs))

    async def _run_loop(self) -> None:
        """主调度循环 — 动态计算 sleep 时长，基于最近到期时间"""
        while self._running:
            now = time.time()
            async with self._lock:
                ready = [
                    j for j in self._jobs.values()
                    if j.status == JobStatus.PENDING and j.next_run <= now
                ]
                pending_times = [
                    j.next_run for j in self._jobs.values()
                    if j.status == JobStatus.PENDING and j.next_run < float("inf")
                ]
                if pending_times:
                    next_at = min(pending_times)
                    sleep_for = max(0.5, min(5.0, next_at - now))
                else:
                    sleep_for = 5.0

            for job in ready:
                await self._execute_job(job.job_id)

            await asyncio.sleep(sleep_for)

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("CronScheduler stopped")

    async def _execute_job(self, job_id: str) -> None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if not job or job.status in (JobStatus.PAUSED, JobStatus.CANCELLED):
                return
            job.status = JobStatus.RUNNING
            job.last_run = time.time()

        try:
            if self._executor:
                result = self._executor(job.task, job.session_id)
                logger.info("Job executed: %s → %s", job_id, result[:80] if result else "")
            else:
                logger.warning("No executor set for job %s", job_id)

            async with self._lock:
                job = self._jobs.get(job_id)
                if job:
                    job.status = JobStatus.PENDING if job.spec.mode != ScheduleMode.ONESHOT else JobStatus.COMPLETED
                    job.run_count += 1
                    job.last_error = ""

        except Exception as e:
            logger.error("Job %s failed: %s", job_id, e)
            async with self._lock:
                job = self._jobs.get(job_id)
                if job:
                    job.status = JobStatus.FAILED
                    job.error_count += 1
                    job.last_error = str(e)[:500]
                    if job.spec.mode != ScheduleMode.ONESHOT and job.error_count < 3:
                        job.status = JobStatus.PENDING

        async with self._lock:
            if job and job.spec.mode != ScheduleMode.ONESHOT:
                job.next_run = self._compute_next_run(job)
            self._save_jobs()

    def _compute_next_run(self, job: ScheduledJob) -> float:
        spec = job.spec
        now = time.time()

        if spec.mode == ScheduleMode.INTERVAL:
            return now + spec.interval_seconds

        if spec.mode == ScheduleMode.ONESHOT:
            return spec.run_at

        if spec.mode == ScheduleMode.CRON:
            import datetime
            dt = datetime.datetime.fromtimestamp(now)

            if spec.minute != "*":
                if int(spec.minute) <= dt.minute:
                    dt += datetime.timedelta(hours=1)
                dt = dt.replace(minute=int(spec.minute), second=0, microsecond=0)

            if spec.hour != "*":
                hour = int(spec.hour)
                if hour <= dt.hour:
                    dt += datetime.timedelta(days=1)
                dt = dt.replace(hour=hour)

            if spec.day_of_week != "*":
                target_dow = int(spec.day_of_week)
                current_dow = dt.weekday()
                days_ahead = (target_dow - current_dow) % 7
                if days_ahead == 0 and dt.timestamp() <= now:
                    days_ahead = 7
                dt += datetime.timedelta(days=days_ahead)

            return dt.timestamp()

        return now + 3600

    def _load_jobs(self) -> None:
        if not self._db_path.exists():
            return
        try:
            data = json.loads(self._db_path.read_text(encoding="utf-8"))
            for item in data:
                if not isinstance(item, dict):
                    continue
                job = ScheduledJob.from_dict(item)
                if job.status in (JobStatus.PENDING, JobStatus.PAUSED):
                    job.status = JobStatus.PENDING if job.status != JobStatus.PAUSED else JobStatus.PAUSED
                if job.status == JobStatus.RUNNING:
                    job.status = JobStatus.FAILED
                    job.last_error = "Interrupted by restart"
                self._jobs[job.job_id] = job
            logger.info("Loaded %d jobs from %s", len(self._jobs), self._db_path)
        except Exception as e:
            logger.error("Failed to load jobs: %s", e)

    def _save_jobs(self) -> None:
        try:
            data = [j.to_dict() for j in self._jobs.values()]
            self._db_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error("Failed to save jobs: %s", e)

    @property
    def job_count(self) -> int:
        return len(self._jobs)
