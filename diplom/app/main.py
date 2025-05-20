from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Optional
import os
import re
from datetime import datetime, timedelta
import json
import traceback
from bson import ObjectId
import secrets
from cryptography.fernet import Fernet
from dotenv import load_dotenv
from transliterate import translit

# Импорт роутеров
from app.api.routers.admin import admin_router
from app.api.routers.cart import cart_router
from app.api.routers.public import public_router
# Импорт middlewares
from app.api.middlewares.auth import AdminAuthMiddleware
# Импорт других необходимых объектов (например, базы данных, шаблонов)
# from app.utils.templates import templates  # Удалить этот импорт, если он есть
from app.database.mongodb import matches_collection, admins_collection, admin_logs_collection, orders_collection, contact_requests_collection
from app.utils.helpers import convert_objectid_to_str
from app.utils.validators import validate_password
from app.core.security import fernet
from app.config import SUPERADMIN_USERNAME, SUPERADMIN_PASSWORD_ENCRYPTED

app = FastAPI(redirect_slashes=False)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

@app.exception_handler(404)
async def not_found_exception_handler(request: Request, exc: HTTPException):
    return templates.TemplateResponse(
        "not_found.html",
        {"request": request},
        status_code=404
    )

app.add_middleware(AdminAuthMiddleware)

app.include_router(public_router)
app.include_router(cart_router)
app.include_router(admin_router, prefix="/admin-panel")