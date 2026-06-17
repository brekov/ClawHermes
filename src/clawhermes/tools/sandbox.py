"""
ClawHermes - Docker 沙箱执行环境
在容器中安全执行代码/命令，支持资源限制和网络隔离
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from clawhermes.agent.exceptions import ClawHermesError

logger = logging.getLogger(__name__)


class SandboxError(ClawHermesError):
    """沙箱相关异常"""


class SandboxNotAvailableError(SandboxError):
    """Docker 沙箱不可用"""


class SandboxTimeoutError(SandboxError):
    """沙箱执行超时"""


@dataclass
class SandboxResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: float
    truncated: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


def _check_docker() -> bool:
    """检查 Docker 是否可用"""
    return shutil.which("docker") is not None


def _docker_is_running() -> bool:
    """检查 Docker daemon 是否在运行"""
    try:
        result = subprocess.run(
            ["docker", "info"], capture_output=True, timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


class DockerSandbox:
    """
    Docker 沙箱执行环境

    用户可自定义 image，默认使用 python:3.12-slim。
    支持:
    - Python 代码执行
    - Shell 命令执行
    - 超时控制
    - 内存限制
    - 网络隔离
    - 文件挂载
    """

    DEFAULT_IMAGE = "python:3.12-slim"

    def __init__(
        self,
        image: str | None = None,
        timeout_seconds: int = 30,
        memory_limit: str = "256m",
        cpu_limit: str = "1.0",
        network_enabled: bool = True,
        work_dir: str | Path | None = None,
    ):
        self._image = image or self.DEFAULT_IMAGE
        self._timeout = timeout_seconds
        self._memory = memory_limit
        self._cpu = cpu_limit
        self._network = network_enabled
        self._work_dir = Path(work_dir) if work_dir else Path.cwd()
        self._initialized = False

    @classmethod
    def is_available(cls) -> bool:
        return _check_docker() and _docker_is_running()

    def ensure_image(self) -> None:
        """拉取 Docker 镜像（如果不存在）"""
        if not _check_docker():
            raise SandboxNotAvailableError("Docker 未安装")

        try:
            result = subprocess.run(
                ["docker", "image", "inspect", self._image],
                capture_output=True, timeout=10,
            )
            if result.returncode != 0:
                logger.info("Pulling Docker image: %s", self._image)
                subprocess.run(
                    ["docker", "pull", self._image],
                    check=True, timeout=300,
                )
            self._initialized = True
        except subprocess.TimeoutExpired:
            raise SandboxError(f"Docker pull timeout for image: {self._image}")
        except subprocess.CalledProcessError as e:
            raise SandboxError(f"Docker pull failed: {e}")
        except Exception as e:
            raise SandboxNotAvailableError(f"Docker error: {e}")

    def run_python(self, code: str, timeout: int | None = None,
                   env: dict[str, str] | None = None) -> SandboxResult:
        """在沙箱中执行 Python 代码"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, prefix="ch_sandbox_",
        ) as f:
            f.write(code)
            script_path = f.name

        try:
            return self._run_container(
                command=["python3", f"/sandbox/{Path(script_path).name}"],
                mounts=[(script_path, "/sandbox/" + Path(script_path).name)],
                timeout=timeout,
                env=env,
            )
        finally:
            Path(script_path).unlink(missing_ok=True)

    def run_command(self, command: str, timeout: int | None = None,
                    env: dict[str, str] | None = None) -> SandboxResult:
        """在沙箱中执行 shell 命令"""
        return self._run_container(
            command=["sh", "-c", command],
            timeout=timeout,
            env=env,
        )

    def _run_container(
        self,
        command: list[str],
        mounts: list[tuple[str, str]] | None = None,
        timeout: int | None = None,
        env: dict[str, str] | None = None,
    ) -> SandboxResult:
        if not _check_docker():
            raise SandboxNotAvailableError("Docker 未安装")

        cmd = [
            "docker", "run", "--rm",
            f"--memory={self._memory}",
            f"--cpus={self._cpu}",
        ]

        if not self._network:
            cmd.append("--network=none")

        if mounts:
            for host_path, container_path in mounts:
                cmd.extend(["-v", f"{host_path}:{container_path}:ro"])

        cmd.append(self._image)
        cmd.extend(command)

        effective_timeout = timeout or self._timeout
        start = time.time()

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=effective_timeout,
            )
            duration = (time.time() - start) * 1000

            stdout = result.stdout[:50000]
            stderr = result.stderr[:20000]
            truncated = (
                len(result.stdout) > 50000 or len(result.stderr) > 20000
            )

            return SandboxResult(
                exit_code=result.returncode,
                stdout=stdout,
                stderr=stderr,
                duration_ms=duration,
                truncated=truncated,
            )

        except subprocess.TimeoutExpired:
            return SandboxResult(
                exit_code=-1,
                stdout="",
                stderr=f"Execution timed out after {effective_timeout}s",
                duration_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            return SandboxResult(
                exit_code=-1,
                stdout="",
                stderr=f"Docker execution error: {e}",
                duration_ms=(time.time() - start) * 1000,
            )


class SandboxPool:
    """
    沙箱池：管理多个预热的 Docker 容器，减少冷启动延迟

    可选功能，需要更多资源。如果不使用，直接用 DockerSandbox 即可。
    """

    def __init__(self, image: str | None = None, pool_size: int = 2):
        self._image = image or DockerSandbox.DEFAULT_IMAGE
        self._pool_size = pool_size
        self._sandboxes: list[DockerSandbox] = []

    def warm_up(self) -> None:
        """预热沙箱池"""
        if not DockerSandbox.is_available():
            logger.warning("Docker not available, skipping sandbox pool warm-up")
            return
        logger.info("Warming up %d sandboxes...", self._pool_size)
        sandbox = DockerSandbox(image=self._image)
        sandbox.ensure_image()
        for _ in range(self._pool_size):
            self._sandboxes.append(DockerSandbox(image=self._image))
        logger.info("Sandbox pool ready (%d sandboxes)", self._pool_size)

    def acquire(self) -> DockerSandbox:
        """获取一个沙箱实例"""
        if self._sandboxes:
            return self._sandboxes.pop()
        return DockerSandbox(image=self._image)

    def release(self, sandbox: DockerSandbox) -> None:
        """归还沙箱实例"""
        if len(self._sandboxes) < self._pool_size:
            self._sandboxes.append(sandbox)

    @property
    def available(self) -> int:
        return len(self._sandboxes)
