/* MyBooks Service Worker（r46）
 *
 * 目标仅为「可安装 + 弱网下打开应用外壳」，不是离线阅读器。
 * 关键约束：**永不缓存 API 与书籍数据**（/api/*、/read/*、/get/*、/books/*、
 * /s/*、/readerx/* 等），否则会缓存他人私有数据、读到过期书目、把登录态串味。
 *
 * 策略：
 *   - 导航请求（HTML 页面）：network-first，失败时回退缓存的 index.html 外壳。
 *   - 带内容哈希的静态资源 /_nuxt/*、/static/*、/logo/*、/icons/*、/favicon*：
 *     cache-first（hash 文件名天然不过期，缓存命中零延迟）。
 *   - 其它一切请求：直接透传，不缓存。
 */

const CACHE = 'mybooks-shell-v1';
const SHELL = '/index.html';

// 需要缓存的静态壳前缀。注意不含 /api /read /get /books /s /readerx /audio /opds 等数据路径。
const STATIC_PREFIXES = [
  '/_nuxt/',
  '/static/',
  '/logo/',
  '/icons/',
  '/avatar/',
];
const STATIC_EXACT = ['/favicon.ico', '/robots.txt', '/manifest.json'];

function isStaticAsset(url) {
  if (STATIC_EXACT.indexOf(url.pathname) !== -1) return true;
  return STATIC_PREFIXES.some(function (p) { return url.pathname.indexOf(p) === 0; });
}

self.addEventListener('install', function (event) {
  event.waitUntil(
    caches.open(CACHE).then(function (cache) {
      return cache.add(SHELL).catch(function () { /* 首次离线安装失败不影响注册 */ });
    }).then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener('activate', function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.map(function (k) {
        if (k.indexOf('mybooks-shell-') === 0 && k !== CACHE) return caches.delete(k);
      }));
    }).then(function () { return self.clients.claim(); })
  );
});

self.addEventListener('fetch', function (event) {
  var req = event.request;
  if (req.method !== 'GET') return;

  var url = new URL(req.url);
  if (url.origin !== self.location.origin) return; // 跨域（如 CDN）不碰

  // 导航请求：network-first，离线回退外壳
  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req).then(function (res) {
        var copy = res.clone();
        caches.open(CACHE).then(function (c) { c.put(SHELL, copy); });
        return res;
      }).catch(function () {
        return caches.match(SHELL);
      })
    );
    return;
  }

  // 静态壳资源：cache-first
  if (isStaticAsset(url)) {
    event.respondWith(
      caches.match(req).then(function (hit) {
        if (hit) return hit;
        return fetch(req).then(function (res) {
          if (res && res.status === 200) {
            var copy = res.clone();
            caches.open(CACHE).then(function (c) { c.put(req, copy); });
          }
          return res;
        });
      })
    );
    return;
  }

  // 其余（API / 书籍 / 数据）：不缓存，直接透传
});
