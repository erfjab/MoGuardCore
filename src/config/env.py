from decouple import config
from dotenv import load_dotenv

load_dotenv(override=True)

### Develop Settings
DEBUG = config("DEBUG", default=False, cast=bool)

### Security Settings
JWT_SECRET_KEY = config("JWT_SECRET_KEY", default="", cast=str)

### Database Settings
DATABASE_NAME = config("DATABASE_NAME", default="", cast=str)
DATABASE_USERNAME = config("DATABASE_USERNAME", default="", cast=str)
DATABASE_PASSWORD = config("DATABASE_PASSWORD", default="", cast=str)
DATABASE_HOST = config("DATABASE_HOST", default="localhost", cast=str)
DATABASE_PORT = config("DATABASE_PORT", default=5432, cast=int)
SQLALCHEMY_DATABASE_URL = (
    f"postgresql+asyncpg://{DATABASE_USERNAME}:{DATABASE_PASSWORD}@{DATABASE_HOST}:{DATABASE_PORT}/{DATABASE_NAME}"
)

### Uvicorn Settings
UVICORN_HOST = config("UVICORN_HOST", default="127.0.0.1", cast=str)
UVICORN_PORT = config("UVICORN_PORT", default=8000, cast=int)
UVICORN_SSL_CERTFILE = config("UVICORN_SSL_CERTFILE", default="", cast=str)
UVICORN_SSL_KEYFILE = config("UVICORN_SSL_KEYFILE", default="", cast=str)

### Notification Settings
NOTIFICATION_TELEGRAM_BOT_TOKEN = config("NOTIFICATION_TELEGRAM_BOT_TOKEN", default="", cast=str)
NOTIFICATION_TELEGRAM_CHAT_ID = config("NOTIFICATION_TELEGRAM_CHAT_ID", default="", cast=str)

### MoreBot Settings
MOREBOT_LINCENSE_KEY = config("MOREBOT_LINCENSE_KEY", default="", cast=str)
MOREBOT_SECRET_KEY = config("MOREBOT_SECRET_KEY", default="", cast=str)
