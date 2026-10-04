const CACHE="civicmaps-gps-v2";
const ASSETS=["./","./index.html","./manifest.json"];
self.addEventListener("install",e=>e.waitUntil(
  caches.open(CACHE).then(c=>c.addAll(ASSETS)).then(()=>self.skipWaiting())
));
self.addEventListener("activate",e=>e.waitUntil(
  caches.keys().then(keys=>Promise.all(keys.filter(key=>key!==CACHE).map(key=>caches.delete(key))))
    .then(()=>self.clients.claim())
));
self.addEventListener("fetch",e=>{
  if(e.request.method!=="GET") return;
  if(new URL(e.request.url).origin!==self.location.origin) return;
  // Prefer deployed updates while falling back to the cached application offline.
  e.respondWith((async()=>{
    try {
      const response=await fetch(e.request);
      // Do not replace a valid offline response with an error page. Awaiting the
      // write also keeps the worker alive until the cache update is complete.
      if(response.ok && response.type==="basic") {
        const cache=await caches.open(CACHE);
        await cache.put(e.request,response.clone());
      }
      return response;
    } catch {
      return (await caches.match(e.request)) || Response.error();
    }
  })());
});
