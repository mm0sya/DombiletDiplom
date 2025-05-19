from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.database.mongodb import admins_collection

async def check_auth(request: Request):
    auth_token = request.cookies.get("auth_token")
    if not auth_token:
        response = RedirectResponse(url="/admin-panel/login", status_code=303)
        response.delete_cookie("auth_token")
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    admin = await admins_collection.find_one({"auth_token": auth_token})
    if not admin:
        response = RedirectResponse(url="/admin-panel/login", status_code=303)
        response.delete_cookie("auth_token")
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    return admin

class AdminAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        url_path = request.url.path
        if url_path in ["/admin-panel/login", "/admin-panel/logout"]:
            response = await call_next(request)
            return response
        if url_path.startswith("/admin-panel"):
            auth_token = request.cookies.get("auth_token")
            if not auth_token:
                response = RedirectResponse(url="/admin-panel/login", status_code=303)
                response.delete_cookie("auth_token")
                response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
                response.headers["Pragma"] = "no-cache"
                response.headers["Expires"] = "0"
                return response
            admin = await admins_collection.find_one({"auth_token": auth_token})
            if not admin:
                response = RedirectResponse(url="/admin-panel/login", status_code=303)
                response.delete_cookie("auth_token")
                response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
                response.headers["Pragma"] = "no-cache"
                response.headers["Expires"] = "0"
                return response
            if url_path.startswith("/admin-panel/set-admin") and admin["role"] != "superadmin":
                raise HTTPException(status_code=403, detail="Access denied: superadmin role required")
        response = await call_next(request)
        return response