from fastapi_users import FastAPIUsers
from fastapi_users.authentication import CookieTransport, JWTStrategy
from fastapi_users.db import SQLAlchemyUserDatabase
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.models.postgres_models import Customer
from backend.app.db.postgres import get_db

cookie_transport = CookieTransport(cookie_max_age=3600)

SECRET = "85b2e20c8346f60429d10afd6e5a3bea6f7afd0e0cd727b6616c5d58c3a03785"  # Замените на безопасный ключ

def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(secret=SECRET, lifetime_seconds=3600)

fastapi_users = FastAPIUsers[Customer, int](
    lambda db: SQLAlchemyUserDatabase(db, Customer),
    [cookie_transport],
    get_jwt_strategy,
)

def get_user_manager(db: AsyncSession = Depends(get_db)):
    return fastapi_users.get_user_manager(db)