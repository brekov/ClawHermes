"""
ClawHermes - Gateway HTTP API
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

# 加载 $CH_DATA_DIR/.env → os.environ
_env_path = Path(os.getenv("CH_DATA_DIR", os.path.expanduser("~/.clawhermes"))) / ".env"
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            _k = _k.strip()
            if _k not in os.environ:
                os.environ[_k] = _v.strip()
from clawhermes.agent.delegate import DelegateManager
from clawhermes.agent.exceptions import (
    ClawHermesError,
    LLMConnectionError,
    LLMError,
    LLMRateLimitError,
    SessionNotFoundError,
)
from clawhermes.agent.loop import Agent, AgentConfig, HookPoint, ToolRegistry
from clawhermes.agent.memory import JSONMemoryProvider, MemoryManager
from clawhermes.agent.scheduler import CronScheduler, ScheduleMode, ScheduleSpec
from clawhermes.agent.session import SessionManager
from clawhermes.channel.adapter import ChannelManager, ChannelType, RESTAdapter
from clawhermes.channel.adapters.feishu import FeishuAdapter
from clawhermes.channel.adapters.qq import QQAdapter
from clawhermes.channel.adapters.wechat import WeChatAdapter, WeComAdapter
from clawhermes.channel.config import build_adapter_config
from clawhermes.channel.pairing import DMPairingManager
from clawhermes.channel.router import ChannelRouter, SessionRouter
from clawhermes.llm.provider import LLMProvider
from clawhermes.tools.builtin import register_builtin_tools



