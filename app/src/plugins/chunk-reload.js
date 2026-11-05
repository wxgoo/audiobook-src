/**
 * chunk 加载失败时自动刷新一次。
 *
 * 背景：`/_nuxt/*.js` 的文件名带内容哈希，每次发版整批换名。升级那一刻
 * 仍开着旧页面的客户端，点击任何懒加载路由都会去取「已经不存在」的 chunk。
 *
 * 两种表现都要处理：
 *   1. nginx 按老规则走 SPA 兜底 → 返回 200 + text/html，浏览器把 `<` 当
 *      JS 解析，控制台报 `Unexpected token '<'`；
 *   2. nginx 已配置 `/_nuxt/ try_files $uri =404`（4.6.0-19 r10 起）→ 干净 404。
 *
 * 用户看到的结果都一样：点了没反应或白屏，必须手动 Ctrl+F5。
 * 这里在路由层兜住，自动 reload 一次；用 sessionStorage 记一个短时效标记，
 * 避免「服务器真的坏了」时陷入无限刷新。
 */

const FLAG = 'chunk_reload_at';
// 同一原因 15 秒内只自动刷新一次
const COOLDOWN = 15000;

function isChunkLoadError(err) {
    if (!err) return false;
    const name = err.name || '';
    const msg = String(err.message || err || '');
    return (
        name === 'ChunkLoadError'
        // webpack 4/5 的懒加载失败
        || /Loading (CSS )?chunk [\w-]+ failed/i.test(msg)
        // 拿到 HTML 当 JS 解析（SPA 兜底导致）
        || /Unexpected token '<'/i.test(msg)
        || /MIME type \('text\/html'\)/i.test(msg)
        // =404 干净 404 的情况
        || /error loading dynamically imported module/i.test(msg)
    );
}

function recentlyReloaded() {
    try {
        const at = Number(sessionStorage.getItem(FLAG) || 0);
        return at > 0 && Date.now() - at < COOLDOWN;
    } catch (e) {
        return true;   // 隐私模式读不到，宁可不动，避免刷新风暴
    }
}

function markReload() {
    try {
        sessionStorage.setItem(FLAG, String(Date.now()));
    } catch (e) { /* 忽略 */ }
}

export default ({ app }) => {
    if (!process.client) return;

    // 首屏加载成功就清掉标记，保证下一次发版还能自动刷新
    app.router.onReady(() => {
        try { sessionStorage.removeItem(FLAG); } catch (e) { /* 忽略 */ }
    });

    app.router.onError((err) => {
        if (!isChunkLoadError(err)) return;
        if (recentlyReloaded()) {
            // 已经刷过一次还是失败：不再刷，把错误留给上层（控制台可见）
            // eslint-disable-next-line no-console
            console.error('[chunk] 刷新后仍然加载失败，可能是服务端资源缺失：', err);
            return;
        }
        markReload();
        // eslint-disable-next-line no-console
        console.warn('[chunk] 前端资源已更新，自动刷新一次以加载新版本');
        window.location.reload();
    });
};
