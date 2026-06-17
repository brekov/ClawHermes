"""
ClawHermes - Cron 调度器
基于 Python 标准库的轻量级任务调度，支持 cron / interval / oneshot 三种模式
"""
from __future__ import annotations

import json
import logging
import sched
import threading
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
    """基于标准库 sched 的任务调度器"""

    def __init__(self, data_dir: str | Path):
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._data_dir / "schedules.json"
        self._jobs: dict[str, ScheduledJob] = {}
        self._scheduler = sched.scheduler(time.time, time.sleep)
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
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

        with self._lock:
            self._jobs[job.job_id] = job
            self._save_jobs()
            if self._running:
                self._schedule_job(job)

        logger.info("Job created: %s (%s, mode=%s)", job.job_id, name, spec.mode.value)
        return job

    def get_job(self, job_id: str) -> ScheduledJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list_jobs(self, status: str | None = None) -> list[ScheduledJob]:
        with self._lock:
            jobs = list(self._jobs.values())
            if status:
                jobs = [j for j in jobs if j.status.value == status]
            return sorted(jobs, key=lambda j: j.created_at)

    def delete_job(self, job_id: str) -> bool:
        with self._lock:
            if job_id not in self._jobs:
                return False
            del self._jobs[job_id]
            self._save_jobs()
            return True

    def pause_job(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or job.status != JobStatus.PENDING:
                return False
            job.status = JobStatus.PAUSED
            self._save_jobs()
            return True

    def resume_job(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or job.status != JobStatus.PAUSED:
                return False
            job.status = JobStatus.PENDING
            job.next_run = self._compute_next_run(job)
            self._save_jobs()
            if self._running:
                self._schedule_job(job)
            return True

    def start(self) -> None:
        if self._running:
            return
        self._running = True

        with self._lock:
            for job in self._jobs.values():
                if job.status == JobStatus.PENDING:
                    job.next_run = self._compute_next_run(job)
                    self._schedule_job(job)

        def _run_loop():
            while self._running:
                try:
                    delay = self._scheduler.run(blocking=False)
                    if delay is None or delay > 1:
                        time.sleep(1)
                    elif delay > 0:
                        time.sleep(delay)
                except Exception as e:
                    logger.error("Scheduler loop error: %s", e)
                    time.sleep(5)

        self._thread = threading.Thread(target=_run_loop, daemon=True)
        self._thread.start()
        logger.info("CronScheduler started (%d jobs)", len(self._jobs))

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("CronScheduler stopped")

    def _schedule_job(self, job: ScheduledJob) -> None:
        if job.next_run <= time.time():
            delay: float = 0.0
        else:
            delay = job.next_run - time.time()

        self._scheduler.enter(
            delay=delay,
            priority=0,
            action=self._execute_job,
            argument=(job.job_id,),
        )

    def _execute_job(self, job_id: str) -> None:
        with self._lock:
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

            with self._lock:
                job = self._jobs.get(job_id)
                if job:
                    job.status = JobStatus.PENDING if job.spec.mode != ScheduleMode.ONESHOT else JobStatus.COMPLETED
                    job.run_count += 1
                    job.last_error = ""

        except Exception as e:
            logger.error("Job %s failed: %s", job_id, e)
            with self._lock:
                job = self._jobs.get(job_id)
                if job:
                    job.status = JobStatus.FAILED
                    job.error_count += 1
                    job.last_error = str(e)[:500]
                    if job.spec.mode != ScheduleMode.ONESHOT and job.error_count < 3:
                        job.status = JobStatus.PENDING

        if job and job.spec.mode != ScheduleMode.ONESHOT:
            with self._lock:
                job.next_run = self._compute_next_run(job)
                if job.status == JobStatus.PENDING:
                    self._schedule_job(job)
            self._save_jobs()
        else:
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
            with self._lock:
                for item in data:
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
        with self._lock:
            return len(self._jobs)
