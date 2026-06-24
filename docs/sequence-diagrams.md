# ClawHermes · 时序图与流程图

> 版本：v0.15.0 Draft（待 Phase 3 Streaming 实现后更新渠道流程）
> 日期：2026-06-16

---

## 1. 对话主流程（Agent Loop）

```
用户                  Gateway                Agent                 LLM              工具
 │                       │                     │                    │                │
 │  POST /chat           │                     │                    │                │
 │──────────────────────▶│                     │                    │                │
 │                       │  chat(msg)          │                    │                │
 │                       │────────────────────▶│                    │                │
 │                       │                     │                    │                │
 │                       │                     │  System Prompt 组装 │                │
 │                       │                     │────────────────────▶                │
 │                       │                     │                    │                │
 │                       │                     │  chat.completion() │                │
 │                       │                     │───────────────────▶│                │
 │                       │                     │                    │                │
 │                       │                     │  ◀──── tool_calls ─┤                │
 │                       │                     │                    │                │
 │                       │                     │  ┌─ 有工具调用？    │                │
 │                       │                     │  │                 │                │
 │                       │                     │  ├─是 → 调度工具    │                │
 │                       │                     │  │    │                         │
 │                       │                     │  │  before_tool_call 钩子       │
 │                       │                     │  │    │                         │
 │                       │                     │  │    ├─ blocked? → 返回错误    │
 │                       │                     │  │    ├─ override? → 改写参数    │
 │                       │                     │  │    │                         │
 │                       │                     │  │  执行工具 ──────────────────▶│
 │                       │                     │  │    │                         │
 │                       │                     │  │  after_tool_call 钩子        │
 │                       │                     │  │    │                         │
 │                       │                     │  │  结果合并回 messages          │
 │                       │                     │  │    │                         │
 │                       │                     │  │  ◀─── 回到 LLM 调用 ─────────│
 │                       │                     │  │                              │
 │                       │                     │  └─否 → ◀─── 最终回复 ──        │
 │                       │                     │                    │           │
 │                       │                     │  before_agent_reply 钩子         │
 │                       │                     │                    │           │
 │                       │                     │  after_agent_end 钩子           │
 │                       │                     │    → Background Review (异步)   │
 │                       │                     │                    │           │
 │                       │  ◀──── 响应 ───────┤                    │           │
 │  ◀────────────────────┤                     │                    │           │
 │                       │                     │                    │           │
```

## 2. Background Review 时序

```
Agent 主循环               BackgroundReview          MemoryManager        SkillManager
     │                           │                       │                    │
     │  after_agent_end 触发     │                       │                    │
     │ ─────────────────────────▶│                       │                    │
     │                           │                       │                    │
     │                           │  review(conversation) │                    │
     │                           │  └─ LLM 审查对话      │                    │
     │                           │       │               │                    │
     │                           │  ◀── 返回 {memories, skills}               │
     │                           │       │               │                    │
     │                           │  apply()              │                    │
     │                           │  ┌─ for each memory   │                    │
     │                           │  │  save(content) ───▶│                    │
     │                           │  │                    │                    │
     │                           │  └─ for each skill    │                    │
     │                           │     create/update ───────────────────────▶│
     │                           │                       │                    │
```

## 3. 上下文压缩流程（F10）

```
Agent 循环               ContextEngine              LLM (压缩)
     │                        │                        │
     │ 消息累积超过阈值(75%)   │                        │
     │ ──────────────────────▶│                        │
     │                        │                        │
     │                        │  should_compress()     │
     │                        │  └─ tokens > threshold │
     │                        │                        │
     │                        │  compress(messages)    │
     │                        │  └─ 保护前3条+后6条    │
     │                        │     │                  │
     │                        │     ├─ 中间部分 → LLM 摘要
     │                        │     │    │             │
     │                        │     │  ◀── summary ────│
     │                        │     │                  │
     │                        │     └─ 重组 messages:  │
     │                        │        保护头 + 摘要 + 保护尾
     │                        │                        │
     │  ◀── 压缩后messages ───┤                        │
     │                        │                        │
```

## 4. 子Agent委派流程（F12）

```
主Agent                     DelegateManager              子Agent
   │                              │                         │
   │ delegate_task(tasks)         │                         │
   │ ────────────────────────────▶│                         │
   │                              │                         │
   │                              │  深度检查               │
   │                              │  ┌─ depth > MAX? → 拒绝 │
   │                              │  └─ depth ok            │
   │                              │                         │
   │                              │  创建子Agent             │
   │                              │  └─ 继承父Agent的配置    │
   │                              │    但禁用：              │
   │                              │    · delegate_task       │
   │                              │    · clarify             │
   │                              │    · memory              │
   │                              │    · send_message        │
   │                              │                         │
   │                              │  子Agent.chat(task) ───▶│
   │                              │                         │
   │                              │  ◀──── 结果 ────────────│
   │                              │                         │
   │  ◀──── 汇总结果 ────────────┤                         │
   │                              │                         │
```

## 5. 记忆系统数据流

```
Agent 对话               MemoryManager      JSONProvider    ChromaProvider
     │                       │                  │               │
     │  save(content)        │                  │               │
     │ ─────────────────────▶│                  │               │
     │                       │                  │               │
     │                       │  save(item) ────▶│               │
     │                       │  save(item) ────────────────────▶│
     │                       │                  │               │
     │                       │                  │               │
     │  search(query)        │                  │               │
     │ ─────────────────────▶│                  │               │
     │                       │                  │               │
     │                       │  search(query) ─▶│               │
     │                       │  search(query) ────────────────▶│
     │                       │                  │               │
     │                       │  ◀── 合并结果 ───┤               │
     │  ◀── 排序取topN ──────┤                  │               │
     │                       │                  │               │
```
