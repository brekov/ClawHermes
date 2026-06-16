#!/usr/bin/env node
/**
 * ClawHermes Channel Bridge
 * 
 * 微信依赖 @tencent-weixin/openclaw-weixin
 * 飞书依赖 @larksuite/openclaw-lark
 * 
 * 安装: npm install @tencent-weixin/openclaw-weixin @larksuite/openclaw-lark
 */
const http = require('http');
const https = require('https');

const PORT = parseInt(process.env.CH_BRIDGE_PORT || '18788');
const WX_PKG = process.env.CH_WX_PACKAGE || '@tencent-weixin/openclaw-weixin';
const LARK_PKG = process.env.CH_LARK_PACKAGE || '@larksuite/openclaw-lark';
const FEISHU_APP_ID = process.env.FEISHU_APP_ID || process.env.LARK_APP_ID;
const FEISHU_APP_SECRET = process.env.FEISHU_APP_SECRET || process.env.LARK_APP_SECRET;

let wxSend = null;

// 加载微信 SDK
try {
    const mod = require(WX_PKG);
    // 微信 SDK 的发送函数在 dist/src/messaging/send.js
    const path = require('path');
    const sendPath = path.dirname(require.resolve(WX_PKG + '/package.json'));
    wxSend = require(path.join(sendPath, 'dist/src/messaging/send.js'));
    console.log(`✅ 微信 SDK 已加载: ${WX_PKG}`);
} catch (e) {
    console.log(`⚠️  微信 SDK 加载失败: ${e.message}`);
    console.log('   运行: npm install @tencent-weixin/openclaw-weixin');
}

// 飞书 token
let feishuToken = null, feishuTokenExpiry = 0;

function getFeishuToken() {
    return new Promise((resolve) => {
        if (feishuToken && Date.now() < feishuTokenExpiry) return resolve(feishuToken);
        if (!FEISHU_APP_ID || !FEISHU_APP_SECRET) return resolve(null);
        const data = JSON.stringify({ app_id: FEISHU_APP_ID, app_secret: FEISHU_APP_SECRET });
        const req = https.request({
            hostname: 'open.feishu.cn', path: '/open-apis/auth/v3/tenant_access_token/internal',
            method: 'POST', headers: { 'Content-Type': 'application/json' },
        }, (res) => {
            let body = '';
            res.on('data', c => body += c);
            res.on('end', () => {
                try {
                    const d = JSON.parse(body);
                    feishuToken = d.tenant_access_token;
                    feishuTokenExpiry = Date.now() + (d.expire || 7200) * 1000 - 60000;
                    resolve(feishuToken);
                } catch { resolve(null); }
            });
        });
        req.on('error', () => resolve(null));
        req.write(data);
        req.end();
    });
}

async function handleSend(channel, to, text) {
    try {
        if (channel === 'weixin') {
            if (!wxSend) return { error: '微信 SDK 未加载' };
            const result = await wxSend.sendMessageWeixin({ to, text, opts: { contextToken: '' } });
            return { success: true, messageId: result?.messageId };
        } else if (channel === 'feishu') {
            const token = await getFeishuToken();
            if (!token) return { error: '飞书 token 获取失败' };
            return new Promise((resolve) => {
                const data = JSON.stringify({ receive_id: to, msg_type: 'text', content: JSON.stringify({ text }) });
                const req = https.request({
                    hostname: 'open.feishu.cn', path: '/open-apis/im/v1/messages?receive_id_type=chat_id',
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
                }, (res) => {
                    let body = '';
                    res.on('data', c => body += c);
                    res.on('end', () => {
                        try { const d = JSON.parse(body); resolve(d.code === 0 ? { success: true } : { error: d.msg }); }
                        catch { resolve({ error: 'parse error' }); }
                    });
                });
                req.on('error', (e) => resolve({ error: e.message }));
                req.write(data);
                req.end();
            });
        }
        return { error: `unknown channel: ${channel}` };
    } catch (e) {
        return { error: e.message };
    }
}

const server = http.createServer(async (req, res) => {
    res.setHeader('Content-Type', 'application/json');
    res.setHeader('Access-Control-Allow-Origin', '*');
    if (req.method === 'OPTIONS') { res.writeHead(204); res.end(); return; }
    const url = new URL(req.url, `http://${req.headers.host}`);
    const readBody = () => new Promise((r) => {
        let b = ''; req.on('data', c => b += c); req.on('end', () => { try { r(JSON.parse(b)); } catch { r({}); } });
    });
    try {
        if (req.method === 'GET' && url.pathname === '/health') {
            res.writeHead(200);
            return res.end(JSON.stringify({ status: 'ok', weixin: !!wxSend }));
        }
        if (req.method === 'POST' && url.pathname === '/send') {
            const body = await readBody();
            const result = await handleSend(body.channel, body.to, body.text);
            res.writeHead(result.error ? 400 : 200);
            return res.end(JSON.stringify(result));
        }
        res.writeHead(404);
        res.end(JSON.stringify({ error: 'not found' }));
    } catch (e) {
        res.writeHead(500);
        res.end(JSON.stringify({ error: e.message }));
    }
});

server.listen(PORT, '127.0.0.1', () => {
    console.log(`🔌 ClawHermes Channel Bridge`);
    console.log(`   Port: ${PORT}`);
    console.log(`   Weixin SDK: ${wxSend ? '✅' : '❌'}`);
});
