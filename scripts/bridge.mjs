#!/usr/bin/env node
/**
 * ClawHermes Node SDK 兼容层 — CLI 模式
 * 
 * 由 Python 端通过 subprocess 调用，加载官方 Node SDK 执行操作。
 * 不做常驻服务，用完即止。
 * 
 * 用法:
 *   node scripts/bridge.mjs send weixin <to> <text>
 *   node scripts/bridge.mjs send feishu <to> <text>
 *   node scripts/bridge.mjs check weixin
 *   node scripts/bridge.mjs check feishu
 */
const cmd = process.argv[2];
const channel = process.argv[3];

async function main() {
    try {
        if (cmd === 'check') {
            const result = { installed: false, sdk: null };
            if (channel === 'weixin') {
                try {
                    require.resolve('@tencent-weixin/openclaw-weixin');
                    result.installed = true;
                    result.sdk = '@tencent-weixin/openclaw-weixin';
                } catch {}
            } else if (channel === 'feishu') {
                try {
                    require.resolve('@larksuite/openclaw-lark');
                    result.installed = true;
                    result.sdk = '@larksuite/openclaw-lark';
                } catch {}
            }
            console.log(JSON.stringify(result));
            process.exit(0);
        }

        if (cmd === 'send') {
            const to = process.argv[4];
            const text = process.argv[5];
            if (!channel || !to || !text) {
                throw new Error('用法: bridge.mjs send <channel> <to> <text>');
            }

            if (channel === 'weixin') {
                const wx = require('@tencent-weixin/openclaw-weixin/dist/src/messaging/send.js');
                const result = await wx.sendMessageWeixin({ to, text, opts: { contextToken: '' } });
                console.log(JSON.stringify({ success: true, messageId: result?.messageId }));

            } else if (channel === 'feishu') {
                const lark = require('@larksuite/openclaw-lark');
                const FEISHU_APP_ID = process.env.FEISHU_APP_ID || process.env.LARK_APP_ID;
                const FEISHU_APP_SECRET = process.env.FEISHU_APP_SECRET || process.env.LARK_APP_SECRET;
                const result = await lark.sendTextLark({ chat_id: to, text });
                console.log(JSON.stringify({ success: true, data: result }));
            }
            process.exit(0);
        }

        console.error('用法: bridge.mjs send|check <channel> [args...]');
        process.exit(1);

    } catch (e) {
        console.log(JSON.stringify({ error: e.message }));
        process.exit(1);
    }
}

main();
