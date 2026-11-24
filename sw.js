// Офлайн-режим: сайт и библиотеки Firebase кэшируются на устройстве.
// Страница - «сначала сеть»: при интернете всегда свежая версия, без него - из кэша.
const CACHE = "kartochki-v2";
// Версия Firebase должна совпадать с FB_VERSION в index.html
const FB = "https://www.gstatic.com/firebasejs/10.12.2/";
// Всё, без чего сайт не запустится без интернета, сохраняем сразу при установке,
// а не при следующем визите: иначе без связи сайт открылся бы в демо-режиме без данных.
const PRECACHE = ["./", "./index.html", "./config.js", "./icon-180.png",
  FB + "firebase-app.js", FB + "firebase-auth.js", FB + "firebase-firestore.js"];

self.addEventListener("install", e => {
  self.skipWaiting();
  // по одному файлу: если какой-то не скачался, остальные всё равно сохранятся
  e.waitUntil(caches.open(CACHE).then(c => Promise.all(PRECACHE.map(u => c.add(u).catch(() => {})))));
});

self.addEventListener("activate", e => {
  e.waitUntil(caches.keys()
    .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);

  if (url.origin === location.origin) {
    e.respondWith(
      fetch(req).then(res => {
        if (res.ok) { const copy = res.clone(); caches.open(CACHE).then(c => c.put(req, copy)); }
        return res;
      }).catch(() => caches.match(req, { ignoreSearch: true }).then(r => {
        if (r) return r;
        // страницу подставляем только вместо страницы, а не вместо скриптов и данных
        if (req.mode === "navigate") return caches.match("./");
        return new Response("", { status: 504, statusText: "Offline" });
      }))
    );
  } else if (url.hostname === "www.gstatic.com" && url.pathname.startsWith("/firebasejs/")) {
    // версия библиотеки зашита в адрес, поэтому можно брать из кэша
    e.respondWith(
      caches.match(req).then(r => r || fetch(req).then(res => {
        if (res.ok) { const copy = res.clone(); caches.open(CACHE).then(c => c.put(req, copy)); }
        return res;
      }))
    );
  }
});
