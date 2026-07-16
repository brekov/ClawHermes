"""原子文件写入工具 — 先写 tmp 再 os.replace，避免半写状态。"""
from __future__ import annotations

import os
from pathlib import Path


def atomic_write(path: Path | str, data: str | bytes, encoding: str = "utf-8") -> None:
    """原子写入文件：先写 tmp，再 os.replace。"""
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    if isinstance(data, bytes):
        tmp.write_bytes(data)
    else:
        tmp.write_text(data, encoding=encoding)
    os.replace(tmp, path)
