# ClawHermes 项目代码技术审查报告

> 审查基线：v0.15.0（`pyproject.toml`），文档标注 v0.15.1
> 审查范围：`src/clawhermes/**`、`clawhermes-{lark,qq,weixin}/**`、`tests/**`、`config/**`、`docs/**`
> 审查方式：全量静态代码 + 交叉一致性阅读，未运行动态测试

作为一个"AI 主导迭代"的项目，整体骨架完整、模块划分合理、文档量丰富，能感觉到刻意向 Hermes / OpenClaw 对齐的设计脉络。但代码层面存在一批**掩盖在 659 个"通过"用例背后的严重缺陷**——包括几个正确性/性能上会直接影响运行的 Bug、几个仅有装饰性的"安全"实现，以及 Copy-Paste 产生的架构性分裂。以下按类别列出。

---

## 1. 发现的问题

### 🔴 严重（Critical）— 会直接影响可用性/正确性

| # | 位置 | 问题 | 影响 |
|:-:|:--|:--|:--|
| C1 | `src/clawhermes/agent/delegate.py:68` | `with self._pool as executor:` 把 `ThreadPoolExecutor` 当上下文使用；退出块时 `__exit__` 会调用 `shutdown()` **销毁**成员池。第二次调用 `delegate()` 会得到 `RuntimeError: cannot schedule new futures after shutdown`。 | 子 Agent 委派仅第一次可用，之后全部报错。测试只调用一次未暴露。 |
| C2 | `src/clawhermes/agent/scheduler.py:269-271` | `_execute_job` 在 asyncio 任务里**同步调用** `self._executor(...)`（=`agent.chat`，含 LLM 阻塞 IO）。Gateway 网关整个事件循环会被单个作业阻塞几十秒到几分钟。 | Cron 触发的一刻，其他 HTTP 请求（含 `/health` 之外的所有请求）、WebSocket ping、渠道消息处理全部卡死。 |
| C3 | `src/clawhermes/agent/context.py:50-53` | `should_compress` 判据是 `prompt_tokens > self.last_prompt_tokens * threshold_percent`，而 `last_prompt_tokens` 类变量初始为 `0` 且**没有任何地方写入**。0 × 0.75 = 0，所以只要 tokens>0 就压缩 → 每轮都会触发 LLM 摘要。 | 上下文压缩逻辑事实上失效，且每轮多一次昂贵 LLM 调用；README 中"75% 触发压缩"名不副实。 |
| C4 | `src/clawhermes/tools/builtin.py:722-755` | `_exec_command` 保留 `subprocess.run(command, shell=True)`，仅靠 12 条"危险模式"黑名单挡（`"rm -rf /"` 等）。绕过极简：`rm  -rf  /`、`\rm -rf /`、`sh -c "rm -rf /"`、`python -c ...`、`/bin/rm -r --no-preserve-root /` 均可通过。 | 提供**任意 shell RCE** 且用户会误以为有兜底保护。仅一个 `require_confirm=True` 是唯一有效防线，但 confirm 钩子在默认 Agent 中并未接入 UI，实际是"必调"。 |
| C5 | `src/clawhermes/tools/builtin.py:1085-1099` | `_code_eval` 用 `subprocess.run(["python3", "-c", code])` 执行任意 Python，**未走 Docker 沙箱**（`tools/sandbox.py` 存在但未接入）。 | Python 层 RCE，读写宿主机文件系统、发起网络请求全部可行。 |
| C6 | `src/clawhermes/channel/pairing.py:172-178` | `verify_code(code, response, user_id=None)`：`user_id` 是**可选**参数，未传时不校验绑定。加之 `_compute_challenge_response = HMAC(server_secret, challenge)`——由于服务端签名密钥不外发，**任何合法客户端都无法算出正确 response**；反过来一旦有人拿到 `signing_key`，则可任意绑定成任何 `user_id`。当前流程既不可用也不安全。 | DM 配对整体设计有洞：要么根本无法用（正常客户端不知 `signing_key`），要么被完全绕过。 |
| C7 | `src/clawhermes/agent/loop.py:291-327` | `ToolDispatcher.execute` 在**同步路径**里 `asyncio.new_event_loop() → run_until_complete` 处理并行工具。若外层已在事件循环内调用（例如 FastAPI 中错误地未走 `to_thread`），会抛 `RuntimeError: This event loop is already running`。 | 潜在死锁/异常。风险随调用点扩散上升。 |
| C8 | `src/clawhermes/agent/loop.py:198` | 同步 `_execute_single_tool` 遇到协程 handler 时 `asyncio.run(raw)`。注释声称"chat() 被 asyncio.to_thread 包装"，但 CLI/直接同步调用不满足此假设，仍会崩溃。 | MCP 动态注册的工具全为 async handler，直接进入这条路径会失败。 |
| C9 | `clawhermes-qq/src/clawhermes_qq/adapter.py:612` | `logger.error("QQ send_group_message failed: %s", await resp.text()[:200])` — 对协程做切片。运行到该分支立即 `TypeError`。 | 群消息发送失败时打日志再抛异常，掩盖真实错误。 |
| C10 | `clawhermes-qq/src/clawhermes_qq/adapter.py:536-539` | `is_group = msg_type == "group" ...`，但 `msg_type` 上文是 `int(QQMsgType)`（0/2/3）。int 恒不等于 "group"，**群聊分支永远走不到**——所有群消息误发到私聊端点。 | QQ 群消息回复功能失效。 |
| C11 | `src/clawhermes/cli/setup.py:940` | `_verify_feishu_event_subscriptions` `import requests`，但 `requests` 未列入 `pyproject.toml` 依赖。 | 首次运行 setup 走到飞书事件检查会 `ImportError`（虽然内部 catch 掉，但功能悄悄失效且给出误导性 warning）。 |

### 🟠 高危（High）— 会造成安全暴露或严重维护问题

| # | 位置 | 问题 | 影响 |
|:-:|:--|:--|:--|
| H1 | `src/clawhermes/skills/manager.py:94-134` 与 `src/clawhermes/agent/agent_mgr.py:60-96` | `name` 直接拼路径（`self.skills_dir / f"{name}.md"`、`get_agents_dir() / name`），未做 `..`/绝对路径/分隔符校验。LLM 若被诱导生成技能名 `"../../.ssh/authorized_keys"`，Background Review 就会写任意文件。 | Path Traversal → 任意文件写。委派后端更是把 skill/create/更新暴露给 LLM 直接调用。 |
| H2 | `src/clawhermes/tools/builtin.py:689-707` | `_read_file` / `_write_file` 无路径限制、无大小上限、`_write_file` 无 `require_confirm`。 | LLM 可读 `/etc/shadow`（若进程有权限）、覆盖 `~/.bashrc`、耗尽磁盘。 |
| H3 | `src/clawhermes/tools/builtin.py:45-66` | `_sqlite_query` 支持任意 SQL（含 `DROP`, `DETACH`, `ATTACH DATABASE ...`），未限制 `db_path`。 | 一条工具调用就能挂载并覆写宿主机上任意 SQLite（含 Gateway 自身 `sessions.db`）。 |
| H4 | `src/clawhermes/gateway/app.py:326` | `CH_CORS_ORIGINS` 默认 `*` + `CH_GATEWAY_SECRET` 空时无认证。若管理员按文档 `docker run -p 18789:18789 clawhermes` 起服务，暴露到公网就是无鉴权 RCE 网关（因为 `/chat` → Agent → `exec` 工具）。 | 严重可导致主机被攻陷。`config.py#check_gateway_secret` 只在 `gateway_host!=127.0.0.1` 时强制；Docker 里默认监听 `0.0.0.0`，但 host 配置走 env/args 传入，绑定 `--host 0.0.0.0` 时校验并不生效于 middleware。 |
| H5 | `src/clawhermes/agent/session.py:44-57` | 所有 SQLite 操作串行到单个 `threading.Lock`；单条消息 add 会拿全表锁，随并发 chat 数目 O(N) 性能下降。 | 高并发下明显串行化，但不至于错。 |
| H6 | `src/clawhermes/skills/hub.py:156-159` | 文档写"SHA-256 校验 + GPG 签名"，实现只有 SHA-256；`SkillManifest.signature` 字段存在但从未校验；`min_clawhermes` 版本比对也没做；`_is_git_url` 因运算符优先级 (`or` 与 `and`) 判定不精准。 | 联邦技能安装等同"信任任何 Git 仓库"。 |
| H7 | `src/clawhermes/cli/setup.py:1032-1071` | `_write_env` 写 `.env` 明文 API Key，不做 `chmod 600`。 | 多用户主机上 API Key 泄露给同组用户/其他容器。 |
| H8 | `src/clawhermes/channel/pairing.py:132` | 6 位纯数字配对码（1e6 空间）+ 5 分钟 TTL，`verify_code` 无速率限制。 | 暴力枚举（10^6 次调用 → 300s 有效期）可行，尤其 pairing 关键。 |
| H9 | `src/clawhermes/llm/provider.py:172-189` | `LLMRateLimitError(retry_after=60)` 硬编码，不解析响应头 `Retry-After`；`dict(response.usage)` 假设 usage 是 mapping，litellm 新版 usage 是 Pydantic 模型 → 抛 `TypeError`。 | 超限 backoff 不遵守服务端指示，且高版本 litellm 直接崩。 |
| H10 | `src/clawhermes/channel/router.py:215-218` | INTERRUPT 模式做 `self._queue.clear(); self._queue.insert(0, qm)`——**清空整个共享队列**，包括其他 session 的排队消息。 | 一个恶意/不小心的 interrupt 影响所有用户。 |

### 🟡 中危（Medium）— 影响健壮性 / 可维护性

| # | 位置 | 问题 |
|:-:|:--|:--|
| M1 | `src/clawhermes/agent/loop.py:561-697` | `chat_stream` 手工重写了 `_build_messages`/`_should_loop_continue`/`_finalize_response` 的等价逻辑（chat/chat_async 都用了辅助方法，就 stream 没用）。用户消息与助手消息**没有持久化**、`AFTER_AGENT_END` 里 background_review 拿不到会话。 |
| M2 | `src/clawhermes/agent/loop.py:367-369` | `AgentConfig.max_tool_calls_per_round` / `queue_mode` 定义但整个代码库无引用，属死代码。 |
| M3 | `src/clawhermes/agent/loop.py:217, 285` | `tool_result=result if 'result' in locals() else None` 使用 `locals()` 判定是否赋值——反 pattern，异常路径下把 `None` 传给 after hook。 |
| M4 | `src/clawhermes/agent/loop.py:88-96` | `trigger_sync_with_async` 使用 `asyncio.get_event_loop()`（Py 3.12 已 DeprecationWarning，未来会 raise）。 |
| M5 | `src/clawhermes/agent/memory.py:34-96` | `JSONMemoryProvider` 每次 `save` 全量重写文件；无 `max_items` 上限（`MemoryConf.max_items=1000` 未接入）；线性 `search`；无锁——并发 save 数据丢失/损坏。 |
| M6 | `src/clawhermes/agent/scheduler.py:367-371` | `job.status = JobStatus.PENDING if job.status != JobStatus.PAUSED else JobStatus.PAUSED` 恒等赋值，死代码。 |
| M7 | `src/clawhermes/agent/scheduler.py:377-385` | `_save_jobs` 非原子写（直接 `write_text`），断电/进程被杀会得到空/半写 JSON。同样问题也存在于 `channel/pairing.py:390-411` 和 `agent/memory.py:51`。 |
| M8 | `src/clawhermes/tools/builtin.py:1116-1134` | `_http_request` 用 `curl` 子进程（其他工具已经全部改成 httpx），前后风格不一致 + 依赖系统 curl。 |
| M9 | `src/clawhermes/tools/builtin.py:1023` | `_patch_file` 描述 "差异补丁"，实现只是 `str.replace(...,1)`——第一次匹配替换，语义误导 LLM。 |
| M10 | `src/clawhermes/tools/sandbox.py:148-172` | `docker run` 未加 `--user nobody`、`--read-only`、`--cap-drop=ALL`、`--security-opt=no-new-privileges`、`--pids-limit`。名义"沙箱"实际隔离度接近裸容器；且**未接入到 `_code_eval` / `_exec_command`**（见 C5）。 |
| M11 | `src/clawhermes/agent/exceptions.py:60` | 自定义 `MemoryError` **覆盖了 Python 内置 `MemoryError`**。之后 `except MemoryError:` 语义歧义（尤其被 `from clawhermes.agent.exceptions import *` 时）。 |
| M12 | `src/clawhermes/agent/agent_mgr.py:181` | `read_instructions(name).split("\n")[1]` 无长度判断，指令文件 <2 行时 `IndexError`。 |
| M13 | `src/clawhermes/llm/provider.py:233-349` | `chat_stream` `AsyncGenerator` 生命周期结束时不 `close()` litellm 底层连接（依赖 GC）；错误路径与正常路径混合 `yield`——静态分析器容易漏检。 |
| M14 | `src/clawhermes/gateway/app.py:302-314` | `_auto_init` 只捕获 `Exception` 打日志，随后 Gateway 继续运行但 agent=None，所有非 `/health` 端点静默 5xx。缺"未初始化"探针。 |
| M15 | `src/clawhermes/channel/router.py:189` | `RESTAdapter.handle_request` 内 `asyncio.get_event_loop()` 亦为过时 API。 |
| M16 | `clawhermes-weixin/src/clawhermes_weixin/adapter.py:175` | 访问 `self._client._session_key` 私有成员；且每次 poll/send 都 `async with aiohttp.ClientSession()` 新建 session（性能浪费）。 |
| M17 | `src/clawhermes/skills/manager.py:46-67` | `_load_all` 启动时同步读所有 SKILL.md，无懒加载。技能库大到 1k+ 时 CLI 冷启动明显。 |
| M18 | `src/clawhermes/mcp/client.py:217` | HTTP 传输固定 `POST "/"`，不兼容 MCP `2025-06-18` Streamable-HTTP 规范（走 `POST /`，但需处理 SSE 响应流）。 |

### 🟢 轻度（Low）— 风格/一致性/文档

- Ruff 已忽略 `E501` 但强调"line-length 100"——两处冲突设置（`pyproject.toml:48-53`）。
- `README.md` 声称"659 passed / 覆盖率 73%"，`pyproject.toml` 却没写覆盖率强制门；`AGENTS.md` 又说 `--cov-fail-under=60`；三处数字不一致。
- 大部分 `_web_search_*` 分支未在 `web_search` 说明中体现，只有 README 稍带过。
- `docs/architecture.md:642-646` 描述 "channel/adapters/feishu.py 已迁移至子仓库"，但 `gateway/app.py` 里对子模块的 `import` 是 `from clawhermes.channel.adapters.feishu import FeishuAdapter`（形状是主仓路径），未确认是否是 shim。
- `Skill` 数据类在 `types.py:94` 与 `skills/manager.py:18` 同名重复定义，字段类型（`last_used: datetime` vs `float`）不一致——迟早踩坑。
- 大量 handler 用裸 `except Exception: return {"error": ...}`，把 ClawHermesError 语义打平，工具错误分类信息丢失。
- 命名基本符合 PEP 8；但 `channel/router.QueueMode` 与 `types.QueueMode` 是两个独立枚举——**同名重复**易搞混。
- 中英文混排/dead code 注释较多（例如 `tools/sandbox.py:112` 后 raise 但无 `from e` 打断异常链）。

---

## 2. 改进建议（按优先级）

### P0 — 必须马上处理

1. **修复委派池销毁**（C1）：将 `delegate.py` 改为
   ```python
   futures = {self._pool.submit(...): tid for ...}
   for fut in as_completed(futures): ...
   ```
   且不用上下文管理器；在应用关闭时集中 `shutdown(wait=True)`。
2. **调度器非阻塞执行**（C2）：`_execute_job` 里
   ```python
   result = await asyncio.to_thread(self._executor, job.task, job.session_id)
   ```
   并把 `for job in ready: await self._execute_job(...)` 改成 `asyncio.gather(*[…])` 以允许并发。
3. **修复上下文压缩判据**（C3）：删除 `last_prompt_tokens` 相对判据，改用**模型上下文窗口的绝对阈值**：
   ```python
   def should_compress(self, prompt_tokens): return prompt_tokens > self.max_context_tokens * self.threshold_percent
   ```
   由 `LLMProvider.max_tokens` 或配置注入 `max_context_tokens`。
4. **正确路径校验**（H1）：技能名、Agent 名统一走
   ```python
   safe = re.fullmatch(r"[A-Za-z0-9_\-]{1,64}", name)
   ```
   否则抛 `ConfigValidationError`。文件写入前再 `assert path.parent.resolve() == expected_dir.resolve()`。
5. **收敛 `_exec_command` / `_code_eval` 到 Docker 沙箱**（C4、C5、M10）：
   - `standard` profile 移除 `exec`；
   - `full` profile 下这两工具强制走 `DockerSandbox.run_command/run_python`；
   - 沙箱 `docker run` 加：`--user 65534:65534 --read-only --tmpfs /tmp --cap-drop=ALL --security-opt=no-new-privileges --pids-limit=64`；
   - 移除黑名单"安全表演"，改说明"仅审计日志，无内建阻拦"。
6. **QQ 群消息发送逻辑修复**（C9、C10）：
   ```python
   is_group = original.metadata.get("msg_type") == "group"
   endpoint = "/v2/groups/…" if is_group else "/v2/users/…"
   ```
   `_send_group_message` 里 `await resp.text()` 括起来再切片；补一条 pytest 覆盖群聊回复分支。
7. **DM 配对重设计**（C6、H8）：
   - `verify_code` 中 `user_id` 改为必填；
   - 挑战验证改成**基于用户侧公钥**（Ed25519 签名）而非共享 HMAC，服务端仅存公钥；
   - `verify_code` 每 IP/user 加漏桶限流（e.g. `10/min`）。
8. **Gateway 认证兜底**（H4）：`gateway_secret` 缺失且 `host in {"0.0.0.0", "::"}` 时启动直接 fail-fast；`_gateway_secret_middleware` 用 `hmac.compare_digest`；CORS `allow_origins` 与 `allow_credentials` 明确联动校验。

### P1 — 尽快处理

9. **`chat_stream` 复用共享辅助方法**（M1）：抽出 `_run_stream_iteration` 与 `chat`/`chat_async` 三处循环共用；stream 完成时补上 `session_mgr.add_message(...)` 与 `AFTER_AGENT_END`。
10. **删掉 dead code**（M2、M6、M11、`identify_sent` 变量 in QQ）：`AgentConfig.max_tool_calls_per_round`、`AgentConfig.queue_mode`、`_load_jobs` 冗余分支、`MemoryError` 改名 `ClawHermesMemoryError`、`Skill` 数据类去重（`types.py` 或 `skills/manager.py` 保留其一）。
11. **原子文件写**（M7）：统一封装
    ```python
    def atomic_write(path, data):
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data); os.replace(tmp, path)
    ```
    scheduler / memory / pairing / skills 全部替换。
12. **LLMProvider 兼容 litellm 新版**（H9）：
    ```python
    usage = response.usage.model_dump() if hasattr(response.usage, "model_dump") else dict(response.usage)
    ```
    RateLimitError 从 headers 提 `Retry-After`。
13. **INTERRUPT 只清当前 session 队列**（H10）：
    ```python
    self._queue = [q for q in self._queue if q.message.metadata.get("chat_id") != chat_id]
    ```
14. **写文件工具白名单**（H2、H3）：`_write_file` / `_read_file` / `_sqlite_query` 增加 workspace root 校验：`Path.resolve().is_relative_to(workspace_root)`；`_sqlite_query` 走 `sqlite3.connect("file:{db}?mode=ro", uri=True)` 默认只读，写操作需显式 opt-in。
15. **`.env` 权限**（H7）：`env_path.chmod(0o600)` 写完立即 chmod。
16. **`requests` 依赖或替换**（C11）：把 `setup.py:940` 改用 `urllib.request`（该文件其他地方已在用）；或把 `requests` 加进 `[project.dependencies]`。

### P2 — 长期改进

17. `asyncio.get_event_loop()` 全量替换为 `get_running_loop()`（M4、M15）；`Ruff` 加 `UP` (pyupgrade) 规则可自动化。
18. `JSONMemoryProvider` 换成 SQLite（本项目已依赖 sqlite3）、加 `max_items` FIFO 淘汰、去重（同 content+scope）。
19. `SkillHub` 补 GPG/minisign 校验 + `min_clawhermes` 语义化版本比对；`_is_git_url` 用 `urllib.parse` 判定 scheme 而不是字符串包含。
20. `AGENTS.md`、`README.md`、`pyproject.toml` 中的测试数目/覆盖率/版本号做 CI 生成，避免继续漂移。

---

## 3. 整体代码质量评分

| 维度 | 分数 (/10) | 说明 |
|:--|:-:|:--|
| 架构设计 | 7 | 分层清晰、`gateway → agent → channel/llm/tools/skills` 依赖图无循环。但 `agent/loop.py` 承担了 Agent + Hook + Dispatcher 三种职责，体量偏大；`chat / chat_async / chat_stream` 未共享 iteration；跨模块 QueueMode/Skill 重复定义拉低了 -1 分。 |
| 代码实现质量 | 5 | 有 C1/C2/C3/C6/C10 五个"运行时明确 Bug"、多个 `is_group=`、`await resp.text()[:200]` 之类明显失误未被测试覆盖。 |
| 命名与风格 | 8 | 整体符合 PEP 8/项目自身 ruff 配置，中文注释密度合理；`_calc` 白名单类保护得当。 |
| 文档/示例一致性 | 6 | 架构文档非常详细，但代码没实现的东西（GPG 签名、"75% 触发压缩"、"blacklist 兜底"）都当"已完成"写在了 README。 |
| Docstring 完整性 | 6 | 类/方法头部注释多为中文，多数覆盖到"是什么"、缺"边界条件/失败模式"（例如 pairing 的 `verify_code` 对 `user_id=None` 的语义就没描述）。 |
| 性能/资源使用 | 5 | Scheduler 阻塞 loop、Memory 全量重写、`aiohttp.ClientSession` 反复创建、Session 全表锁。 |
| 安全性 | 4 | AST 求值器和 `_web_fetch/_grep` 用纯 Python 做得漂亮，但 `_exec_command`/`_code_eval` 完全放开，写入类工具没有沙箱边界，Gateway 默认无鉴权 + 默认 `*` CORS，Pairing 设计有洞。 |
| 测试覆盖与质量 | 6 | 700+ 测试，主链路覆盖不错，但对**已发现 Bug 全部漏检**——说明测试倾向"验证 happy path"，缺**变异测试/负例**。 |
| 可维护性/扩展性 | 7 | ChannelAdapter ABC、ToolRegistry、MemoryProvider 接口清晰，扩展新渠道/工具/记忆源门槛低；MCP registry 良好；但 `gateway/app.py` 里 initialize 大函数与 `_state` 全局单例限制了多实例场景。 |
| **总体加权分** | **5.8 / 10** | 骨架优秀 → 若把 P0 列表清空，能上到 8 分档；当前状态更接近"演示可用，生产不宜"。 |

---

## 4. 关键风险点提醒（对运营部署方）

1. **不要按 README/Docker 例子直接对公网暴露** —— 默认无鉴权 + `exec`/`code_eval` 工具在 `standard`/`full` profile 中开放。
2. **不要启用 Cron 调度并同时依赖 SSE/长连接** —— scheduler 目前会**周期性冻结事件循环**（C2 未修复前）。
3. **不要把 pairing_state.json 视为已上线的可信安全模型**（C6）；如果需要 DM 配对，请先关闭 `pairing_required=True` 或用应用层 API 网关做 IP allowlist。
4. **背景审查可能写到任意路径**（H1）：LLM 生成技能名不可信，暂时禁用 `BackgroundReview` 或收窄技能目录到 chroot 只读挂载。
5. **`config/.env` 泄露风险**（H7）：多租户宿主机务必手动 `chmod 600 ~/.clawhermes/.env`。
6. **`agent.chat` 是同步阻塞** —— 任何直接在 asyncio 上下文里同步调用它（例如 tests 或 REST 路径外的 handler）都会阻塞整个 event loop。

---

## 5. 重构建议

### 5.1 拆分 `agent/loop.py`（当前 704 行）

按职责拆四文件：
- `agent/hook_manager.py` — `HookPoint` + `HookManager`
- `agent/tool_registry.py` — `ToolDef` + `ToolRegistry`
- `agent/tool_dispatcher.py` — `ToolDispatcher`（合并 sync/async 执行，去掉 `new_event_loop`）
- `agent/agent.py` — `Agent` + `AgentConfig`，`chat/chat_async/chat_stream` 复用抽象出的 `AgentIteration` 协作对象

同时统一 `chat`/`chat_async`/`chat_stream` 到一个私有 async generator：
```python
async def _iterate(self, user_message, session_id):
    yield ("messages", messages)
    for iteration in range(...):
        yield ("model_call_started", None)
        resp = await self.llm.chat_async(...)
        yield ("assistant_msg", resp)
        if not resp.tool_calls: return
        results = await self.dispatcher.execute_async(...)
        yield ("tool_results", results)
```
- `chat_async` 消费到结束返回字符串；
- `chat_stream` 消费同一 generator 时同步 yield SSE event；
- `chat` = `asyncio.run(chat_async(...))`。

结果：**行数减少 30%+，三条链路语义强一致**（自然修掉 M1 与部分 C7/C8）。

### 5.2 引入统一的 Filesystem-scope 类

新建 `clawhermes/util/scoped_path.py`：
```python
class ScopedPath:
    def __init__(self, root: Path): self.root = root.resolve()
    def resolve(self, name: str) -> Path:
        p = (self.root / name).resolve()
        if not p.is_relative_to(self.root):
            raise ConfigValidationError(f"path escapes scope: {name}", field="path")
        return p
```
应用到 `SkillManager`、`agent_mgr`、`_read_file`、`_write_file`、`_patch_file`、`_search_replace`、`_hash_file`、`_compress_file`。一次改动堵掉多个 CWE-22。

### 5.3 收敛 QueueMode

`clawhermes/types.py` 保留唯一 `QueueMode`；`channel/router.py` 直接 `from clawhermes.types import QueueMode`（M11 顺带 `MemoryError` 一起改名）。

### 5.4 提取 `LLMProvider` 的错误映射

把 `chat/chat_async/chat_stream` 里重复的 `except litellm.RateLimitError/AuthError/…` 抽成 `_map_exception(e, used_key)`，减少 3 份复制粘贴（约 90 行）。

---

## 6. 最佳实践推荐

- **fail-fast 配置校验做完整**：`ClawHermesConfig` 已很好，进一步把 `tools.profile` 与 `agent.max_iterations` 也放进校验（当前只在 CLI 拒 0）。
- **`Any` 逐步替换**：`gateway/app.py` 里 `feishu_adapter: Any` 之类，换成 `TYPE_CHECKING` 下的字符串前向引用，mypy 就能给出真实提示。
- **测试组织补齐**：
  - `test_scheduler.py` 加"executor 阻塞 5 秒时 `/health` 仍能应答"用例（会立即暴露 C2）；
  - `test_delegate` 增加**连续两次 `delegate`** 用例（会立即暴露 C1）；
  - `test_pairing.py` 加"未传 user_id 是否拒绝"（会暴露 C6）；
  - 加 `test_security.py` 集中攻击面：path traversal、SQL 注入、CORS/secret bypass。
- **CI 增补 `pip install .`+`clawhermes gateway start --dry-run` 冒烟**，防止像 `import requests` 这种缺依赖再次上主分支。
- **`ruff`**：开启 `S`（bandit 规则集），会自动捕获 `shell=True`、`hashlib.md5(usedforsecurity=False)` 等；`B006` 帮抓 mutable default；`ASYNC` 抓死循环里的同步调用（会指到 C2）。
- **`pytest-cov` 硬门**：`--cov-fail-under=70`，且分模块最低值（例如 `tools/` 允许低到 50，但 `agent/loop.py` 要求 ≥ 85）——目前把总覆盖率作为唯一指标掩盖了核心逻辑覆盖不足。
- **依赖清单来源单一**：`pyproject.toml` 是唯一 source of truth；`.egg-info/requires.txt` 应从 build 目录移除（当前项目根污染）。
- **文档与实现一致的自动化**：`docs/architecture.md` 与 `README.md` 中提到的功能，用 mkdocs macros 或 `pytest --collect-only` + doctest 交叉检查。

---

**总结**：ClawHermes 的**模块骨架、接口抽象、文档意识**已达到相当水准，作为"AI 驱动开发"的中期产物非常可观；但代码里能找到**多处只在 happy path 下运行正常、真实并发或异常路径下失效的 Bug**，同时"看起来安全"的实现（危险命令黑名单、6 位配对码、shared HMAC 挑战）实际带来虚假的安全感。**先补齐 P0 列表 → 补上负例测试 → 再谈生产化**。当前评级 **5.8 / 10**（骨架 8 分，实现质量与安全拉低 2 分）。
