from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.api import router as api_router
from app.core.config import settings
from app.db.init_db import init_db
from contextlib import asynccontextmanager
from app.core.executor import shutdown_executor

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
    shutdown_executor()
    
app = FastAPI(title="FastAPI Image Processor", lifespan=lifespan)

# --- ИСПРАВЛЕННЫЙ БЛОК CORS ---
origins = [
    "http://localhost:5173",     # Vite Localhost
    "http://127.0.0.1:5173",     # IP версия
    # Если фронтенд запущен на другом порту, добавьте его сюда явно:
    # "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # Разрешаем ЛЮБОЙ источник
    allow_credentials=False,  # ОТКЛЮЧАЕМ проверку кредитов (кук), это снимет строгость
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"] # Это обязательно для скачивания файла
)
# --- КОНЕЦ БЛОКА CORS ---

app.include_router(api_router, prefix="/api/v1")

@app.get("/")
async def root():
    return {"message": "Welcome to the FastAPI Image Processor!"}

import uvicorn
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)