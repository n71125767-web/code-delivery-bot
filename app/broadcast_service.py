from __future__ import annotations
import asyncio
import json
import logging
from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter
from sqlalchemy import select
from app.database import SessionLocal
from app.models import BroadcastJob
from app.time_utils import utcnow

logger=logging.getLogger(__name__)

async def create_broadcast_job(admin_id:int, recipients:list[int], text:str) -> int:
    async with SessionLocal() as session:
        job=BroadcastJob(admin_id=admin_id,text=text,status="queued",total_count=len(recipients),recipients_json=json.dumps(recipients),cursor=0)
        session.add(job); await session.commit(); await session.refresh(job); return job.id

async def run_broadcast_job(bot:Bot, job_id:int) -> None:
    async with SessionLocal() as session:
        job=await session.get(BroadcastJob,job_id)
        if not job or job.status=="done": return
        recipients=json.loads(job.recipients_json or "[]")
        start=int(job.cursor or 0); job.status="running"; await session.commit()
    for idx in range(start,len(recipients)):
        recipient_id=int(recipients[idx]); ok=False; err=None
        try:
            await bot.send_message(recipient_id,job.text); ok=True
        except TelegramRetryAfter as exc:
            await asyncio.sleep(float(exc.retry_after)+0.5)
            try:
                await bot.send_message(recipient_id,job.text); ok=True
            except Exception as e: err=str(e)
        except Exception as e: err=str(e)
        async with SessionLocal() as session:
            current=await session.get(BroadcastJob,job_id)
            if not current: return
            current.cursor=idx+1
            if ok: current.sent_count=int(current.sent_count or 0)+1
            else:
                current.failed_count=int(current.failed_count or 0)+1
                current.last_error=(err or "send failed")[:1000]
            await session.commit()
        await asyncio.sleep(0.05)
    async with SessionLocal() as session:
        current=await session.get(BroadcastJob,job_id)
        if not current: return
        current.status="done"; current.finished_at=utcnow(); await session.commit()
        admin_id=current.admin_id; total=current.total_count; sent=current.sent_count; failed=current.failed_count
    try:
        await bot.send_message(admin_id,f"📢 Рассылка завершена\n\nПолучателей: {total}\nОтправлено: {sent}\nОшибок: {failed}")
    except Exception:
        logger.exception("BROADCAST_RESULT_SEND_FAILED admin_id=%s",admin_id)

async def resume_broadcast_jobs(bot:Bot) -> list[asyncio.Task]:
    async with SessionLocal() as session:
        ids=list((await session.scalars(select(BroadcastJob.id).where(BroadcastJob.status.in_(("queued","running"))))).all())
    return [asyncio.create_task(run_broadcast_job(bot,int(job_id))) for job_id in ids]
