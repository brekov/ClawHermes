#!/usr/bin/env node
// ClawHermes Channel Bridge
// 复用 OpenClaw 的微信 SDK 发消息，飞书走 HTTP API
// ClawHermes (Python) → HTTP → Bridge → Weixin/Feishu

const http = require('http');
const path = require('path');

const PORT = parseInt(process.env.CH_BRIDGE_PORT || '18788');
const CLAWHERMES_URL = process.env.CH_GATEWAY_URL || 'http://127.0.0.1:18789';

// 加载微信 SDK（CJS 兼容）
const wxSend = require('/root/.openclaw/extensions/openclaw-weixin/dist/src/messaging/send.js');
console.log('✅ 微信 SDK 已加载');

// 飞书凭证（从环境变量读，和 OpenClaw 共用）
const FEISHU_APP_ID = process.env.FEISHU_APP_ID || process.env.LARK_APP_ID;
const FEISHU_APP_SECRET = process.env.FEISHU_APP_SECRET || process.env.LARK_APP_SECRET;
let feishuToken = null;
let feishuTokenExpiry = 0;

// 获取飞书 access_token
async function getFeishuToken() {
    if (feishuToken && Date.now() < feishuTokenExpiry) return feishuToken;
    if (!FEISHU_APP_ID || !FEISHU_APP_SECRET) return null;

    const https = require('https');
    const data = JSON.stringify({ app_id: FEISHU_APP_ID, app_secret: FEISHU_APP_SECRET });

    return new Promise((resolve, reject) => {
        const req = https.request({
            hostname: 'open.feishu.cn',
            path: '/open-apis/auth/v3/tenant_access_token/internal',
            method: 'POST',
            headers: { 'Content-Type': 'application/json; charset=utf-8' },
        }, (res) => {
            let body = '';
            res.on('data', c => body += c);
            res.on('end', () => {
                try {
                    const d = JSON.parse(body);
                    feishuToken = d.tenant_access_token;
                    feishuTokenExpiry = Date.now() + (d.expire || 7200) * 1000 - 60000;
                    resolve(feishuToken);
                } catch (e) { reject(e); }
            });
        });
        req.on('error', reject);
        req.write(data);
        req.end();
    });
}

// 发送飞书消息
async function sendFeishu(chatId, text) {
    const token = await getFeishuToken();
    if (!token) return { error: '飞书 token 获取失败' };

    const https = require('https');
    return new Promise((resolve) => {
        const postData = JSON.stringify({
            receive_id: chatId,
            msg_type: 'text',
            content: JSON.stringify({ text }),
        });

        const req = https.request({
            hostname: 'open.feishu.cn',
            path: '/open-apis/im/v1/messages?receive_id_type=chat_id',
            method: 'POST',
            headers: {
                'Content-Type': 'application/json; charset=utf-8',
                'Authorization': `Bearer ${token}`,
            },
        }, (res) => {
            let body = '';
            res.on('data', c => body += c);
            res.on('end', () => {
                try {
                    const d = JSON.parse(body);
                    resolve(d.code === 0 ? { success: true } : { error: d.msg });
                } catch (e) { resolve({ error: e.message }); }
            });
        });
        req.on('error', (e) => resolve({ error: e.message }));
        req.write(postData);
        req.end();
    });
}

// 发送消息
async function handleSend(channel, to, text) {
    try {
        if (channel === 'weixin') {
            const result = await wxSend.sendMessageWeixin({ to, text, opts: { contextToken: '' } });
            return { success: true, messageId: result?.messageId };
        } else if (channel === 'feishu') {
            return await sendFeishu(to, text);
        }
        return { error: `unknown channel: ${channel}` };
    } catch (e) {
        return { error: e.message };
    }
}

// HTTP 服务器
const server = http.createServer(async (req, res) => {
    res.setHeader('Content-Type', 'application/json');
    res.setHeader('Access-Control-Allow-Origin', '*');

    if (req.method === 'OPTIONS') { res.writeHead(204); res.end(); return; }

    const url = new URL(req.url, `http://${req.headers.host}`);

    const sendJSON = (code, data) => {
        res.writeHead(code);
        res.end(JSON.stringify(data));
    };

    const readBody = () => new Promise((resolve) => {
        let body = '';
        req.on('data', c => body += c);
        req.on('end', () => { try { resolve(JSON.parse(body)); } catch { resolve({}); } });
    });

    try {
        // GET /health
        if (req.method === 'GET' && url.pathname === '/health') {
            return sendJSON(200, {
                status: 'ok',
                weixin: !!wxSend.sendMessageWeixin,
                feishu: !!(FEISHU_APP_ID && FEISHU_APP_SECRET),
                feishu_configured: !!(FEISHU_APP_ID && FEISHU_APP_SECRET),
            });
        }

        // POST /send
        if (req.method === 'POST' && url.pathname === '/send') {
            const body = await readBody();
            const result = await handleSend(body.channel, body.to, body.text);
            return sendJSON(result.error ? 400 : 200, result);
        }

        sendJSON(404, { error: 'not found' });
    } catch (e) {
        sendJSON(500, { error: e.message });
    }
});

server.listen(PORT, '127.0.0.1', () => {
    console.log(`🔌 ClawHermes Channel Bridge (CJS)`);
    console.log(`   Port: ${PORT}`);
    console.log(`   Weixin: ✅ SDK loaded`);
    console.log(`   Feishu: ${FEISHU_APP_ID ? '✅ configured' : '❌ not configured'}`);
    console.log(`   API:`);
    console.log(`     POST /send    { channel, to, text }`);
    console.log(`     GET  /health`);
});
