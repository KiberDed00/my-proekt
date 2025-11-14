from fastapi import FastAPI, HTTPException, Depends, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
from typing import List, Optional
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from datetime import datetime
import logging
from contextlib import contextmanager

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="TechStore API",
    version="1.0.0",
    description="## API для управления товарами интернет-магазина TechStore\n\n### Возможности:\n- ✅ Полный CRUD для товаров\n- ✅ Сортировка и фильтрация\n- ✅ Пагинация\n- ✅ Валидация данных\n- ✅ Защита от SQL-инъекций",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware для GitHub Codespaces
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Разрешаем все origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Модели Pydantic
class ProductBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Название товара")
    price: float = Field(..., gt=0, description="Цена товара (должна быть больше 0)")
    category: str = Field(..., min_length=1, max_length=100, description="Категория товара")
    description: Optional[str] = Field(None, description="Описание товара")

    @validator('price')
    def validate_price(cls, v):
        if v <= 0:
            raise ValueError('Price must be greater than 0')
        return round(v, 2)

    class Config:
        schema_extra = {
            "example": {
                "name": "iPhone 15 Pro",
                "price": 99999.99,
                "category": "Смартфоны",
                "description": "Флагманский смартфон Apple с камерой 48 МП"
            }
        }

class ProductCreate(ProductBase):
    pass

class Product(ProductBase):
    id: int = Field(..., description="Уникальный идентификатор товара")
    created_at: datetime = Field(..., description="Дата и время создания")

    class Config:
        schema_extra = {
            "example": {
                "id": 1,
                "name": "iPhone 15 Pro",
                "price": 99999.99,
                "category": "Смартфоны",
                "description": "Флагманский смартфон Apple с камерой 48 МП",
                "created_at": "2024-01-15T10:30:00.000Z"
            }
        }

# Конфигурация базы данных для Codespaces
class DatabaseConfig:
    def __init__(self):
        self.host = os.getenv("DB_HOST", "localhost")
        self.database = os.getenv("DB_NAME", "techstore")
        self.user = os.getenv("DB_USER", "postgres")
        self.password = os.getenv("DB_PASSWORD", "password")
        self.port = os.getenv("DB_PORT", "5432")

# Зависимость для получения соединения с БД
@contextmanager
def get_db_connection():
    config = DatabaseConfig()
    conn = None
    try:
        conn = psycopg2.connect(
            host=config.host,
            database=config.database,
            user=config.user,
            password=config.password,
            port=config.port,
            cursor_factory=RealDictCursor
        )
        logger.info("Successfully connected to database")
        yield conn
    except psycopg2.OperationalError as e:
        logger.error(f"Database connection error: {e}")
        raise HTTPException(
            status_code=503,
            detail="Database connection unavailable"
        )
    except Exception as e:
        logger.error(f"Unexpected database error: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )
    finally:
        if conn:
            conn.close()

def get_db():
    with get_db_connection() as conn:
        yield conn

# Валидация параметров сортировки
ALLOWED_SORT_FIELDS = {
    'id', 'name', 'price', 'category', 'created_at'
}

def validate_sort_field(sort_field: str) -> str:
    """Валидация и преобразование поля для сортировки"""
    field = sort_field.lower().replace('_desc', '').replace('_asc', '')
    
    if field not in ALLOWED_SORT_FIELDS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid sort field. Allowed fields: {', '.join(ALLOWED_SORT_FIELDS)}"
        )
    
    if sort_field.endswith('_desc'):
        return f"{field} DESC"
    else:
        return f"{field} ASC"

# Ручки CRUD операций
@app.get(
    "/",
    summary="Корневой эндпоинт",
    description="Возвращает основную информацию о API",
    response_description="Основная информация API"
)
async def root():
    return {"message": "TechStore API", "version": "1.0.0"}

@app.get(
    "/products/",
    response_model=List[Product],
    summary="Получить список товаров",
    description="""## Получение списка товаров с возможностью:
- 📝 Сортировки по различным полям
- 🔍 Фильтрации по категории
- 📄 Пагинации результатов
- 🛡️ Защиты от SQL-инъекций""",
    response_description="Список товаров"
)
async def get_products(
    sort_by: str = Query(
        "id", 
        description="Поле для сортировки. Доступные поля: id, name, price, category, created_at"
    ),
    category: Optional[str] = Query(
        None, 
        description="Фильтр по категории. Например: 'Смартфоны', 'Ноутбуки'"
    ),
    skip: int = Query(
        0, 
        ge=0, 
        description="Количество записей для пропуска (пагинация)"
    ),
    limit: int = Query(
        100, 
        ge=1, 
        le=1000, 
        description="Ограничение количества возвращаемых записей (макс. 1000)"
    ),
    conn = Depends(get_db)
):
    """
    Получить список товаров с возможностью сортировки и фильтрации
    
    - **sort_by**: Поле для сортировки (по умолчанию: id)
    - **category**: Фильтр по категории (опционально)
    - **skip**: Пропустить N записей (пагинация)
    - **limit**: Ограничить количество записей (1-1000)
    """
    try:
        # Безопасная сортировка
        safe_sort = validate_sort_field(sort_by)
        
        query = """
            SELECT id, name, price, category, description, created_at 
            FROM products 
        """
        params = []
        
        # Фильтрация по категории
        if category:
            query += " WHERE category = %s"
            params.append(category)
        
        # Сортировка
        query += f" ORDER BY {safe_sort}"
        
        # Пагинация
        query += " LIMIT %s OFFSET %s"
        params.extend([limit, skip])
        
        with conn.cursor() as cur:
            cur.execute(query, params)
            products = cur.fetchall()
        
        logger.info(f"Retrieved {len(products)} products")
        return products
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving products: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post(
    "/products/",
    response_model=Product,
    status_code=status.HTTP_201_CREATED,
    summary="Создать новый товар",
    description="""## Создание нового товара в базе данных
    
    ### Особенности:
    - ✅ Валидация входных данных
    - ✅ Проверка на дубликаты по имени
    - ✅ Защита от SQL-инъекций
    - ✅ Автоматическое присвоение ID и даты создания""",
    response_description="Созданный товар"
)
async def create_product(
    product: ProductCreate,
    conn = Depends(get_db)
):
    """
    Создать новый товар
    
    - **name**: Название товара (обязательно)
    - **price**: Цена товара (должна быть > 0)
    - **category**: Категория товара (обязательно)
    - **description**: Описание товара (опционально)
    """
    try:
        with conn.cursor() as cur:
            # Проверка на дубликаты по имени
            cur.execute(
                "SELECT id FROM products WHERE name = %s",
                (product.name,)
            )
            if cur.fetchone():
                raise HTTPException(
                    status_code=400,
                    detail="Product with this name already exists"
                )
            
            # Вставка с защитой от SQL-инъекций
            cur.execute("""
                INSERT INTO products (name, price, category, description)
                VALUES (%s, %s, %s, %s)
                RETURNING id, name, price, category, description, created_at
            """, (
                product.name, 
                product.price, 
                product.category, 
                product.description
            ))
            
            new_product = cur.fetchone()
            conn.commit()
            
            logger.info(f"Created new product: {new_product['name']}")
            return new_product
            
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        logger.error(f"Error creating product: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get(
    "/products/{product_id}",
    response_model=Product,
    summary="Получить товар по ID",
    description="Получение информации о конкретном товаре по его идентификатору",
    responses={
        404: {"description": "Товар не найден"},
        200: {"description": "Информация о товаре"}
    }
)
async def get_product(
    product_id: int,
    conn = Depends(get_db)
):
    """
    Получить товар по ID
    
    - **product_id**: ID товара (целое число > 0)
    """
    try:
        # Валидация product_id
        if product_id < 1:
            raise HTTPException(
                status_code=400,
                detail="Product ID must be greater than 0"
            )
            
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, name, price, category, description, created_at
                FROM products 
                WHERE id = %s
            """, (product_id,))
            
            product = cur.fetchone()
            
            if not product:
                raise HTTPException(
                    status_code=404, 
                    detail="Product not found"
                )
            
            return product
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving product {product_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.put(
    "/products/{product_id}",
    response_model=Product,
    summary="Обновить товар",
    description="Полное обновление информации о товаре",
    responses={
        404: {"description": "Товар не найден"},
        400: {"description": "Некорректные данные"},
        200: {"description": "Товар успешно обновлен"}
    }
)
async def update_product(
    product_id: int,
    product: ProductCreate,
    conn = Depends(get_db)
):
    """
    Обновить товар
    
    - **product_id**: ID товара для обновления
    - **Тело запроса**: Новые данные товара
    """
    try:
        # Валидация product_id
        if product_id < 1:
            raise HTTPException(
                status_code=400,
                detail="Product ID must be greater than 0"
            )
            
        with conn.cursor() as cur:
            # Проверка существования товара
            cur.execute("SELECT id FROM products WHERE id = %s", (product_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Product not found")
            
            # Проверка на дубликаты по имени (исключая текущий товар)
            cur.execute(
                "SELECT id FROM products WHERE name = %s AND id != %s",
                (product.name, product_id)
            )
            if cur.fetchone():
                raise HTTPException(
                    status_code=400,
                    detail="Another product with this name already exists"
                )
            
            # Безопасное обновление
            cur.execute("""
                UPDATE products 
                SET name = %s, price = %s, category = %s, description = %s
                WHERE id = %s
                RETURNING id, name, price, category, description, created_at
            """, (
                product.name, 
                product.price, 
                product.category, 
                product.description,
                product_id
            ))
            
            updated_product = cur.fetchone()
            conn.commit()
            
            logger.info(f"Updated product: {updated_product['name']}")
            return updated_product
            
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        logger.error(f"Error updating product {product_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.delete(
    "/products/{product_id}",
    summary="Удалить товар",
    description="Удаление товара из базы данных по ID",
    responses={
        404: {"description": "Товар не найден"},
        200: {"description": "Товар успешно удален"}
    }
)
async def delete_product(
    product_id: int,
    conn = Depends(get_db)
):
    """
    Удалить товар
    
    - **product_id**: ID товара для удаления
    """
    try:
        # Валидация product_id
        if product_id < 1:
            raise HTTPException(
                status_code=400,
                detail="Product ID must be greater than 0"
            )
            
        with conn.cursor() as cur:
            # Проверка существования товара
            cur.execute("SELECT name FROM products WHERE id = %s", (product_id,))
            product = cur.fetchone()
            
            if not product:
                raise HTTPException(status_code=404, detail="Product not found")
            
            # Безопасное удаление
            cur.execute("DELETE FROM products WHERE id = %s", (product_id,))
            conn.commit()
            
            logger.info(f"Deleted product: {product['name']}")
            return {"message": "Product deleted successfully"}
            
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        logger.error(f"Error deleting product {product_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get(
    "/products/sort/{sort_type}",
    response_model=List[Product],
    summary="Сортировка товаров",
    description="""## Специализированные методы сортировки
    
    ### Доступные типы сортировки:
    - **name** - по имени (А-Я)
    - **name_desc** - по имени (Я-А) 
    - **price** - по цене (дешевые first)
    - **price_desc** - по цене (дорогие first)
    - **category** - по категории (А-Я)
    - **category_desc** - по категории (Я-А)
    - **id** - по ID (возрастание)
    - **id_desc** - по ID (убывание)
    - **created** - по дате создания (старые first)
    - **created_desc** - по дате создания (новые first)""",
    response_description="Отсортированный список товаров"
)
async def get_sorted_products(
    sort_type: str,
    category: Optional[str] = Query(None, description="Фильтр по категории"),
    conn = Depends(get_db)
):
    """
    Получить товары с различными вариантами сортировки
    
    - **sort_type**: Тип сортировки (см. описание выше)
    - **category**: Фильтр по категории (опционально)
    """
    try:
        # Безопасное определение типа сортировки
        sort_mapping = {
            "name": "name ASC",
            "name_desc": "name DESC",
            "price": "price ASC", 
            "price_desc": "price DESC",
            "category": "category ASC",
            "category_desc": "category DESC",
            "id": "id ASC",
            "id_desc": "id DESC",
            "created": "created_at ASC",
            "created_desc": "created_at DESC"
        }
        
        if sort_type not in sort_mapping:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid sort type. Allowed: {', '.join(sort_mapping.keys())}"
            )
        
        sort_expression = sort_mapping[sort_type]
        
        query = """
            SELECT id, name, price, category, description, created_at
            FROM products 
        """
        params = []
        
        if category:
            query += " WHERE category = %s"
            params.append(category)
        
        query += f" ORDER BY {sort_expression}"
        
        with conn.cursor() as cur:
            cur.execute(query, params)
            products = cur.fetchall()
        
        return products
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in sorted products: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)