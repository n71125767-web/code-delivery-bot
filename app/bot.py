import asyncio
import logging
import os
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from app.config import BOT_TOKEN
from app.database import init_db
from app.handlers import on_message, on_business_message, on_callback_query, on_business_connection, on_edited_business_message, on_deleted_business_messages

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def health(_request):
    return web.json_response({"status": "ok"})

async def start_health_server():
    app = web.Application(); app.router.add_get('/', health); app.router.add_get('/health', health)
    runner = web.AppRunner(app); await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.getenv('PORT', '10000'))); await site.start()
    logger.info('Health server started')
    return runner

def build_dispatcher() -> Dispatcher:
    dp=Dispatcher()
    dp.message.register(on_message); dp.callback_query.register(on_callback_query)
    dp.business_message.register(on_business_message); dp.business_connection.register(on_business_connection)
    dp.edited_business_message.register(on_edited_business_message); dp.deleted_business_messages.register(on_deleted_business_messages)
    return dp

async def main():
    await init_db(); await start_health_server()
    while True:
        bot=Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=None)); dp=build_dispatcher()
        try:
            me=await bot.me(); logger.info('Bot started: @%s id=%s', me.username, me.id)
            logger.info('FIX_MARKER_RELEASE_REBUILD=v18 loaded')
            await dp.start_polling(bot, allowed_updates=['message','callback_query','business_connection','business_message','edited_business_message','deleted_business_messages'])
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception('Polling stopped unexpectedly; restart in 5 seconds')
            await asyncio.sleep(5)
        finally:
            await bot.session.close()

if __name__ == '__main__': asyncio.run(main())
