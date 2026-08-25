// 杀死开关：不再注册新的 service worker（见 main.tsx），这份脚本只负责把老版本
// （包括重写前那版会把失败请求兜底成缓存旧首页、导致 iOS 主屏幕黑屏的 sw.js）自己注销掉，
// 清空它留下的缓存，然后让还开着的页面重新加载一次。
self.addEventListener("install", () => {
  self.skipWaiting();
});
self.addEventListener("activate", (e) => {
  e.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(keys.map((k) => caches.delete(k)));
      await self.registration.unregister();
      const clientList = await self.clients.matchAll({ type: "window" });
      for (const client of clientList) {
        client.navigate(client.url);
      }
    })(),
  );
});
