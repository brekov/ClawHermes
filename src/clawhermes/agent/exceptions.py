"""
ClawHermes - 自定义异常类层次（向后兼容 shim）
依赖倒置（A1）：异常类已迁移至 clawhermes.common.exceptions（底层共享包）。
本模块仅做 re-export，保持现有 `from clawhermes.agent.exceptions import ...` 不变。
新代码应直接 from clawhermes.common.exceptions import ...
"""
from __future__ import annotations

from clawhermes.common.exceptions import *  # noqa: F401,F403
