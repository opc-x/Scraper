from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response

from app.adapters.registry import close_all
from app.core.telegram_client import close_all_clients
from app.api.routes import channels, config, save, search, telegram_auth, telegram_ops
from app.core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await close_all()
    await close_all_clients()


app = FastAPI(
    title="Scraper",
    description="AI-native multi-channel job scraper",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(search.router)
app.include_router(channels.router)
app.include_router(save.router)
app.include_router(config.router)
app.include_router(telegram_auth.router)
app.include_router(telegram_ops.router)


@app.get("/", response_class=HTMLResponse)
async def index():
    html = (Path(__file__).parent / "index.html").read_text()
    return HTMLResponse(html)


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


@app.get("/manifest.json")
async def manifest():
    return JSONResponse({
        "name": "Scraper 职位狙击",
        "short_name": "Scraper",
        "description": "多渠道职位实时抓取",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#0a0a0a",
        "theme_color": "#0a0a0a",
        "orientation": "portrait",
        "icons": [
            {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
            {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
        ],
    })


@app.get("/sw.js")
async def service_worker():
    sw = """
const CACHE = 'scraper-v1';
const OFFLINE = ['/'];
self.addEventListener('install', e => { e.waitUntil(caches.open(CACHE).then(c => c.addAll(OFFLINE))); self.skipWaiting(); });
self.addEventListener('activate', e => { e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))); self.clients.claim(); });
self.addEventListener('fetch', e => {
  if (e.request.url.includes('/api/')) return;
  e.respondWith(fetch(e.request).catch(() => caches.match('/')));
});
"""
    return Response(content=sw, media_type="application/javascript")


@app.get("/icon-{size}.png")
async def icon(size: str):
    import base64
    # 最小有效 PNG：绿色圆形
    _icons = {
        "192": "iVBORw0KGgoAAAANSUhEUgAAAMAAAADACAYAAABS3GwHAAAACXBIWXMAAAsTAAALEwEAmpwYAAABpElEQVR4nO3BMQEAAADCoPVP7WsIoAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAeAMBuAABHgAAAABJRU5ErkJggg==",
    }
    # Return a simple 1x1 green PNG for any size
    import struct, zlib
    sz = int(size) if size.isdigit() else 192
    def make_png(s):
        center = s / 2
        rows = []
        for y in range(s):
            row = b'\x00'
            for x in range(s):
                dx, dy = x - center + .5, y - center + .5
                if dx*dx + dy*dy <= center*center:
                    row += b'\x22\xc5\x5e\xff'
                else:
                    row += b'\x00\x00\x00\x00'
            rows.append(row)
        raw = b''.join(rows)
        def chunk(t, d):
            c = t + d
            return struct.pack('>I', len(d)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)
        ihdr = struct.pack('>IIBBBBB', s, s, 8, 6, 0, 0, 0)
        return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b'')
    return Response(content=make_png(sz), media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=settings.debug)
