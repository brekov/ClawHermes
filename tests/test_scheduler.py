"""
ClawHermes - Cron 调度器测试
"""
from __future__ import annotations

import asyncio
import tempfile
import time

from clawhermes.agent.scheduler import (
    CronScheduler,
    JobStatus,
    ScheduledJob,
    ScheduleMode,
    ScheduleSpec,
)


class TestScheduleSpec:
    def test_cron_mode(self):
        spec = ScheduleSpec.cron(minute="30", hour="9", day_of_week="1")
        assert spec.mode == ScheduleMode.CRON
        assert spec.minute == "30"
        assert spec.hour == "9"
        assert spec.day_of_week == "1"

    def test_interval_mode(self):
        spec = ScheduleSpec.interval(seconds=3600)
        assert spec.mode == ScheduleMode.INTERVAL
        assert spec.interval_seconds == 3600

    def test_oneshot_mode_with_delay(self):
        spec = ScheduleSpec.oneshot(delay_seconds=600)
        assert spec.mode == ScheduleMode.ONESHOT
        assert spec.run_at > 0

    def test_oneshot_mode_with_timestamp(self):
        target = time.time() + 7200
        spec = ScheduleSpec.oneshot(run_at=target)
        assert spec.mode == ScheduleMode.ONESHOT
        assert spec.run_at == target

    def test_serialization_roundtrip(self):
        spec = ScheduleSpec.cron(minute="0", hour="8")
        d = spec.to_dict()
        restored = ScheduleSpec.from_dict(d)
        assert restored.mode == ScheduleMode.CRON
        assert restored.minute == "0"
        assert restored.hour == "8"


class TestScheduledJob:
    def test_create_job(self):
        spec = ScheduleSpec.interval(3600)
        job = ScheduledJob(
            job_id="j1",
            name="test job",
            spec=spec,
            task="say hello",
        )
        assert job.job_id == "j1"
        assert job.status == JobStatus.PENDING
        assert job.run_count == 0

    def test_job_serialization(self):
        spec = ScheduleSpec.interval(60)
        job = ScheduledJob(
            job_id="j2",
            name="minutely",
            spec=spec,
            task="check status",
            session_id="sess_abc",
            metadata={"env": "prod"},
        )
        d = job.to_dict()
        restored = ScheduledJob.from_dict(d)
        assert restored.job_id == "j2"
        assert restored.name == "minutely"
        assert restored.task == "check status"
        assert restored.session_id == "sess_abc"
        assert restored.metadata["env"] == "prod"
        assert restored.spec.mode == ScheduleMode.INTERVAL


class TestCronScheduler:
    def test_create_and_list_jobs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sched = CronScheduler(tmpdir)
            sched.create_job("daily report", "generate report",
                             ScheduleSpec.interval(3600))
            sched.create_job("weekly cleanup", "clean cache",
                             ScheduleSpec.cron("0", "2", "0"))

            jobs = sched.list_jobs()
            assert len(jobs) == 2
            names = {j.name for j in jobs}
            assert "daily report" in names
            assert "weekly cleanup" in names

    def test_get_job(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sched = CronScheduler(tmpdir)
            job = sched.create_job("test", "echo hi", ScheduleSpec.interval(60))
            fetched = sched.get_job(job.job_id)
            assert fetched is not None
            assert fetched.name == "test"

    def test_get_nonexistent_job(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sched = CronScheduler(tmpdir)
            assert sched.get_job("nonexistent") is None

    def test_delete_job(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sched = CronScheduler(tmpdir)
            job = sched.create_job("temp", "do thing", ScheduleSpec.interval(10))
            assert sched.delete_job(job.job_id) is True
            assert sched.get_job(job.job_id) is None
            assert sched.delete_job("nonexistent") is False

    def test_pause_and_resume(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sched = CronScheduler(tmpdir)
            job = sched.create_job("pausable", "do work", ScheduleSpec.interval(60))
            assert sched.pause_job(job.job_id) is True
            assert sched.get_job(job.job_id).status == JobStatus.PAUSED
            assert sched.pause_job(job.job_id) is False

            assert sched.resume_job(job.job_id) is True
            assert sched.get_job(job.job_id).status == JobStatus.PENDING

    def test_filter_jobs_by_status(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sched = CronScheduler(tmpdir)
            job = sched.create_job("pausable", "work", ScheduleSpec.interval(60))
            sched.pause_job(job.job_id)
            sched.create_job("active", "work", ScheduleSpec.interval(120))

            active = sched.list_jobs(status="pending")
            assert len(active) == 1
            assert active[0].name == "active"

            paused = sched.list_jobs(status="paused")
            assert len(paused) == 1
            assert paused[0].name == "pausable"

    async def test_execute_job(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sched = CronScheduler(tmpdir)
            executed = []

            def executor(task, session_id):
                executed.append(task)
                return "done"

            sched.set_executor(executor)
            sched.create_job("quick", "print time", ScheduleSpec.interval(1))
            await sched.start()

            await asyncio.sleep(2.5)
            await sched.stop()

            assert len(executed) >= 1

    def test_persistence_across_restarts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sched1 = CronScheduler(tmpdir)
            sched1.create_job("persistent", "keep alive", ScheduleSpec.interval(300))
            sched1.create_job("daily", "daily task",
                              ScheduleSpec.cron("0", "9", "*"))

            sched2 = CronScheduler(tmpdir)
            jobs = sched2.list_jobs()
            assert len(jobs) == 2
            names = {j.name for j in jobs}
            assert "persistent" in names
            assert "daily" in names

    async def test_oneshot_executes_once(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sched = CronScheduler(tmpdir)
            call_count = 0

            def executor(task, session_id):
                nonlocal call_count
                call_count += 1
                return "ok"

            sched.set_executor(executor)
            sched.create_job("once", "fire", ScheduleSpec.oneshot(delay_seconds=1))
            await sched.start()

            await asyncio.sleep(2)
            await sched.stop()

            assert call_count == 1

    def test_job_count_property(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sched = CronScheduler(tmpdir)
            assert sched.job_count == 0
            sched.create_job("a", "x", ScheduleSpec.interval(60))
            sched.create_job("b", "y", ScheduleSpec.interval(120))
            assert sched.job_count == 2

    async def test_start_stop_idempotent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sched = CronScheduler(tmpdir)
            await sched.start()
            await sched.start()  # idempotent
            await sched.stop()
            await sched.stop()   # idempotent

    async def test_executor_not_set_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sched = CronScheduler(tmpdir)
            sched.create_job("noexec", "do", ScheduleSpec.oneshot(delay_seconds=1))
            await sched.start()
            await asyncio.sleep(1.5)
            await sched.stop()
