from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update, delete
from backend.app.models.postgres_models import Product
from backend.app.db.postgres import get_db
from pydantic import BaseModel
from typing import List

router = APIRouter(prefix="/products", tags=["products"])

# Pydantic модели для запросов и ответов
class ProductCreate(BaseModel):
    name: str
    price: float
    category_id: int
    stock_quantity: int = 0

class ProductUpdate(BaseModel):
    name: str | None = None
    price: float | None = None
    category_id: int | None = None
    stock_quantity: int | None = None

class ProductResponse(ProductCreate):
    id: int

    class Config:
        from_attributes = True

# CRUD операции
@router.get("/", response_model=List[ProductResponse])
async def get_products(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Product))
    return result.scalars().all()

@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(product_id: int, db: AsyncSession = Depends(get_db)):
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product

@router.post("/", response_model=ProductResponse, status_code=201)
async def create_product(product_data: ProductCreate, db: AsyncSession = Depends(get_db)):
    product = Product(**product_data.model_dump())
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product

@router.put("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: int, 
    product_data: ProductUpdate, 
    db: AsyncSession = Depends(get_db)
):
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    update_data = product_data.model_dump(exclude_unset=True)
    await db.execute(
        update(Product)
        .where(Product.id == product_id)
        .values(**update_data)
    )
    await db.commit()
    
    # Получаем обновленный продукт
    updated_product = await db.get(Product, product_id)
    return updated_product

@router.patch("/{product_id}", response_model=ProductResponse)
async def partial_update_product(
    product_id: int, 
    product_data: ProductUpdate, 
    db: AsyncSession = Depends(get_db)
):
    # Для PATCH используем ту же логику, что и для PUT
    return await update_product(product_id, product_data, db)

@router.delete("/{product_id}", status_code=204)
async def delete_product(product_id: int, db: AsyncSession = Depends(get_db)):
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    await db.execute(
        delete(Product)
        .where(Product.id == product_id)
    )
    await db.commit()
    return None