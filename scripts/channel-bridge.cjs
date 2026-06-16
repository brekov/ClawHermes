#!/usr/bin/env node
/**
 * ClawHermes Channel Bridge — 可选组件
 * 
 * 需要安装 @tencent-weixin/openclaw-weixin 才能启用微信发送能力。
 * 设置 CH_WX_SDK_PATH 环境变量指向 SDK 的 send.js 文件路径。
 * 
 * 飞书发送通过 HTTP API 直连，不依赖 OpenClaw。
 */
const http = require('http');
const https = require('https');

const PORT = parseInt(process.env.CH_BRIDGE_PORT || '18788');
const WX_SDK_PATH = process.env.CH_WX_SDK_PATH || '';
const FEISHU_APP_ID = process.env.FEISHU_APP_ID || process.env.LARK_APP_ID;
const FEISHU_APP_SECRET = process.env.FEISHU_APP_SECRET || process.env.LARK_APP_SECRET;

// 微信 SDK（可选加载）
let wxSend = null;
if (WX_SDK_PATH) {
    try {
        wxSend = require(WX_SDK_PATH);
        if (wxSend.sendMessageWeixin) {
            console.log(`✅ 微信 SDK 已加载: ${WX_SDK_PATH}`);
        } else {
            console.log(`⚠️  SDK 无 sendMessageWeixin，微信不可用`);
            wxSend = null;
        }
    } catch (e) {
        console.log(`⚠️  微信 SDK 加载失败: ${e.message}`);
    }
} else {
    console.log('ℹ️  未配置微信 SDK（设置 CH_WX_SDK_PATH 可启用）');
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
            if (!wxSend) return { error: '微信 SDK 未加载，请设置 CH_WX_SDK_PATH' };
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

// HTTP Server
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
            return res.end(JSON.stringify({ status: 'ok', weixin: !!wxSend, feishu: !!(FEISHU_APP_ID && FEISHU_APP_SECRET) }));
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
    console.log(`   Weixin: ${wxSend ? '✅' : '❌'} (set CH_WX_SDK_PATH)`);
    console.log(`   Feishu: ${FEISHU_APP_ID ? '✅' : '❌'}`);
});
