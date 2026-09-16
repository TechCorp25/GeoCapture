const CACHE="civicmaps-gps-v2";
const ASSETS=["./","./index.html","./manifest.json"];
self.addEventListener("install",e=>e.waitUntil(caches.open(CACHE).then(c=>c.addAll(ASSETS))));
self.addEventListener("activate",e=>e.waitUntil(
  caches.keys().then(keys=>Promise.all(keys.filter(key=>key!==CACHE).map(key=>caches.delete(key))))
    .then(()=>self.clients.claim())
));
self.addEventListener("fetch",e=>{
  if(e.request.method!=="GET") return;
  // Prefer deployed updates while falling back to the cached application offline.
  e.respondWith(fetch(e.request).then(response=>{
    const copy=response.clone();
    caches.open(CACHE).then(cache=>cache.put(e.request,copy));
    return response;
  }).catch(()=>caches.match(e.request)));
});
