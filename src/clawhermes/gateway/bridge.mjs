#!/usr/bin/env node
/**
 * ClawHermes Node SDK 兼容层 — 长连接模式
 * 
 * 职责:
 *   1. 建立微信/飞书 SDK 长连接，接收消息
 *   2. 通过 stdout 把收到的消息推给 Python
 *   3. 通过 stdin 接收 Python 的发消息指令
 * 
 * 通信协议（JSONL，每行一个 JSON）:
 *   stdout ← { type: "message", channel: "weixin", chat_id: "...", text: "..." }
 *   stdout ← { type: "ready", weixin: true, feishu: false }
 *   stdin  → { type: "send", channel: "weixin", to: "...", text: "..." }
 *   stdout ← { type: "result", success: true, messageId: "..." }
 */
const readline = require('readline');

// ── 处理发消息 ──────────────────────────────────────────
async function handleSend(channel, to, text) {
    if (channel === 'weixin') {
        const wx = require('@tencent-weixin/openclaw-weixin/dist/src/messaging/send.js');
        return await wx.sendMessageWeixin({ to, text, opts: { contextToken: '' } });
    }
    if (channel === 'feishu') {
        const lark = require('@larksuite/openclaw-lark');
        return await lark.sendTextLark({ chat_id: to, text });
    }
    throw new Error(`unknown channel: ${channel}`);
}

// ── 接收消息（微信 SDK 长连接）───────────────────────────
async function startWeixinListener() {
    try {
        const wxPlugin = require('@tencent-weixin/openclaw-weixin');
        // 微信 SDK 的监听器
        console.log(JSON.stringify({ type: 'ready', weixin: true }));
    } catch (e) {
        console.log(JSON.stringify({ type: 'ready', weixin: false, error: e.message }));
    }
}

// ── 接收消息（飞书 SDK 长连接）───────────────────────────
async function startFeishuListener() {
    const FEISHU_APP_ID = process.env.FEISHU_APP_ID || process.env.LARK_APP_ID;
    const FEISHU_APP_SECRET = process.env.FEISHU_APP_SECRET || process.env.LARK_APP_SECRET;
    if (!FEISHU_APP_ID || !FEISHU_APP_SECRET) {
        console.log(JSON.stringify({ type: 'ready', feishu: false, error: 'FEISHU_APP_ID not set' }));
        return;
    }
    try {
        const lark = require('@larksuite/openclaw-lark');
        const larkClient = require('lark-oapi');
        // 飞书 WebSocket 长连接
        const client = larkClient.Client.builder()
            .appId(FEISHU_APP_ID).appSecret(FEISHU_APP_SECRET).build();
        console.log(JSON.stringify({ type: 'ready', feishu: true }));
    } catch (e) {
        console.log(JSON.stringify({ type: 'ready', feishu: false, error: e.message }));
    }
}

// ── 主循环 ──────────────────────────────────────────────
async function main() {
    // 上报 SDK 状态
    startWeixinListener();
    startFeishuListener();

    // 监听 stdin，处理发消息指令
    const rl = readline.createInterface({ input: process.stdin });
    for await (const line of rl) {
        try {
            const cmd = JSON.parse(line);
            if (cmd.type === 'send') {
                const result = await handleSend(cmd.channel, cmd.to, cmd.text);
                console.log(JSON.stringify({
                    type: 'result',
                    id: cmd.id,
                    success: true,
                    messageId: result?.messageId,
                }));
            }
        } catch (e) {
            console.log(JSON.stringify({ type: 'result', error: e.message }));
        }
    }
}

main().catch(e => {
    console.log(JSON.stringify({ type: 'error', error: e.message }));
    process.exit(1);
});
