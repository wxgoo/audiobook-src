/**
 * PWA Service Worker 注册（r46）。
 *
 * 只在生产环境（nuxt generate 出来的静态产物）注册：开发模式下 dist 不稳定，
 * 注册 sw 反而会缓存到旧 chunk 干扰调试。
 *
 * 更新策略：sw.js 自身每次导航由浏览器检查（updateViaCache: 'none'），
 * 发现新版本 skipWaiting + clients.claim 立即接管；配合 chunk-reload.js，
 * 旧页面取不到已删 chunk 时会自动刷新一次，避免白屏。
 */
export default () => {
  if (!process.client) return;
  if (process.env.NODE_ENV !== 'production') return;
  if (!('serviceWorker' in navigator)) return;

  window.addEventListener('load', () => {
    navigator.serviceWorker
      .register('/sw.js', { scope: '/', updateViaCache: 'none' })
      .catch(() => { /* 注册失败不应影响站点可用 */ });
  });
};
