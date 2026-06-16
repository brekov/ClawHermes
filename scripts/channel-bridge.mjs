#!/usr/bin/env node
/**
 * ClawHermes Channel Bridge
 * 
 * Node.js 桥接层，复用 OpenClaw 的 @tencent-weixin/openclaw-weixin
 * 和 @larksuite/openclaw-lark  SDK 的发送能力。
 * 
 * ClawHermes (Python) → HTTP → Bridge (Node.js) → Weixin/Feishu API
 * 
 * 用法: node channel-bridge.mjs [--port 18788]
 */
import http from 'node:http';
import { createRequire } from 'node:module';

const PORT = parseInt(process.env.CH_BRIDGE_PORT || '18788');
const CLAWHERMES_URL = process.env.CH_GATEWAY_URL || 'http://127.0.0.1:18789';

const require = createRequire(import.meta.url);

// 懒加载 SDK（只在需要时才 require）
let weixinSend = null;
let larkSend = null;

function getWeixinSend() {
    if (!weixinSend) {
        const mod = require('@tencent-weixin/openclaw-weixin');
        weixinSend = mod.sendMessageWeixin;
    }
    return weixinSend;
}

function getLarkSend() {
    if (!larkSend) {
        const mod = require('@larksuite/openclaw-lark');
        larkSend = mod.sendTextLark;
    }
    return larkSend;
}

// 记录活跃的 Webhook 回调（微信/飞书收到消息后通知 ClawHermes）
const activeCallbacks = new Map();

/**
 * 发送消息
 * POST /send
 * Body: { channel: "weixin"|"feishu", to: "user_id", text: "消息内容" }
 */
async function handleSend(body) {
    const { channel, to, text } = body;
    if (!channel || !to || !text) {
        return { error: 'missing required fields: channel, to, text' };
    }

    try {
        if (channel === 'weixin') {
            const send = getWeixinSend();
            const result = await send({ to, text, opts: {} });
            return { success: true, messageId: result?.messageId };
        } else if (channel === 'feishu' || channel === 'lark') {
            const send = getLarkSend();
            const result = await send({ chat_id: to, text });
            return { success: true, data: result };
        } else {
            return { error: `unknown channel: ${channel}` };
        }
    } catch (e) {
        return { error: e.message };
    }
}

/**
 * 注册消息回调
 * POST /register
 * Body: { channel: "weixin"|"feishu", webhook_url: "http://..." }
 */
function handleRegister(body) {
    const { channel, webhook_url } = body;
    if (!channel || !webhook_url) {
        return { error: 'missing channel or webhook_url' };
    }
    activeCallbacks.set(channel, webhook_url);
    return { success: true, registered: channel, callback: webhook_url };
}

// HTTP Server
const server = http.createServer(async (req, res) => {
    res.setHeader('Content-Type', 'application/json');
    res.setHeader('Access-Control-Allow-Origin', '*');

    // CORS preflight
    if (req.method === 'OPTIONS') {
        res.writeHead(204);
        res.end();
        return;
    }

    const url = new URL(req.url, `http://${req.headers.host}`);

    try {
        // GET /health
        if (req.method === 'GET' && url.pathname === '/health') {
            res.writeHead(200);
            res.end(JSON.stringify({
                status: 'ok',
                channels: Array.from(activeCallbacks.keys()),
                weixin_sdk: !!weixinSend,
                lark_sdk: !!larkSend,
            }));
            return;
        }

        // POST /send
        if (req.method === 'POST' && url.pathname === '/send') {
            let body = '';
            req.on('data', chunk => body += chunk);
            req.on('end', async () => {
                try {
                    const result = await handleSend(JSON.parse(body));
                    res.writeHead(result.error ? 400 : 200);
                    res.end(JSON.stringify(result));
                } catch (e) {
                    res.writeHead(500);
                    res.end(JSON.stringify({ error: e.message }));
                }
            });
            return;
        }

        // POST /register
        if (req.method === 'POST' && url.pathname === '/register') {
            let body = '';
            req.on('data', chunk => body += chunk);
            req.on('end', () => {
                const result = handleRegister(JSON.parse(body));
                res.writeHead(result.error ? 400 : 200);
                res.end(JSON.stringify(result));
            });
            return;
        }

        // Not Found
        res.writeHead(404);
        res.end(JSON.stringify({ error: 'not found' }));

    } catch (e) {
        res.writeHead(500);
        res.end(JSON.stringify({ error: e.message }));
    }
});

server.listen(PORT, '127.0.0.1', () => {
    console.log(`🔌 ClawHermes Channel Bridge running on http://127.0.0.1:${PORT}`);
    console.log(`   Forwarding to ClawHermes at ${CLAWHERMES_URL}`);
    console.log(`   Endpoints:`);
    console.log(`     POST /send     - 发送消息`);
    console.log(`     POST /register - 注册消息回调`);
    console.log(`     GET  /health   - 健康检查`);
});
