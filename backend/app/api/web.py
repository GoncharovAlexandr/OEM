from fastapi import APIRouter, Request, Form, Depends, HTTPException, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update, delete
from sqlalchemy.sql import func
from backend.app.models.postgres_models import Product, Review, Customer
from backend.app.db.postgres import get_db
from fastapi_users import FastAPIUsers, BaseUserManager
from fastapi_users.authentication import CookieTransport, JWTStrategy, AuthenticationBackend
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from pydantic import EmailStr
from fastapi_users import schemas
from datetime import datetime
from passlib.context import CryptContext
import os
import logging
import asyncio

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация шаблонов
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
logger.info(f"Templates directory set to: {os.path.join(BASE_DIR, 'templates')}")

router = APIRouter()

# Pydantic-схемы для fastapi-users
class UserRead(schemas.BaseUser[int]):
    name: str
    email: EmailStr
    is_admin: bool

class UserCreate(schemas.BaseUserCreate):
    name: str
    email: EmailStr
    is_admin: bool = False

# Настройка авторизации
SECRET = "85b2e20c8346f60429d10afd6e5a3bea6f7afd0e0cd727b6616c5d58c3a03785"
cookie_transport = CookieTransport(cookie_name="auth_cookie", cookie_max_age=3600)

def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(secret=SECRET, lifetime_seconds=3600)

auth_backend = AuthenticationBackend(
    name="jwt",
    transport=cookie_transport,
    get_strategy=get_jwt_strategy,
)

# Настройка passlib
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

# Кастомный менеджер пользователей
class CustomerManager(BaseUserManager[Customer, int]):
    async def on_after_register(self, user: Customer, request: Request | None = None):
        logger.info(f"User {user.email} has registered.")

    def parse_id(self, value: str) -> int:
        try:
            return int(value)
        except ValueError:
            raise ValueError(f"Invalid user ID: {value}")

async def get_user_manager(db: AsyncSession = Depends(get_db)):
    user_db = SQLAlchemyUserDatabase(db, Customer)
    yield CustomerManager(user_db)

fastapi_users = FastAPIUsers[Customer, int](
    get_user_manager,
    [auth_backend],
)

# Проверка админа
async def get_current_admin(user: Customer = Depends(fastapi_users.current_user(active=True))):
    logger.info(f"Checking admin: user={user.email}, is_admin={user.is_admin}")
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

@router.get("/", response_class=HTMLResponse)
async def home(request: Request, user: Customer = Depends(fastapi_users.current_user(optional=True)), db: AsyncSession = Depends(get_db)):
    stmt = select(Product).limit(4)
    result = await db.execute(stmt)
    products = result.scalars().all()
    logger.info(f"Fetched {len(products)} products for home page")
    return templates.TemplateResponse(
        "home.html",
        {
            "request": request,
            "user": user,
            "is_authenticated": user is not None,
            "products": products
        }
    )

@router.get("/products", response_class=HTMLResponse)
async def get_products(
    request: Request,
    query: str = "",
    db: AsyncSession = Depends(get_db),
    user: Customer = Depends(fastapi_users.current_user(optional=True))
):
    stmt = select(Product)
    if query:
        stmt = stmt.filter(Product.name.ilike(f"%{query}%"))
    result = await db.execute(stmt)
    products = result.scalars().all()
    logger.info(f"Products fetched: {len(products)}")
    return templates.TemplateResponse(
        "products.html",
        {
            "request": request,
            "products": products,
            "query": query,
            "user": user,
            "is_authenticated": user is not None
        }
    )

@router.get("/products/new", response_class=HTMLResponse)
async def new_product_form(
    request: Request,
    user: Customer = Depends(get_current_admin)
):
    return templates.TemplateResponse(
        "product_form.html",
        {
            "request": request,
            "title": "Добавить товар",
            "action": "/products/new",
            "button_text": "Создать",
            "user": user,
            "is_authenticated": True
        }
    )

@router.get("/products/{product_id}", response_class=HTMLResponse)
async def get_product(
    request: Request,
    product_id: int,
    db: AsyncSession = Depends(get_db),
    user: Customer = Depends(fastapi_users.current_user(optional=True))
):
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    reviews = (await db.execute(select(Review).filter(Review.product_id == product_id))).scalars().all()
    avg_rating_result = await db.execute(
        select(func.avg(Review.rating)).filter(Review.product_id == product_id)
    )
    avg_rating = avg_rating_result.scalar() or 0
    avg_rating = round(float(avg_rating), 1) if avg_rating else 0
    logger.info(f"Average rating for product {product_id}: {avg_rating}")
    return templates.TemplateResponse(
        "product_detail.html",
        {
            "request": request,
            "product": product,
            "reviews": reviews,
            "avg_rating": avg_rating,
            "user": user,
            "is_authenticated": user is not None
        }
    )

@router.post("/products/new", response_class=RedirectResponse)
async def create_product(
    name: str = Form(...),
    price: float = Form(...),
    category_id: int = Form(...),
    stock_quantity: int = Form(...),
    image: UploadFile = File(None),
    db: AsyncSession = Depends(get_db),
    user: Customer = Depends(get_current_admin)
):
    logger.info(f"Creating product: name={name}, price={price}, category_id={category_id}, stock_quantity={stock_quantity}")
    image_path = None
    if image:
        upload_dir = os.path.join(BASE_DIR, "../static/uploads")
        try:
            os.makedirs(upload_dir, exist_ok=True)
            os.chmod(upload_dir, 0o755)
            logger.info(f"Ensured upload directory exists with 755 permissions: {upload_dir}")
            image_filename = f"{datetime.now().timestamp()}_{image.filename}"
            image_full_path = os.path.join(upload_dir, image_filename)
            # Читаем содержимое файла
            content = await image.read()
            logger.info(f"Image file size: {len(content)} bytes")
            if len(content) == 0:
                logger.error("Image file is empty")
                raise HTTPException(status_code=400, detail="Image file is empty")
            # Записываем файл
            with open(image_full_path, "wb") as buffer:
                buffer.write(content)
            logger.info(f"Image saved to: {image_full_path}")
            # Проверяем существование
            if not os.path.exists(image_full_path):
                logger.error(f"Image file not found after saving: {image_full_path}")
                raise HTTPException(status_code=500, detail="Failed to save image")
            # Проверяем размер файла на диске
            file_size = os.path.getsize(image_full_path)
            logger.info(f"Image file size on disk: {file_size} bytes")
            # Проверяем права
            os.chmod(image_full_path, 0o644)
            logger.info(f"Set permissions to 644 for: {image_full_path}")
            image_path = f"/static/uploads/{image_filename}"
        except Exception as e:
            logger.error(f"Error saving image: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error saving image: {str(e)}")
        finally:
            await image.close()
    product = Product(
        name=name,
        price=price,
        category_id=category_id,
        stock_quantity=stock_quantity,
        image=image_path
    )
    db.add(product)
    await db.commit()
    logger.info("Product created")
    return RedirectResponse(url="/products", status_code=303)

@router.get("/products/edit/{product_id}", response_class=HTMLResponse)
async def edit_product_form(
    request: Request,
    product_id: int,
    db: AsyncSession = Depends(get_db),
    user: Customer = Depends(get_current_admin)
):
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return templates.TemplateResponse(
        "product_form.html",
        {
            "request": request,
            "product": product,
            "title": "Редактировать товар",
            "action": f"/products/edit/{product_id}",
            "button_text": "Обновить",
            "user": user,
            "is_authenticated": True
        }
    )

@router.post("/products/edit/{product_id}", response_class=RedirectResponse)
async def update_product(
    product_id: int,
    name: str = Form(...),
    price: float = Form(...),
    category_id: int = Form(...),
    stock_quantity: int = Form(...),
    image: UploadFile = File(None),
    db: AsyncSession = Depends(get_db),
    user: Customer = Depends(get_current_admin)
):
    logger.info(f"Updating product {product_id}: name={name}, price={price}, category_id={category_id}, stock_quantity={stock_quantity}")
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    image_path = product.image
    if image:
        upload_dir = os.path.join(BASE_DIR, "../static/uploads")
        try:
            os.makedirs(upload_dir, exist_ok=True)
            os.chmod(upload_dir, 0o755)
            logger.info(f"Ensured upload directory exists with 755 permissions: {upload_dir}")
            image_filename = f"{datetime.now().timestamp()}_{image.filename}"
            image_full_path = os.path.join(upload_dir, image_filename)
            # Читаем содержимое файла
            content = await image.read()
            logger.info(f"Image file size: {len(content)} bytes")
            if len(content) == 0:
                logger.error("Image file is empty")
                raise HTTPException(status_code=400, detail="Image file is empty")
            # Записываем файл
            with open(image_full_path, "wb") as buffer:
                buffer.write(content)
            logger.info(f"Image saved to: {image_full_path}")
            # Проверяем существование
            if not os.path.exists(image_full_path):
                logger.error(f"Image file not found after saving: {image_full_path}")
                raise HTTPException(status_code=500, detail="Failed to save image")
            # Проверяем размер файла на диске
            file_size = os.path.getsize(image_full_path)
            logger.info(f"Image file size on disk: {file_size} bytes")
            # Проверяем права
            os.chmod(image_full_path, 0o644)
            logger.info(f"Set permissions to 644 for: {image_full_path}")
            image_path = f"/static/uploads/{image_filename}"
        except Exception as e:
            logger.error(f"Error saving image: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error saving image: {str(e)}")
        finally:
            await image.close()
    await db.execute(
        update(Product)
        .where(Product.id == product_id)
        .values(
            name=name,
            price=price,
            category_id=category_id,
            stock_quantity=stock_quantity,
            image=image_path
        )
    )
    await db.commit()
    logger.info(f"Product {product_id} updated")
    return RedirectResponse(url=f"/products/{product_id}", status_code=303)

@router.post("/products/delete/{product_id}", response_class=RedirectResponse)
async def delete_product(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    user: Customer = Depends(get_current_admin)
):
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    await db.execute(delete(Product).where(Product.id == product_id))
    await db.commit()
    logger.info(f"Product {product_id} deleted")
    return RedirectResponse(url="/products", status_code=303)

@router.post("/cart/add/{product_id}", response_class=RedirectResponse)
async def add_to_cart(
    request: Request,
    product_id: int,
    db: AsyncSession = Depends(get_db),
    user: Customer = Depends(fastapi_users.current_user(optional=True))
):
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    if "cart" not in request.session:
        request.session["cart"] = {}
    cart = request.session["cart"]
    cart[str(product_id)] = cart.get(str(product_id), 0) + 1
    request.session["cart"] = cart
    logger.info(f"Added product {product_id} to cart")
    return RedirectResponse(url="/cart", status_code=303)

@router.get("/cart", response_class=HTMLResponse)
async def view_cart(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: Customer = Depends(fastapi_users.current_user(optional=True))
):
    cart = request.session.get("cart", {})
    products = []
    total = 0
    for product_id, quantity in cart.items():
        product = await db.get(Product, int(product_id))
        if product:
            products.append({"product": product, "quantity": quantity})
            total += product.price * quantity
    logger.info(f"Cart viewed, total items: {len(products)}")
    return templates.TemplateResponse(
        "cart.html",
        {
            "request": request,
            "cart_items": products,
            "total": total,
            "user": user,
            "is_authenticated": user is not None
        }
    )

@router.post("/cart/clear", response_class=RedirectResponse)
async def clear_cart(request: Request):
    request.session["cart"] = {}
    logger.info("Cart cleared")
    return RedirectResponse(url="/cart", status_code=303)

@router.post("/products/{product_id}/review", response_class=RedirectResponse)
async def add_review(
    product_id: int,
    rating: int = Form(...),
    comment: str = Form(...),
    db: AsyncSession = Depends(get_db),
    user: Customer = Depends(fastapi_users.current_user(active=True))
):
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    review = Review(
        product_id=product_id,
        customer_id=user.id,
        rating=rating,
        comment=comment,
        review_date=datetime.utcnow()
    )
    db.add(review)
    await db.commit()
    logger.info(f"Review added for product {product_id}: rating={rating}")
    return RedirectResponse(url=f"/products/{product_id}", status_code=303)

@router.get("/auth/jwt/login", response_class=HTMLResponse)
async def login_form(request: Request):
    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "error": None
        }
    )

@router.post("/auth/jwt/login", response_class=RedirectResponse)
async def login(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user_manager: CustomerManager = Depends(get_user_manager)
):
    try:
        form = await request.form()
        email = form.get("username")
        password = form.get("password")
        logger.info(f"Login attempt: email={email}")
        result = await db.execute(select(Customer).filter(Customer.email.ilike(email)))
        user = result.scalars().first()
        if user is None or not user.is_active:
            logger.warning("Authentication failed: user not found or inactive")
            return templates.TemplateResponse(
                "login.html",
                {
                    "request": request,
                    "error": "Неверный email или пароль"
                }
            )
        if not pwd_context.verify(password, user.hashed_password):
            logger.warning("Authentication failed: incorrect password")
            return templates.TemplateResponse(
                "login.html",
                {
                    "request": request,
                    "error": "Неверный email или пароль"
                }
            )
        logger.info(f"Authenticated user: {user.email}")
        response = RedirectResponse(url="/", status_code=303)
        token = await get_jwt_strategy().write_token(user)
        response.set_cookie(
            key=cookie_transport.cookie_name,
            value=token,
            max_age=cookie_transport.cookie_max_age,
            httponly=True,
        )
        logger.info("Login successful, redirecting to /")
        return response
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": "Произошла ошибка при входе"
            }
        )

@router.post("/auth/jwt/logout", response_class=RedirectResponse)
async def logout(request: Request):
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(key=cookie_transport.cookie_name)
    logger.info("User logged out, redirecting to /")
    return response

@router.get("/auth/register", response_class=HTMLResponse)
async def register_form(request: Request):
    return templates.TemplateResponse(
        "register.html",
        {
            "request": request,
            "error": None
        }
    )

@router.post("/auth/register", response_class=RedirectResponse)
async def register(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user_manager: CustomerManager = Depends(get_user_manager)
):
    try:
        form = await request.form()
        user_data = UserCreate(
            name=form.get("name"),
            email=form.get("email"),
            password=form.get("password"),
            is_admin=False
        )
        await user_manager.create(user_data)
        logger.info(f"User registered: {user_data.email}")
        return RedirectResponse(url="/auth/jwt/login", status_code=303)
    except Exception as e:
        logger.error(f"Registration error: {str(e)}")
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "error": str(e)
            }
        )

@router.get("/create-admin")
async def create_admin(db: AsyncSession = Depends(get_db)):
    user_manager = CustomerManager(SQLAlchemyUserDatabase(db, Customer))
    try:
        user_data = UserCreate(
            name="Admin",
            email="admin@example.com",
            password="admin_password",
            is_admin=True,
            is_active=True,
            is_superuser=False,
            is_verified=False
        )
        await user_manager.create(user_data)
        logger.info("Admin created")
        return {"message": "Admin created"}
    except Exception as e:
        logger.error(f"Error creating admin: {str(e)}")
        return {"message": f"Error creating admin: {str(e)}"}

router.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/auth/jwt",
    tags=["auth"]
)