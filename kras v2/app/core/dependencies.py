from fastapi import Depends, HTTPException, Request
from app.api.middlewares.auth import check_auth

# Пример зависимости для получения текущего администратора
async def get_current_admin(request: Request):
    admin = await check_auth(request)
    if not admin:
        raise HTTPException(status_code=403, detail="Access denied: superadmin role required")
    return admin

# Здесь можно добавить другие зависимости, например, для подключения к базе
