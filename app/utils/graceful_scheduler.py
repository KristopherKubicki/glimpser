"""APScheduler wrapper with restart-friendly shutdown."""
from __future__ import annotations

import logging
from apscheduler.schedulers.background import BackgroundScheduler
from flask_apscheduler import APScheduler


class GracefulAPScheduler(APScheduler):
    """Background scheduler that can restart after shutdown."""

    def __init__(self) -> None:
        super().__init__()
        self._scheduler = None
        self.set_scheduler(BackgroundScheduler())

    def set_scheduler(self, scheduler: BackgroundScheduler) -> None:
        self._scheduler = scheduler

    def shutdown(self, wait: bool = True) -> None:
        try:
            if self.running:
                for job in self._scheduler.get_jobs():
                    job.remove()
                super().shutdown(wait)
                self.set_scheduler(BackgroundScheduler())
            else:
                logging.info("Scheduler is not running.")
        except Exception as e:
            logging.error(f"Error during scheduler shutdown: {e}")
        finally:
            logging.info("Scheduler shutdown complete.")
