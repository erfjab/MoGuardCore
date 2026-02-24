import os
import psutil
from src.config import logger
from src.utils.notif import NotificationService


async def check_system_resources():
    try:
        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()
        memory_usage = memory_info.rss
        await NotificationService.system_log(f"Current memory usage: {memory_usage / (1024**2):.2f} MB")
    except Exception as e:
        logger.error(f"Error in resource monitor: {e}")
