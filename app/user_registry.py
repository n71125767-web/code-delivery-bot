from datetime import datetime
from app.database import SessionLocal
from app.models import BotUser


async def touch_user(user_id: int, username: str | None) -> bool:
    async with SessionLocal() as session:
        row = await session.get(BotUser, user_id)
        is_new = row is None
        if row is None:
            row = BotUser(telegram_id=user_id, username=username, is_active=True)
            session.add(row)
        else:
            row.username = username
            row.is_active = True
            row.last_seen_at = datetime.utcnow()
        await session.commit()
        return is_new
