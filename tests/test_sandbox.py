"""
ClawHermes - Docker Sandbox 测试
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from clawhermes.tools.sandbox import (
    DockerSandbox,
    SandboxError,
    SandboxNotAvailableError,
    SandboxPool,
    SandboxResult,
    SandboxTimeoutError,
    _check_docker,
)


class TestSandboxDetection:
    def test_check_docker_binary(self):
        result = _check_docker()
        assert isinstance(result, bool)

    def test_docker_not_running_when_absent(self):
        with patch("clawhermes.tools.sandbox.shutil.which", return_value=None):
            assert not _check_docker()
            assert not DockerSandbox.is_available()

    def test_sandbox_not_available_without_docker(self):
        with patch("clawhermes.tools.sandbox.shutil.which", return_value=None):
            assert not DockerSandbox.is_available()


class TestSandboxResult:
    def test_success_result(self):
        r = SandboxResult(exit_code=0, stdout="hello", stderr="", duration_ms=100)
        assert r.exit_code == 0
        assert r.stdout == "hello"
        assert not r.truncated

    def test_error_result(self):
        r = SandboxResult(exit_code=1, stdout="", stderr="error msg", duration_ms=50)
        assert r.exit_code == 1
        assert r.stderr == "error msg"

    def test_truncated_result(self):
        r = SandboxResult(
            exit_code=0, stdout="x" * 100, stderr="",
            duration_ms=10, truncated=True,
        )
        assert r.truncated is True


class TestDockerSandbox:
    def test_default_image(self):
        sb = DockerSandbox()
        assert sb._image == "python:3.12-slim"
        assert sb._timeout == 30
        assert sb._memory == "256m"
        assert sb._cpu == "1.0"
        assert sb._network is True

    def test_custom_config(self):
        sb = DockerSandbox(
            image="ubuntu:22.04",
            timeout_seconds=60,
            memory_limit="512m",
            cpu_limit="2.0",
            network_enabled=False,
        )
        assert sb._image == "ubuntu:22.04"
        assert sb._timeout == 60
        assert sb._memory == "512m"
        assert sb._cpu == "2.0"
        assert sb._network is False

    def test_ensure_image_no_docker(self):
        with patch("clawhermes.tools.sandbox.shutil.which", return_value=None):
            sb = DockerSandbox()
            try:
                sb.ensure_image()
                assert False
            except SandboxNotAvailableError:
                pass

    def test_is_available_checks_daemon(self):
        with patch("clawhermes.tools.sandbox.shutil.which", return_value="/usr/bin/docker"):
            with patch("clawhermes.tools.sandbox._docker_is_running", return_value=True):
                assert DockerSandbox.is_available()

            with patch("clawhermes.tools.sandbox._docker_is_running", return_value=False):
                assert not DockerSandbox.is_available()

    def test_run_command_mocked(self):
        with patch("clawhermes.tools.sandbox.shutil.which", return_value="/usr/bin/docker"):
            with patch("clawhermes.tools.sandbox.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0, stdout="output", stderr="",
                )
                sb = DockerSandbox(image="alpine:latest")
                result = sb.run_command("echo hello")
                assert result.exit_code == 0
                assert result.stdout == "output"

    def test_run_python_mocked(self):
        with patch("clawhermes.tools.sandbox.shutil.which", return_value="/usr/bin/docker"):
            with patch("clawhermes.tools.sandbox.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0, stdout="result", stderr="",
                )
                sb = DockerSandbox()
                result = sb.run_python("print(2+2)")
                assert result.exit_code == 0
                assert result.stdout == "result"

    def test_timeout_handling(self):
        with patch("clawhermes.tools.sandbox.shutil.which", return_value="/usr/bin/docker"):
            with patch("clawhermes.tools.sandbox.subprocess.run") as mock_run:
                import subprocess
                mock_run.side_effect = subprocess.TimeoutExpired("docker", 5)
                sb = DockerSandbox(timeout_seconds=1)
                result = sb.run_command("sleep 100")
                assert result.exit_code == -1
                assert "timed out" in result.stderr.lower()

    def test_docker_error_handling(self):
        with patch("clawhermes.tools.sandbox.shutil.which", return_value="/usr/bin/docker"):
            with patch("clawhermes.tools.sandbox.subprocess.run") as mock_run:
                mock_run.side_effect = RuntimeError("docker broken")
                sb = DockerSandbox()
                result = sb.run_command("ls")
                assert result.exit_code == -1
                assert "error" in result.stderr.lower()


class TestSandboxPool:
    def test_create_pool(self):
        pool = SandboxPool(pool_size=3)
        assert pool._pool_size == 3
        assert pool.available == 0

    def test_acquire_release(self):
        with patch("clawhermes.tools.sandbox.shutil.which", return_value="/usr/bin/docker"):
            pool = SandboxPool(pool_size=2)
            sb1 = DockerSandbox()
            sb2 = DockerSandbox()
            pool.release(sb1)
            pool.release(sb2)
            assert pool.available == 2

            a1 = pool.acquire()
            assert pool.available == 1
            assert a1 is not None

            pool.acquire()
            assert pool.available == 0

            a3 = pool.acquire()
            assert pool.available == 0
            assert a3 is not None

    def test_exception_hierarchy(self):
        assert issubclass(SandboxNotAvailableError, SandboxError)
        assert issubclass(SandboxTimeoutError, SandboxError)
        from clawhermes.agent.exceptions import ClawHermesError
        assert issubclass(SandboxError, ClawHermesError)
