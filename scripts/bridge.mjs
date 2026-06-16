#!/usr/bin/env node
/**
 * ClawHermes Channel Bridge — Node.js SDK 兼容层
 * 
 * 由 Python Gateway 自动启动，通过 HTTP 为本进程内的 Node SDK 提供调用入口。
 * 
 * Python (WeChatAdapter) → HTTP → Bridge → @tencent-weixin/openclaw-weixin
 * Python (FeishuAdapter) → HTTP → Bridge → @larksuite/openclaw-lark
 */
const http = require('http');

const PORT = parseInt(process.env.CH_BRIDGE_PORT || '18788');
const WX_PKG = process.env.CH_WX_PACKAGE || '@tencent-weixin/openclaw-weixin';
const LARK_PKG = process.env.CH_LARK_PACKAGE || '@larksuite/openclaw-lark';

// ── 加载微信 SDK ──────────────────────────────────────
let wxSend = null;
try {
    const wxRoot = require.resolve(WX_PKG + '/package.json');
    const path = require('path');
    wxSend = require(path.join(path.dirname(wxRoot), 'dist/src/messaging/send.js'));
    console.log(`✅ 微信 SDK 已加载: ${WX_PKG}`);
} catch (e) {
    console.log(`ℹ️  微信 SDK 未安装 (${e.message})`);
}

// ── HTTP 服务 ─────────────────────────────────────────
const server = http.createServer((req, res) => {
    res.setHeader('Content-Type', 'application/json');
    res.setHeader('Access-Control-Allow-Origin', '*');
    if (req.method === 'OPTIONS') { res.writeHead(204); res.end(); return; }

    const url = new URL(req.url, `http://${req.headers.host}`);
    let body = '';
    req.on('data', c => body += c);
    req.on('end', async () => {
        try {
            const result = await handle(url, body);
            res.writeHead(result.error ? 400 : 200);
            res.end(JSON.stringify(result));
        } catch (e) {
            res.writeHead(500);
            res.end(JSON.stringify({ error: e.message }));
        }
    });
});

async function handle(url, body) {
    const path = url.pathname;
    const params = Object.fromEntries(url.searchParams);

    if (path === '/health') {
        return { status: 'ok', weixin: !!wxSend };
    }

    if (path === '/send') {
        const { channel, to, text } = JSON.parse(body || '{}');
        if (!channel || !to || !text) return { error: 'missing channel/to/text' };

        if (channel === 'weixin') {
            if (!wxSend) return { error: '微信 SDK 未安装（npm install @tencent-weixin/openclaw-weixin）' };
            const result = await wxSend.sendMessageWeixin({ to, text, opts: { contextToken: '' } });
            return { success: true, messageId: result?.messageId };

        } else if (channel === 'feishu') {
            const FEISHU_APP_ID = process.env.FEISHU_APP_ID || process.env.LARK_APP_ID;
            const FEISHU_APP_SECRET = process.env.FEISHU_APP_SECRET || process.env.LARK_APP_SECRET;
            if (!FEISHU_APP_ID || !FEISHU_APP_SECRET) return { error: 'FEISHU_APP_ID/ SECRET 未设置' };
            const lark = require(LARK_PKG);
            const result = await lark.sendTextLark({ chat_id: to, text });
            return { success: true, data: result };
        }

        return { error: `unknown channel: ${channel}` };
    }

    if (path === '/install') {
        const { pkg } = params;
        if (!pkg) return { error: 'missing pkg parameter' };
        const { execSync } = require('child_process');
        execSync(`npm install ${pkg}`, { cwd: __dirname, stdio: 'inherit' });
        return { success: true, installed: pkg };
    }

    return { error: 'not found' };
}

server.listen(PORT, '127.0.0.1', () => {
    console.log(`🔌 ClawHermes Bridge (Node SDK 兼容层)`);
    console.log(`   端口: ${PORT}`);
    console.log(`   微信: ${wxSend ? '✅' : '❌'} (npm install @tencent-weixin/openclaw-weixin)`);
});
