import os
from aiohttp import web


async def health(request):
    return web.Response(text="Bot is running")


app = web.Application()
app.router.add_get("/", health)
app.router.add_get("/health", health)

port = int(os.environ.get("PORT", 10000))
web.run_app(app, host="0.0.0.0", port=port)
