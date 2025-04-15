from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from backend.app.db.postgres import init_db
from backend.app.api.web import router as web_router
from contextlib import asynccontextmanager
import os
import logging
from fastapi_users.authentication import CookieTransport, JWTStrategy, AuthenticationBackend

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Создаём директорию static/uploads
    upload_dir = os.path.join(BASE_DIR, "../static/uploads")
    os.makedirs(upload_dir, exist_ok=True)
    os.chmod(upload_dir, 0o755)
    logger.info(f"Created/verified upload directory: {upload_dir}")
    await init_db()
    yield
    logger.info("Application shutdown")

app = FastAPI(lifespan=lifespan)

# Подключение статических файлов
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "../static")), name="static")
logger.info(f"Static files mounted at: {os.path.join(BASE_DIR, '../static')}")

# Инициализация шаблонов
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
logger.info(f"Templates directory set to: {os.path.join(BASE_DIR, 'templates')}")

# Настройка аутентификации
SECRET = "85b2e20c8346f60429d10afd6e5a3bea6f7afd0e0cd727b6616c5d58c3a03785"

cookie_transport = CookieTransport(cookie_name="auth", cookie_max_age=3600)

def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(secret=SECRET, lifetime_seconds=3600)

auth_backend = AuthenticationBackend(
    name="jwt",
    transport=cookie_transport,
    get_strategy=get_jwt_strategy,
)

# Middleware сессии
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET,
    session_cookie="session"
)

# Подключение маршрутов
app.include_router(web_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)