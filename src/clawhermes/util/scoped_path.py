"""
ClawHermes - 作用域路径校验器

确保用户/LLM 可控的名称拼接到 root 目录后不会逃逸。
用于所有接受外部 name 参数的文件路径操作（技能、Agent 等）。
"""
from __future__ import annotations

import re
from pathlib import Path

from clawhermes.agent.exceptions import ConfigValidationError


class ScopedPath:
    """
    作用域路径校验器：确保拼接后的路径不逃逸指定 root 目录。
    用于所有用户/LLM 可控的文件路径参数。
    """

    # 安全名称正则：字母、数字、下划线、连字符，1-64 字符
    NAME_PATTERN = re.compile(r"[A-Za-z0-9_\-]{1,64}")

    def __init__(self, root: Path | str):
        self.root = Path(root).resolve()

    def validate_name(self, name: str) -> str:
        """校验名称是否仅含安全字符"""
        if not name or not self.NAME_PATTERN.fullmatch(name):
            raise ConfigValidationError(
                f"无效的名称: {name!r}，仅允许字母、数字、下划线、连字符（1-64字符）",
                field="name",
            )
        return name

    def resolve(self, name: str, suffix: str = "") -> Path:
        """
        校验名称并拼接路径，确保结果在 root 内。
        :param name: 相对名称（已通过 validate_name）
        :param suffix: 可选后缀（如 .md）
        :return: 校验后的绝对路径
        :raises ConfigValidationError: 路径逃逸或名称非法
        """
        self.validate_name(name)
        target = (self.root / f"{name}{suffix}").resolve()
        if not target.is_relative_to(self.root):
            raise ConfigValidationError(
                f"路径逃逸: {name} -> {target} 不在 {self.root} 内",
                field="path",
            )
        return target
