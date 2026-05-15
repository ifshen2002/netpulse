from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()
_started = False


def start_scheduler() -> None:
    global _started
    if not _started:
        scheduler.start()
        _started = True


def stop_scheduler() -> None:
    global _started
    if _started and scheduler.running:
        scheduler.shutdown(wait=False)
        _started = False
