import asyncio
from uvicorn import Config, Server
from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from src.tasks import TaskManager
from src.db import GetDB, Admin
from src.utils.cache import AdminCache
from src.guard_node import GuardNodeManager
from src.utils.notif import NotificationService
from src.tasks.node_access import upsert_access
from src.tasks.links_update import update_links_task
from src.tasks.configs_update import update_configs_task
from src.routers import api_router
from src.config import (
    UVICORN_SSL_CERTFILE,
    UVICORN_SSL_KEYFILE,
    UVICORN_HOST,
    UVICORN_PORT,
    NOTIFICATION_TELEGRAM_BOT_TOKEN,
    NOTIFICATION_TELEGRAM_CHAT_ID,
    config_uvicorn_log,
    logger,
)

app = FastAPI(
    title="MoGuardCore API",
    version="0.13.0",
    docs_url="/docs",
    description="MoGuardCore API Documentation",
)


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
def validation_exception_handler(request: Request, exc: RequestValidationError):
    details = {}
    for error in exc.errors():
        details[error["loc"][-1]] = error.get("msg")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=jsonable_encoder({"detail": details}),
    )


async def main():
    cfg = Config(
        app=app,
        host=UVICORN_HOST,
        port=UVICORN_PORT,
        log_config=config_uvicorn_log(),
        workers=1,
    )
    if UVICORN_SSL_CERTFILE and UVICORN_SSL_KEYFILE:
        cfg.ssl_certfile = UVICORN_SSL_CERTFILE
        cfg.ssl_keyfile = UVICORN_SSL_KEYFILE
        logger.info("SSL configuration loaded successfully")

    logger.info("Caching configs on startup")
    for i in range(5):
        success = await update_configs_task()
        if not success:
            break
    logger.info("Configs cached successfully")
    logger.info("Caching links on startup")
    for i in range(5):
        success = await update_links_task()
        if success:
            break
    logger.info("Links cached successfully")
    async with GetDB() as db:
        admins = await Admin.get_all(db)
        AdminCache.set_all(admins)
        logger.info(f"Cached {len(admins)} admins on startup")
    TaskManager.start()
    logger.info("Scheduler started successfully")
    await upsert_access()
    logger.info("Initial node access upsert completed")
    if NOTIFICATION_TELEGRAM_BOT_TOKEN and NOTIFICATION_TELEGRAM_CHAT_ID:
        logger.info("Telegram notifications are enabled")
        await NotificationService.startup()

    server = Server(cfg)
    logger.info(f"Starting server on {UVICORN_HOST}:{UVICORN_PORT}")
    await server.serve()


@app.on_event("shutdown")
async def on_shutdown():
    """Actions to perform on application shutdown."""
    if TaskManager.running:
        TaskManager.shutdown()
    await GuardNodeManager.close()
    logger.info("GuardNodeManager closed")
    await asyncio.sleep(0.5)
    logger.info("Scheduler stopped successfully")
