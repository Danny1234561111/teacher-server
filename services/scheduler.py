# services/scheduler.py
import asyncio
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime
from typing import Optional

from database.database import SessionLocal
from services.parser_service import ParserService

logger = logging.getLogger(__name__)


class ParserScheduler:
    """Планировщик для периодического запуска парсера"""

    def __init__(self, interval_hours: int = 1):
        self.interval_hours = interval_hours
        self.scheduler = AsyncIOScheduler()
        self.is_running = False
        self.last_run: Optional[datetime] = None
        self.last_stats: Optional[dict] = None

    async def run_parser_job(self):
        """Задание для запуска парсера"""
        logger.info(f"⏰ Запуск парсера по расписанию ({self.interval_hours}ч)")

        db = SessionLocal()
        try:
            parser = ParserService(db)
            stats = parser.run_parser()

            self.last_run = datetime.utcnow()
            self.last_stats = stats

            logger.info(f"✅ Парсер завершил работу в {self.last_run}")

        except Exception as e:
            logger.error(f"❌ Ошибка в задании парсера: {e}")
        finally:
            db.close()

    def start(self):
        """Запускает планировщик"""
        if self.is_running:
            logger.warning("⚠️ Планировщик уже запущен")
            return

        # Добавляем задание
        self.scheduler.add_job(
            self.run_parser_job,
            trigger=IntervalTrigger(hours=self.interval_hours),
            id='parser_job',
            name='Парсинг абитуриентов',
            replace_existing=True
        )

        self.scheduler.start()
        self.is_running = True
        logger.info(f"✅ Планировщик запущен (интервал: {self.interval_hours}ч)")

    def stop(self):
        """Останавливает планировщик"""
        if self.is_running:
            self.scheduler.shutdown()
            self.is_running = False
            logger.info("🛑 Планировщик остановлен")

    def run_now(self):
        """Запускает парсер немедленно (вне расписания)"""
        logger.info("🚀 Ручной запуск парсера")
        asyncio.create_task(self.run_parser_job())


# Глобальный экземпляр планировщика
scheduler = ParserScheduler(interval_hours=1)  # По умолчанию каждый час