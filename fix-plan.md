# ClawHermes 评审问题验证结果与修改计划

> 基线：`review.md` 评审报告（忽略 clawhermes-qq / clawhermes-weixin 子仓问题 C9/C10/M16）
> 验证方式：逐项对照源码静态核验
> 制定日期：2026-07-16

---

## 一、问题验证结果汇总

### Critical（严重）— 9 项全部确认真实

| # | 位置 | 验证结论 | 说明 |
|:-:|:--|:-:|:--|
| C1 | `agent/delegate.py:68` | ✅ 真实 | `with self._pool as executor:` 退出时 `shutdown()` 销毁线程池，第二次调用 `delegate()` 崩溃 |
| C2 | `agent/scheduler.py:270` | ✅ 真实 | `result = self._executor(job.task, job.session_id)` 同步阻塞调用，冻结事件循环 |
| C3 | `agent/context.py:24,50-53` | ✅ 真实 | `last_prompt_tokens=0` 类变量从未写入，`0*0.75=0` 导致每轮触发压缩 |
| C4 | `tools/builtin.py:712-755` | ✅ 真实 | 12 条黑名单可被多空格/`sh -c`/`python -c` 绕过，仍用 `shell=True` |
| C5 | `tools/builtin.py:1085-1099` | ✅ 真实 | `_code_eval` 直接 `subprocess.run(["python3","-c",code])`，未走 DockerSandbox |
| C6 | `channel/pairing.py:152-178` | ✅ 真实 | `user_id` 可选参数；HMAC 用服务端 `signing_key`，客户端无法算出 response |
| C7 | `agent/loop.py:316-321` | ✅ 真实（细化） | `new_event_loop()`+`run_until_complete` 不直接抛 RuntimeError，但会阻塞外层事件循环；架构隐患成立 |
| C8 | `agent/loop.py:198` | ✅ 真实 | `asyncio.run(raw)` 在已运行事件循环中调用必抛 `RuntimeError: cannot be called from a running event loop` |
| C11 | `cli/setup.py:940` | ✅ 真实 | `import requests` 未列入 `pyproject.toml` 依赖，ImportError 被静默捕获 |

### High（高危）— 10 项全部确认真实

| # | 位置 | 验证结论 | 说明 |
|:-:|:--|:-:|:--|
| H1 | `skills/manager.py:105,122` + `agent/agent_mgr.py:53,62,96` | ✅ 真实 | `name` 直接拼路径，无 `..`/绝对路径校验；`shutil.rmtree` 可删任意目录 |
| H2 | `tools/builtin.py:689-707` | ✅ 真实 | `_read_file`/`_write_file` 无路径限制、无大小上限、`_write_file` 无 `require_confirm` |
| H3 | `tools/builtin.py:45-66` | ✅ 真实 | `_sqlite_query` 支持任意 SQL（DROP/ATTACH），`db_path` 未限制 |
| H4 | `gateway/app.py:326-344` | ✅ 真实 | `CH_GATEWAY_SECRET` 默认空→无鉴权；`CH_CORS_ORIGINS` 默认 `*`；比较用 `!=` 非恒定时间 |
| H5 | `agent/session.py:48` | ✅ 真实 | 单个 `threading.Lock` 串行化所有 SQLite 操作，O(N) 性能下降 |
| H6 | `skills/hub.py:156-159,228` | ✅ 真实 | `signature` 字段从未校验；`min_clawhermes` 未比对；无 manifest 时直接安装；`_is_git_url` 判定窄 |
| H7 | `cli/setup.py:1032-1071` | ✅ 真实 | `_write_env` 写 `.env` 后无 `chmod 0o600` |
| H8 | `channel/pairing.py:96-98,159` | ✅ 真实 | 6 位纯数字（1e6 空间）+ 5 分钟 TTL + `verify_code` 无速率限制 |
| H9 | `llm/provider.py:175-177,218-220,167,210,281` | ✅ 真实 | `retry_after=60` 硬编码；`dict(response.usage)` 在新版 litellm（Pydantic 模型）抛 TypeError |
| H10 | `channel/router.py:215-218` | ✅ 真实 | `self._queue.clear()` 清空整个共享队列，影响其他 session 排队消息 |

### Medium（中危）— 17 项确认（M15 部分修正）

| # | 位置 | 验证结论 | 说明 |
|:-:|:--|:-:|:--|
| M1 | `agent/loop.py:561-697` | ✅ 真实 | `chat_stream` 手工重写逻辑，未复用 `_build_messages`/`_should_loop_continue`/`_finalize_response`；用户/助手消息未持久化 |
| M2 | `agent/loop.py:368-369` | ✅ 真实 | `AgentConfig.max_tool_calls_per_round`/`queue_mode` 在 Agent 循环中无引用（`queue_mode` 在 router 中另有用途） |
| M3 | `agent/loop.py:217,285` | ✅ 真实 | `result if 'result' in locals() else None` 反 pattern |
| M4 | `agent/loop.py:93` | ✅ 真实 | `asyncio.get_event_loop()` Py3.12 DeprecationWarning |
| M5 | `agent/memory.py:51-52,65-80` | ✅ 真实 | 全量重写、无 `max_items`、无锁、线性搜索 |
| M6 | `agent/scheduler.py:368` | ✅ 真实 | `PENDING if status != PAUSED else PAUSED` 恒等赋值 |
| M7 | `scheduler.py:380` + `pairing.py:409` + `memory.py:52` | ✅ 真实 | 非原子写，断电得空/半写 JSON |
| M8 | `tools/builtin.py:1116-1134` | ✅ 真实 | `_http_request` 用 `curl` 子进程，与 httpx 风格不一致 |
| M9 | `tools/builtin.py:1015-1027` | ✅ 真实 | `_patch_file` 描述"差异补丁"实为 `str.replace(...,1)`，误导 LLM |
| M10 | `tools/sandbox.py:148-172` | ✅ 真实 | `docker run` 缺 `--user/--read-only/--cap-drop=ALL/--security-opt/--pids-limit`；未接入 `_code_eval`/`_exec_command` |
| M11 | `agent/exceptions.py:60` | ✅ 真实 | `class MemoryError` 覆盖内置 `MemoryError` |
| M12 | `agent/agent_mgr.py:181` | ✅ 真实 | `split("\n")[1]` 无长度判断，<2 行 IndexError |
| M13 | `llm/provider.py:233-349` | ✅ 真实（轻微） | 异常路径未显式 `aclose()` litellm 流连接，依赖 GC |
| M14 | `gateway/app.py:301-314` | ✅ 真实 | `_auto_init` 捕获所有异常仅打日志，agent=None 时非 `/health` 端点静默 5xx |
| M15 | `channel/router.py` | ⚠️ 部分修正 | 当前代码已用 `asyncio.get_running_loop()`（230/243/275 行），报告位置引用不准确；但 M4（loop.py:93）成立 |
| M17 | `skills/manager.py:43-67` | ✅ 真实 | `_load_all` 启动同步读所有 SKILL.md，无懒加载 |
| M18 | `mcp/client.py:217` | ✅ 真实 | 固定 `POST "/"` 不处理 SSE 响应流，不兼容 MCP 2025-06-18 Streamable-HTTP |

### 验证统计

- **确认真实且有效**：C1-C8、C11（9 项 Critical）+ H1-H10（10 项 High）+ M1-M14、M17、M18（16 项 Medium）= **35 项**
- **部分修正**：M15（router.py 已用现代 API，但 loop.py 同类问题成立）
- **忽略**：C9、C10（clawhermes-qq）、M16（clawhermes-weixin）

---

## 二、修改计划

### 阶段划分

- **P0 阶段（必须立即处理）**：影响可用性/正确性/安全的 Critical + High 核心项
- **P1 阶段（尽快处理）**：高危剩余项 + 影响健壮性的 Medium 项
- **P2 阶段（长期改进）**：可维护性/一致性 Medium 项 + 重构建议

---

### P0 阶段 — 必须立即处理（12 项）

#### P0-1 修复委派线程池销毁（C1）

- **责任分配**：Agent 模块负责人
- **涉及文件**：`src/clawhermes/agent/delegate.py`
- **实施步骤**：
  1. 移除 `with self._pool as executor:` 上下文管理器用法
  2. 改为 `futures = {self._pool.submit(self._run_sub_agent, task, depth, ctx): task.get("id","") for task in tasks}`
  3. 用 `as_completed(futures)` 收集结果
  4. 新增 `shutdown()` 方法，在应用关闭时集中调用 `self._pool.shutdown(wait=True)`
- **验收标准**：
  - 连续两次调用 `delegate()` 不报 `RuntimeError`
  - 新增回归测试 `test_delegate_consecutive`（连续两次委派均成功）

#### P0-2 调度器非阻塞执行（C2）

- **责任分配**：Agent 模块负责人
- **涉及文件**：`src/clawhermes/agent/scheduler.py`
- **实施步骤**：
  1. `_execute_job` 中将 `result = self._executor(...)` 改为 `result = await asyncio.to_thread(self._executor, job.task, job.session_id)`
  2. `_run_loop` 中 `for job in ready: await self._execute_job(...)` 改为 `await asyncio.gather(*[self._execute_job(j.job_id) for j in ready])` 允许并发
  3. 注意 `_executor` 当前签名是同步 `(task, session_id) -> str`，`to_thread` 包装后保持兼容
- **验收标准**：
  - 新增测试：executor 阻塞 3 秒时 `/health` 仍能即时应答
  - 多个 ready 作业可并发执行（用 mock 验证 gather 调用）

#### P0-3 修复上下文压缩判据（C3）

- **责任分配**：Agent 模块负责人
- **涉及文件**：`src/clawhermes/agent/context.py`
- **实施步骤**：
  1. 删除 `last_prompt_tokens` 类变量
  2. `ContextEngine.__init__` 增加 `max_context_tokens: int` 参数（由 `LLMProvider.max_tokens` 或配置注入）
  3. `should_compress` 改为 `return prompt_tokens > self.max_context_tokens * self.threshold_percent`
  4. `LLMCompressor.__init__` 接收并透传 `max_context_tokens`
- **验收标准**：
  - `prompt_tokens < 75% max` 时不触发压缩
  - `prompt_tokens > 75% max` 时触发压缩
  - 原 NoopCompressor 行为不变

#### P0-4 路径校验统一防护（H1 + H2 + H3）

- **责任分配**：工具模块负责人 + Skills 模块负责人
- **涉及文件**：
  - 新建 `src/clawhermes/util/scoped_path.py`
  - `src/clawhermes/skills/manager.py`
  - `src/clawhermes/agent/agent_mgr.py`
  - `src/clawhermes/tools/builtin.py`
- **实施步骤**：
  1. 新建 `ScopedPath` 类：
     ```python
     class ScopedPath:
         def __init__(self, root: Path): self.root = root.resolve()
         def resolve(self, name: str) -> Path:
             p = (self.root / name).resolve()
             if not p.is_relative_to(self.root):
                 raise ConfigValidationError(f"path escapes scope: {name}", field="path")
             return p
     ```
  2. `SkillManager.create/update/_save_meta`：技能名先 `re.fullmatch(r"[A-Za-z0-9_\-]{1,64}", name)` 校验，再用 `ScopedPath(self.skills_dir).resolve(name + ".md")`
  3. `agent_mgr.agent_path/create_agent/delete_agent/write_*`：同样校验 `name`
  4. `_read_file`/`_write_file`/`_patch_file`/`_search_replace`/`_hash_file`/`_compress_file`：增加 workspace root 校验（`Path.resolve().is_relative_to(workspace_root)`），workspace root 由配置注入
  5. `_sqlite_query`：`db_path` 限定在 data_dir 下；连接用 `sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)` 默认只读，写操作需显式 opt-in 参数
- **验收标准**：
  - 测试：技能名 `"../../.ssh/authorized_keys"` 抛 `ConfigValidationError`
  - 测试：`_read_file("/etc/shadow")` 在 workspace 外被拒
  - 测试：`_sqlite_query` 默认只读，DROP 被拒

#### P0-5 收敛 exec/code_eval 到沙箱（C4 + C5 + M10）

- **责任分配**：工具模块负责人
- **涉及文件**：`src/clawhermes/tools/builtin.py`、`src/clawhermes/tools/sandbox.py`
- **实施步骤**：
  1. `DockerSandbox._run_container` 的 `docker run` 命令追加：`--user 65534:65534 --read-only --tmpfs /tmp --cap-drop=ALL --security-opt=no-new-privileges --pids-limit=64`
  2. `_exec_command`：检测 `DockerSandbox.is_available()`，可用时走 `sandbox.run_command(command, timeout)`；不可用时回退当前 subprocess 但保留 `require_confirm`，并在日志注明"非沙箱模式"
  3. `_code_eval`：同理走 `sandbox.run_python(code, timeout)`
  4. 移除 `_EXEC_DANGEROUS_PATTERNS` 黑名单的"安全表演"语义，保留仅作审计日志，注释明确"无内建阻拦，主防线为 require_confirm + 沙箱"
  5. `standard` profile 从 `STANDARD_TOOLS` 移除 `exec`（仅 `full` 保留）
- **验收标准**：
  - Docker 可用时 `_exec_command` 通过沙箱执行
  - 沙箱内 `whoami` 返回 `nobody`，写入 `/etc/test` 失败
  - 黑名单命中时仍记录审计日志但不阻断（或保留阻断作为额外兜底，二者择一明确）

#### P0-6 DM 配对重设计（C6 + H8）

- **责任分配**：Channel 模块负责人
- **涉及文件**：`src/clawhermes/channel/pairing.py`
- **实施步骤**：
  1. `verify_code` 签名：`user_id` 改为必填（`user_id: str`，删除默认值）
  2. 挑战验证改为基于用户侧密钥对（Ed25519）：服务端存公钥，客户端用私钥签名 challenge；移除"服务端共享 HMAC"模型
  3. 新增漏桶限流：每 `user_id`/IP 10 次/分钟，超限抛 `PairingRateLimitError`
  4. 配对码长度提升到 8 位（`CODE_LENGTH = 8`，1e8 空间）或改用 base32
  5. `verify_code` 中 `user_id` 校验从可选改为强制：`if request.user_id != user_id: raise`
- **验收标准**：
  - 测试：未传 `user_id` 抛 TypeError（必填）
  - 测试：`user_id` 不匹配抛 `PairingInvalidError`
  - 测试：连续 11 次错误尝试触发限流
  - 测试：客户端用私钥签名可通过验证

#### P0-7 Gateway 认证兜底（H4）

- **责任分配**：Gateway 模块负责人
- **涉及文件**：`src/clawhermes/gateway/app.py`、`src/clawhermes/config.py`
- **实施步骤**：
  1. 启动时 fail-fast：`gateway_secret` 为空且 `host in {"0.0.0.0", "::"}` 时直接 `sys.exit(1)` 并提示配置 `CH_GATEWAY_SECRET`
  2. `_gateway_secret_middleware` 比较改用 `hmac.compare_digest(request.headers.get("X-Gateway-Secret", ""), _gateway_secret)`
  3. CORS：`allow_credentials=True` 时禁止 `allow_origins=["*"]`，启动校验互斥
  4. `config.py#check_gateway_secret` 扩展：对 `0.0.0.0`/`::` 绑定也强制
- **验收标准**：
  - 测试：`host=0.0.0.0` 且 secret 空时启动失败
  - 测试：secret 校验用恒定时间比较
  - 测试：CORS credentials+wildcard 互斥校验

#### P0-8 修复同步路径事件循环崩溃（C7 + C8）

- **责任分配**：Agent 模块负责人
- **涉及文件**：`src/clawhermes/agent/loop.py`
- **实施步骤**：
  1. `_execute_single_tool`（C8）：协程 handler 改用 `asyncio.run_coroutine_threadsafe(raw, loop)` 或检测运行中循环；最稳妥：同步 `execute()` 路径在 `asyncio.to_thread` 内调用时无运行循环，保留 `asyncio.run`；若检测到运行中循环则改用 `get_running_loop().run_until_complete` 不可行 → 改为强制走 `execute_async`
  2. `execute`（C7）：移除 `new_event_loop()`，并行工具改用 `asyncio.run(self._run_parallel())`（同步上下文安全）或文档明确"同步 execute 不得在运行中的事件循环内调用"
  3. 推荐：Gateway/FastAPI 路径强制走 `execute_async`，`chat` 同步入口确保在 `to_thread` 内
- **验收标准**：
  - 测试：在运行中的事件循环内调用同步 `execute` 抛明确异常或文档化警告
  - 测试：`asyncio.to_thread(agent.chat, ...)` 内工具协程 handler 正常执行
  - MCP async 工具在 CLI 同步路径不崩溃

#### P0-9 requests 依赖修复（C11）

- **责任分配**：CLI 模块负责人
- **涉及文件**：`src/clawhermes/cli/setup.py`、`pyproject.toml`
- **实施步骤**：
  1. 将 `setup.py:940` 的 `import requests` + `requests.post/get` 替换为 `urllib.request`（标准库，该文件其他地方已在用）或 `httpx`（已是依赖）
  2. 推荐用 `httpx`（项目已依赖）：`httpx.Client(timeout=10).post(url, json=...)`
  3. 移除误导性 `except ImportError: "requests 未安装"` 分支
- **验收标准**：
  - `clawhermes setup` 飞书事件订阅检查不再 ImportError
  - `pip install .` 后无额外依赖缺失
  - 测试：mock httpx 验证事件订阅检查逻辑

#### P0-10 INTERRUPT 只清当前 session（H10）

- **责任分配**：Channel 模块负责人
- **涉及文件**：`src/clawhermes/channel/router.py`
- **实施步骤**：
  1. `QueueMode.INTERRUPT` 分支改为：
     ```python
     self._queue = [q for q in self._queue
                    if q.message.metadata.get("chat_id", q.message.user.user_id) != chat_id]
     self._queue.insert(0, qm)
     ```
  2. 用 `chat_id` 过滤，保留其他 session 的排队消息
- **验收标准**：
  - 测试：session A 的 INTERRUPT 不影响 session B 的排队消息
  - 测试：当前 session 的排队消息被清空

#### P0-11 .env 权限修复（H7）

- **责任分配**：CLI 模块负责人
- **涉及文件**：`src/clawhermes/cli/setup.py`
- **实施步骤**：
  1. `_write_env` 末尾 `env_path.write_text(...)` 后追加 `env_path.chmod(0o600)`
  2. 对已存在的 `.env` 也补一次 chmod
- **验收标准**：
  - 测试：写入后 `env_path.stat().st_mode & 0o777 == 0o600`
  - 多用户主机上同组用户不可读

#### P0-12 LLMProvider 兼容性修复（H9）

- **责任分配**：LLM 模块负责人
- **涉及文件**：`src/clawhermes/llm/provider.py`
- **实施步骤**：
  1. 新增工具函数 `_usage_to_dict(usage)`：
     ```python
     def _usage_to_dict(usage) -> dict | None:
         if usage is None: return None
         if hasattr(usage, "model_dump"): return usage.model_dump()
         if hasattr(usage, "__dict__"): return vars(usage)
         try: return dict(usage)
         except TypeError: return None
     ```
  2. `chat`/`chat_async`/`chat_stream` 中 `dict(response.usage)` / `dict(chunk.usage)` 全部替换为 `_usage_to_dict(...)`
  3. `LLMRateLimitError` 的 `retry_after`：从 `e.response.headers.get("Retry-After")` 解析（若存在），否则默认 60
  4. 抽取 `_map_llm_exception(e, used_key)` 收敛三处重复 except 块（顺带预实现重构建议 5.4）
- **验收标准**：
  - 测试：Pydantic 模型 usage 不再抛 TypeError
  - 测试：响应头含 `Retry-After: 120` 时 `retry_after=120`
  - 测试：无 Retry-After 头时默认 60

---

### P1 阶段 — 尽快处理（11 项）

#### P1-1 chat_stream 复用共享辅助方法（M1）

- **责任分配**：Agent 模块负责人
- **涉及文件**：`src/clawhermes/agent/loop.py`
- **实施步骤**：
  1. `chat_stream` 开头调用 `self._build_messages(user_message, session_id)` 替代手工构建
  2. 循环内调用 `self._should_loop_continue(messages, iteration)` 替代手工 hook/interrupt/compress
  3. 完成分支调用 `self._finalize_response(messages, content, session_id)` 替代手工 hook/持久化
  4. 验证 stream 仍正确 yield SSE 事件
- **验收标准**：
  - 测试：`chat_stream` 完成后 `session_mgr.get_messages` 包含 user + assistant 消息
  - 测试：`AFTER_AGENT_END` hook 在 stream 中被触发
  - 行数减少，三条链路语义一致

#### P1-2 删除 dead code（M2 + M6 + M11）

- **责任分配**：Agent 模块负责人
- **涉及文件**：`src/clawhermes/agent/loop.py`、`agent/scheduler.py`、`agent/exceptions.py`、`types.py`、`skills/manager.py`
- **实施步骤**：
  1. 删除 `AgentConfig.max_tool_calls_per_round`、`AgentConfig.queue_mode`（确认无引用后）
  2. 删除 `scheduler.py:368` 恒等赋值，改为直接 `pass` 或移除分支
  3. `exceptions.py:60` `MemoryError` 改名 `ClawHermesMemoryError`，全量替换引用
  4. `Skill` 数据类在 `types.py:94` 与 `skills/manager.py:18` 二选一（保留 `skills/manager.py`，`types.py` 改 re-export）
- **验收标准**：
  - `ruff` 无未使用变量警告
  - 全量测试通过
  - `grep -r "MemoryError" src/` 仅匹配 `ClawHermesMemoryError`

#### P1-3 原子文件写（M7）

- **责任分配**：基础设施负责人
- **涉及文件**：新建 `src/clawhermes/util/atomic.py`，修改 `scheduler.py`、`pairing.py`、`memory.py`、`skills/manager.py`
- **实施步骤**：
  1. 新建 `atomic_write(path: Path, data: str | bytes)`：
     ```python
     def atomic_write(path: Path, data: str | bytes) -> None:
         tmp = path.with_suffix(path.suffix + ".tmp")
         mode = "wb" if isinstance(data, bytes) else "w"
         tmp.write_text(data, encoding="utf-8") if mode == "w" else tmp.write_bytes(data)
         os.replace(tmp, path)
     ```
  2. `scheduler._save_jobs`、`pairing._save_state`、`memory._save`、`skills._save_meta` 全部替换
- **验收标准**：
  - 测试：写入过程中模拟中断（mock os.replace 失败）原文件完整
  - 并发写不产生损坏

#### P1-4 写文件工具白名单与大小限制（H2 补充 + H3 补充）

- **责任分配**：工具模块负责人
- **涉及文件**：`src/clawhermes/tools/builtin.py`
- **实施步骤**：
  1. `_read_file`：增加大小上限（默认 1MB，超限截断并警告）
  2. `_write_file`：增加 `require_confirm=True`（覆盖写入）；大小上限（默认 10MB）
  3. `_sqlite_query`：DROP/DETACH 等危险操作需 `allow_write=True` 显式参数
- **验收标准**：
  - 测试：>1MB 文件读取被截断
  - 测试：`_write_file` 触发 confirm hook

#### P1-5 SkillHub 安全补齐（H6）

- **责任分配**：Skills 模块负责人
- **涉及文件**：`src/clawhermes/skills/hub.py`
- **实施步骤**：
  1. `verify`：增加 GPG/minisign 签名校验（若 `manifest.signature` 非空）
  2. `_install_from`：增加 `min_clawhermes` 语义化版本比对，不满足则拒绝
  3. 无 manifest 的技能默认拒绝安装（需 `allow_unverified=True` 显式 opt-in）
  4. `_is_git_url`：用 `urllib.parse.urlparse` 判定 scheme in {git, https, http} 或 `git@` 前缀
- **验收标准**：
  - 测试：签名不匹配拒绝安装
  - 测试：`min_clawhermes` 高于当前版本拒绝
  - 测试：无 manifest 默认拒绝

#### P1-6 配对码速率限制（H8 补充）

- **责任分配**：Channel 模块负责人
- **涉及文件**：`src/clawhermes/channel/pairing.py`
- **实施步骤**：见 P0-6（已合并）
- **验收标准**：见 P0-6

#### P1-7 Session 锁优化（H5）

- **责任分配**：Agent 模块负责人
- **涉及文件**：`src/clawhermes/agent/session.py`
- **实施步骤**：
  1. 读操作不加锁（SQLite WAL 已支持并发读）
  2. 写操作用 `threading.Lock` 串行化（仅写）
  3. 或改为 `asyncio.Lock` + 全异步 DB 访问（较大改动，P2 再评估）
- **验收标准**：
  - 测试：并发读不阻塞
  - 测试：并发写不损坏数据

#### P1-8 gateway _auto_init 健壮性（M14）

- **责任分配**：Gateway 模块负责人
- **涉及文件**：`src/clawhermes/gateway/app.py`
- **实施步骤**：
  1. `_auto_init` 失败后设置 `_state._init_error`，`/health` 返回 `{"status":"degraded","error":...}`
  2. 非 `/health` 端点在未初始化时返回 503 + 明确错误（非 5xx 静默）
- **验收标准**：
  - 测试：初始化失败后 `/health` 返回 degraded
  - 测试：`/chat` 在未初始化时返回 503

#### P1-9 异常处理规范化（M3 + M12）

- **责任分配**：Agent 模块负责人
- **涉及文件**：`agent/loop.py`、`agent/agent_mgr.py`
- **实施步骤**：
  1. `loop.py:217,285` `result if 'result' in locals()` 改为初始化 `result = None` 在 try 块前
  2. `agent_mgr.py:181` `split("\n")[1]` 增加长度判断：`lines = read_instructions(name).split("\n"); instr = lines[1][:40] if len(lines) > 1 else ""`
- **验收标准**：
  - 测试：单行指令文件不抛 IndexError
  - ruff/flake8 无 `locals()` 警告

#### P1-10 asyncio.get_event_loop 替换（M4 + M15）

- **责任分配**：Agent 模块负责人
- **涉及文件**：`agent/loop.py`
- **实施步骤**：
  1. `loop.py:93` `asyncio.get_event_loop()` 改为 `asyncio.get_running_loop()`（在 async 上下文）或 `asyncio.new_event_loop()`（同步上下文）
  2. 全量 grep 确认无遗漏
- **验收标准**：
  - Python 3.12 无 DeprecationWarning
  - 测试通过

#### P1-11 _http_request 改用 httpx（M8）

- **责任分配**：工具模块负责人
- **涉及文件**：`src/clawhermes/tools/builtin.py`
- **实施步骤**：
  1. `_http_request` 用 `httpx.Client` 替代 `curl` 子进程
  2. 统一超时/headers 处理
- **验收标准**：
  - 测试：无 curl 依赖
  - 测试：POST/GET 正常工作

---

### P2 阶段 — 长期改进（12 项）

#### P2-1 JSONMemoryProvider 重构（M5）

- **实施步骤**：换 SQLite 存储、加 `max_items` FIFO 淘汰、去重、加锁
- **验收标准**：并发 save 不损坏、超限自动淘汰

#### P2-2 _patch_file 语义修正（M9）

- **实施步骤**：描述改为"搜索并替换第一处匹配"或实现真正的 unified diff 解析
- **验收标准**：描述与实现一致

#### P2-3 chat_stream 连接清理（M13）

- **实施步骤**：`async finally` 中显式 `await response.aclose()`
- **验收标准**：异常路径无连接泄漏

#### P2-4 Skills 懒加载（M17）

- **实施步骤**：`_load_all` 改为按需读取（首次 `get`/`list` 时加载）
- **验收标准**：1000 技能时冷启动 <500ms

#### P2-5 MCP Streamable-HTTP 支持（M18）

- **实施步骤**：`_send_request_http` 处理 SSE 响应流（`text/event-stream`）
- **验收标准**：兼容 MCP 2025-06-18 规范

#### P2-6 DockerSandbox 默认网络禁用（M10 补充）

- **实施步骤**：`network_enabled` 默认改 `False`
- **验收标准**：沙箱内无法发起网络请求

#### P2-7 重构 agent/loop.py（重构建议 5.1）

- **实施步骤**：拆分为 `hook_manager.py`/`tool_registry.py`/`tool_dispatcher.py`/`agent.py`；统一 chat/chat_async/chat_stream 到 `_iterate` async generator
- **验收标准**：行数减少 30%+，三条链路语义一致

#### P2-8 收敛 QueueMode（重构建议 5.3）

- **实施步骤**：`types.py` 保留唯一 `QueueMode`，router.py import
- **验收标准**：无同名重复定义

#### P2-9 文档一致性自动化

- **实施步骤**：README/AGENTS/pyproject 测试数/覆盖率/版本号 CI 生成
- **验收标准**：无人工漂移

#### P2-10 ruff 规则增强

- **实施步骤**：开启 `S`（bandit）/`B006`/`ASYNC` 规则
- **验收标准**：CI 捕获 shell=True/可变默认参数/死循环同步调用

#### P2-11 pyproject.toml 版本号修正

- **实施步骤**：`version = "0.15.0"` → `"0.15.1"`（与文档基线对齐）
- **验收标准**：`pip show clawhermes` 版本为 0.15.1

#### P2-12 测试补齐（负例/变异）

- **实施步骤**：
  - `test_delegate` 加连续两次 delegate
  - `test_scheduler` 加 executor 阻塞时 /health 应答
  - `test_pairing` 加未传 user_id 拒绝
  - 新建 `test_security.py`：path traversal / SQL 注入 / CORS bypass
- **验收标准**：覆盖所有已修复 Critical/High 项的回归

---

## 三、责任分配与时间安排

| 阶段 | 责任模块 | 项数 | 建议完成节点 |
|:--|:--|:-:|:--|
| P0 | Agent 模块（C1/C2/C3/C7/C8）| 5 | 第 1-2 天 |
| P0 | 工具模块（C4/C5/H2/H3/M10）| 4 | 第 2-3 天 |
| P0 | Channel 模块（C6/H8/H10）| 3 | 第 3 天 |
| P0 | Gateway 模块（H4/M14）| 2 | 第 3 天 |
| P0 | CLI 模块（C11/H7）| 2 | 第 1 天 |
| P0 | LLM 模块（H9）| 1 | 第 2 天 |
| P0 | Skills 模块（H1）| 1 | 第 2 天 |
| P1 | 全模块协作 | 11 | 第 4-5 天 |
| P2 | 全模块协作 | 12 | 第 6 天起持续 |

---

## 四、总体验收标准

1. **P0 全部完成**：9 项 Critical + 10 项 High 全部修复，对应回归测试通过
2. **测试覆盖**：新增 `test_security.py` 覆盖 path traversal / SQL 注入 / 配对绕过 / CORS bypass
3. **静态检查**：`ruff check` + `mypy src/` 无新增错误；开启 `S`/`ASYNC` 规则
4. **动态验证**：`pytest -q` 全量通过；`clawhermes gateway start --dry-run` 冒烟成功
5. **版本对齐**：`pyproject.toml` 版本 → 0.15.2（修复发布版本）
6. **文档更新**：CHANGELOG/RELEASE/FEATURES 反映本批修复

---

## 五、风险评估

- **C6 配对重设计**涉及客户端协议变更，需与 clawhermes-lark 子仓协同，向后兼容方案需评估
- **C4/C5 沙箱接入**依赖 Docker 环境，无 Docker 时需明确降级策略
- **P2-7 loop.py 拆分**改动大，建议放在 P0/P1 验收后独立 PR
