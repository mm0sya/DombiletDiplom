from fastapi import FastAPI, Request, Form, File, UploadFile, HTTPException, Depends, APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Optional
import motor.motor_asyncio
import os
import re
from datetime import datetime, timedelta
import json
import traceback
from bson import ObjectId
import secrets
from cryptography.fernet import Fernet
from dotenv import load_dotenv
import os
from transliterate import translit

load_dotenv()
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
SUPERADMIN_USERNAME = os.getenv("SUPERADMIN_USERNAME")
SUPERADMIN_PASSWORD_ENCRYPTED = os.getenv("SUPERADMIN_PASSWORD_ENCRYPTED")

if not all([ENCRYPTION_KEY, SUPERADMIN_USERNAME, SUPERADMIN_PASSWORD_ENCRYPTED]):
    raise ValueError("Missing required environment variables")

try:
    fernet = Fernet(ENCRYPTION_KEY.encode())
except Exception as e:
    raise ValueError(f"Invalid encryption key: {e}")

app = FastAPI(redirect_slashes=False)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Обработчик ошибок 404
@app.exception_handler(404)
async def not_found_exception_handler(request: Request, exc: HTTPException):
    return templates.TemplateResponse(
        "not_found.html",
        {"request": request},
        status_code=404
    )


try:
    client = motor.motor_asyncio.AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["krasnodar_tickets"]
    matches_collection = db["matches"]
    orders_collection = db["orders"]
    contact_requests_collection = db["contact_requests"]
    admins_collection = db["admins"]  # Новая коллекция для администраторов
    admin_logs_collection = db["admin_logs"]  # Новая коллекция для логов действий superadmin
except Exception as e:
    print(f"Failed to connect to MongoDB: {e}")
    raise

def verify_password(plain_password: str, encrypted_password: str) -> bool:
    try:
        decrypted_password = fernet.decrypt(encrypted_password.encode()).decode()
        return plain_password == decrypted_password
    except Exception:
        return False

def validate_password(password: str) -> bool:
    """Проверка пароля: ≥8 символов, минимум 1 заглавная латинская буква, 1 специальный символ."""
    if len(password) < 8:
        return False
    if not re.search(r"[A-Z]", password):
        return False
    if not re.search(r"[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]", password):
        return False
    if not re.match(r"^[a-zA-Z0-9!@#$%^&*()_+\-=\[\]{}|;:,.<>?]*$", password):
        return False
    return True

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

app.add_middleware(AdminAuthMiddleware)

def convert_objectid_to_str(data):
    if isinstance(data, list):
        return [convert_objectid_to_str(item) for item in data]
    elif isinstance(data, dict):
        return {key: convert_objectid_to_str(value) if key != "_id" else str(value) for key, value in data.items()}
    return data

admin_router = APIRouter()

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    matches = await matches_collection.find({"is_active": True}).to_list(1000)
    matches = convert_objectid_to_str(matches)
    return templates.TemplateResponse("index.html", {"request": request, "matches": matches})

@app.get("/matches", response_class=HTMLResponse)
async def read_matches(request: Request):
    matches = await matches_collection.find({"is_active": True}).to_list(1000)
    matches = convert_objectid_to_str(matches)
    return templates.TemplateResponse("matches.html", {"request": request, "matches": matches})

@app.get("/stadium", response_class=HTMLResponse)
async def stadium(request: Request):
    return templates.TemplateResponse("stadium.html", {"request": request})

@app.get("/tickets/{match_slug}", response_class=HTMLResponse)
async def get_tickets(request: Request, match_slug: str):
    match = await matches_collection.find_one({"slug": match_slug})
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    match = convert_objectid_to_str(match)
    return templates.TemplateResponse("tickets.html", {"request": request, "match": match})

@app.get("/sector_view/{match_slug}/{sector_name}", response_class=HTMLResponse)
async def get_sector_view(request: Request, match_slug: str, sector_name: str):
    match = await matches_collection.find_one({"slug": match_slug})
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    match = convert_objectid_to_str(match)
    for sector in match["sectors"]:
        if sector["name"] == sector_name:
            if not sector.get("seats"):
                raise HTTPException(status_code=400, detail="No seats available in this sector")
            # Чтение SVG-файла
            svg_path = os.path.join("static", "svg", f"{sector_name}.svg")
            try:
                with open(svg_path, encoding="utf-8") as f:
                    svg_code = f.read()
            except Exception:
                svg_code = "<svg><!-- SVG не найден --></svg>"
            # Формируем список доступных мест с полной информацией
            available_seats = [
                {
                    "row": (seat["number"] - 1) // 35 + 1,
                    "seat": (seat["number"] - 1) % 35 + 1,
                    "price": seat["price"],
                    "sector_name": sector_name,
                    "match_id": match["slug"]
                }
                for seat in sector["seats"] if seat["available"]
            ]
            return templates.TemplateResponse("sector_view.html", {
                "request": request,
                "match": match,
                "sector_name": sector_name,
                "sector": sector,
                "svg_code": svg_code,
                "available_seats": available_seats
            })
    raise HTTPException(status_code=404, detail="Sector not found")

@app.get("/check_seat/{match_slug}/{sector_name}/{row}/{seat}", response_class=JSONResponse)
async def check_seat(match_slug: str, sector_name: str, row: int, seat: int):
    match = await matches_collection.find_one({"slug": match_slug})
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    for sector in match["sectors"]:
        if sector["name"] == sector_name:
            seat_number = (row - 1) * 35 + seat
            for st in sector["seats"]:
                if st["number"] == seat_number:
                    return {"available": st["available"], "price": st["price"]}
            return {"available": False}
    raise HTTPException(status_code=404, detail="Sector not found")

@app.post("/sector_view/{match_slug}/{sector_name}/select_seat", response_class=HTMLResponse)
async def select_seat(match_slug: str, sector_name: str, row: int = Form(...), seat: int = Form(...)):
    match = await matches_collection.find_one({"slug": match_slug})
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    for sector in match["sectors"]:
        if sector["name"] == sector_name:
            seat_number = (row - 1) * 35 + seat
            for st in sector["seats"]:
                if st["number"] == seat_number:
                    if not st["available"]:
                        raise HTTPException(status_code=400, detail=f"Seat {seat_number} already taken")
                    break
            else:
                raise HTTPException(status_code=404, detail=f"Seat {seat_number} not found in sector")
            break
    else:
        raise HTTPException(status_code=404, detail="Sector not found")
    return RedirectResponse(url=f"/sector_view/{match_slug}/{sector_name}", status_code=303)

@app.get("/cart", response_class=HTMLResponse)
async def get_cart(request: Request):
    try:
        matches = await matches_collection.find().to_list(1000)
        matches = convert_objectid_to_str(matches)
        return templates.TemplateResponse("cart.html", {
            "request": request,
            "matches": matches
        })
    except Exception as e:
        print(f"Error in get_cart: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to load cart: {str(e)}")

@app.post("/cart/clear", response_class=RedirectResponse)
async def clear_cart():
    return RedirectResponse(url="/cart", status_code=303)

@app.post("/submit_order", response_class=HTMLResponse)
async def submit_order(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    selected_seats: str = Form(...)
):
    try:
        selected_seats = json.loads(selected_seats)
        if not isinstance(selected_seats, list):
            raise ValueError("selected_seats must be a list")
        for seat_info in selected_seats:
            required_fields = ["match_id", "sector_name", "row", "seat", "price"]
            for field in required_fields:
                if field not in seat_info:
                    raise ValueError(f"Missing field {field} in seat_info: {seat_info}")
            if not isinstance(seat_info["match_id"], str):
                raise ValueError(f"match_id must be a string, got {seat_info['match_id']}")
            if not isinstance(seat_info["sector_name"], str):
                raise ValueError(f"sector_name must be a string, got {seat_info['sector_name']}")
            if not isinstance(seat_info["row"], int):
                raise ValueError(f"row must be an integer, got {seat_info['row']}")
            if not isinstance(seat_info["seat"], int):
                raise ValueError(f"seat must be an integer, got {seat_info['seat']}")
            if not isinstance(seat_info["price"], (int, float)):
                raise ValueError(f"price must be a number, got {seat_info['price']}")
        seats_by_match_and_sector = {}
        for seat_info in selected_seats:
            match_id = seat_info["match_id"]
            sector_name = seat_info["sector_name"]
            key = (match_id, sector_name)
            if key not in seats_by_match_and_sector:
                seats_by_match_and_sector[key] = []
            seats_by_match_and_sector[key].append(seat_info)
        for (match_id, sector_name), seats in seats_by_match_and_sector.items():
            match = await matches_collection.find_one({"slug": match_id})
            if not match:
                raise HTTPException(status_code=404, detail=f"Match not found: {match_id}")
            for sector in match["sectors"]:
                if sector["name"] == sector_name:
                    for seat_info in seats:
                        row = seat_info["row"]
                        seat_num = seat_info["seat"]
                        seat_number = (row - 1) * 35 + seat_num
                        for st in sector["seats"]:
                            if st["number"] == seat_number:
                                if not st["available"]:
                                    raise HTTPException(status_code=400, detail=f"Seat {seat_number} already taken")
                                if st["price"] != seat_info["price"]:
                                    raise HTTPException(status_code=400, detail=f"Price mismatch for seat {seat_number}")
                                st["available"] = False
                                break
                        else:
                            raise HTTPException(status_code=404, detail=f"Seat {seat_number} not found in sector")
                    break
            else:
                raise HTTPException(status_code=404, detail=f"Sector not found: {sector_name}")
            await matches_collection.update_one({"slug": match_id}, {"$set": {"sectors": match["sectors"]}})
            for seat_info in seats:
                order = {
                    "match_id": match_id,
                    "name": name,
                    "email": email,
                    "phone": phone,
                    "sector": sector_name,
                    "seat": (seat_info["row"] - 1) * 35 + seat_info["seat"],
                    "price": seat_info["price"],
                    "timestamp": datetime.utcnow() + timedelta(hours=3)
                }
                await orders_collection.insert_one(order)
        return RedirectResponse(url="/cart?success=true", status_code=303)
    except json.JSONDecodeError as e:
        print(f"JSON decode error in submit_order: {str(e)}")
        print(f"Selected seats data: {selected_seats}")
        raise HTTPException(status_code=400, detail=f"Invalid selected_seats format: {str(e)}")
    except ValueError as e:
        print(f"Value error in submit_order: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Invalid data: {str(e)}")
    except Exception as e:
        print(f"Error in submit_order: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.post("/checkout", response_class=RedirectResponse)
async def checkout(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    selected_seats: str = Form(...)
):
    try:
        if not re.match(r'^\+?\d{10,15}$', phone):
            raise HTTPException(status_code=400, detail="Invalid phone number format")
        response = await submit_order(
            request=request,
            name=full_name,
            email=email,
            phone=phone,
            selected_seats=selected_seats
        )
        return response
    except Exception as e:
        print(f"Error in checkout: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.post("/submit_contact", response_class=RedirectResponse)
async def submit_contact(
    request: Request,
    name: str = Form(...),
    phone: str = Form(...),
    email: str = Form(...),
    consent: bool = Form(...)
):
    try:
        if not re.match(r'^[a-zA-Zа-яА-Я\s]+$', name):
            raise HTTPException(status_code=400, detail="Invalid name format")
        if not re.match(r'^\+?\d{10,15}$', phone):
            raise HTTPException(status_code=400, detail="Invalid phone number format")
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            raise HTTPException(status_code=400, detail="Invalid email format")
        if not consent:
            raise HTTPException(status_code=400, detail="Consent is required")
        contact_request = {
            "name": name,
            "phone": phone,
            "email": email,
            "timestamp": datetime.utcnow() + timedelta(hours=3)
        }
        await contact_requests_collection.insert_one(contact_request)
        return RedirectResponse(url="/?success=true", status_code=303)
    except Exception as e:
        print(f"Error in submit_contact: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/admin-panel/login", response_class=HTMLResponse)
async def admin_login(request: Request):
    response = templates.TemplateResponse("admin_login.html", {"request": request})
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.post("/admin-panel/login", response_class=HTMLResponse)
async def admin_login_post(request: Request, username: str = Form(...), password: str = Form(...)):
    # Проверка superadmin
    if username == SUPERADMIN_USERNAME:
        if verify_password(password, SUPERADMIN_PASSWORD_ENCRYPTED):
            auth_token = secrets.token_hex(16)
            # Для superadmin создаем временную запись в MongoDB
            admin = {
                "username": username,
                "role": "superadmin",
                "auth_token": auth_token,
                "password_encrypted": SUPERADMIN_PASSWORD_ENCRYPTED
            }
            await admins_collection.update_one(
                {"username": username},
                {"$set": admin},
                upsert=True
            )
            response = RedirectResponse(url="/admin-panel", status_code=303)
            response.set_cookie(key="auth_token", value=auth_token, httponly=True, secure=False)
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            return response
        else:
            response = templates.TemplateResponse(
                "admin_login.html",
                {"request": request, "error": "Неверный логин или пароль"}
            )
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            return response

    # Проверка admin из MongoDB
    admin = await admins_collection.find_one({"username": username})
    if not admin or not verify_password(password, admin["password_encrypted"]):
        response = templates.TemplateResponse(
            "admin_login.html",
            {"request": request, "error": "Неверный логин или пароль"}
        )
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    auth_token = secrets.token_hex(16)
    await admins_collection.update_one(
        {"_id": admin["_id"]},
        {"$set": {"auth_token": auth_token}}
    )
    response = RedirectResponse(url="/admin-panel", status_code=303)
    response.set_cookie(key="auth_token", value=auth_token, httponly=True, secure=False)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.get("/admin-panel/logout", response_class=RedirectResponse)
async def admin_logout(request: Request):
    auth_token = request.cookies.get("auth_token")
    if auth_token:
        await admins_collection.update_one(
            {"auth_token": auth_token},
            {"$unset": {"auth_token": ""}}
        )
    response = RedirectResponse(url="/admin-panel/login", status_code=303)
    response.delete_cookie("auth_token")
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@admin_router.get("", response_class=HTMLResponse)
async def admin_panel(
    request: Request,
    tournament: Optional[str] = None,
    date: Optional[str] = None,
    show_inactive: Optional[str] = None,
    admin: dict = Depends(check_auth)
):
    query = {}
    if tournament and tournament != "Все лиги":
        query["tournament"] = tournament
    if date:
        query["date"] = date
    show_inactive_bool = str(show_inactive).lower() in ['1', 'true', 'yes']
    if not show_inactive_bool:
        query["is_active"] = {"$eq": True}
    matches = await matches_collection.find(query).to_list(1000)
    # Проверка и обновление статуса матчей
    for match in matches:
        if match.get('date'):
            try:
                match_date = datetime.strptime(match['date'], '%Y-%m-%d')
                if match_date < datetime.now():
                    await matches_collection.update_one(
                        {"id": match["id"]},
                        {"$set": {"is_active": False}}
                    )
                    match['is_active'] = False
            except ValueError:
                pass
    if not show_inactive_bool:
        matches = [m for m in matches if m.get('is_active') is True]
    matches = convert_objectid_to_str(matches)
    return templates.TemplateResponse("admin_panel.html", {
        "request": request,
        "matches": matches,
        "username": admin["username"]
    })

@admin_router.get("/set-admin/", response_class=HTMLResponse)
@admin_router.get("/set-admin", response_class=HTMLResponse)
async def set_admin(request: Request, admin: dict = Depends(check_auth)):
    if admin["role"] != "superadmin":
        raise HTTPException(status_code=403, detail="Access denied: superadmin role required")
    admins = await admins_collection.find().to_list(1000)
    admins = convert_objectid_to_str(admins)
    response = templates.TemplateResponse("set_admin.html", {
        "request": request,
        "admins": admins,
        "username": admin["username"]
    })
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@admin_router.post("/set-admin/create", response_class=RedirectResponse)
async def create_admin(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    admin: dict = Depends(check_auth)
):
    if admin["role"] != "superadmin":
        raise HTTPException(status_code=403, detail="Access denied: superadmin role required")
    if not re.match(r"^[a-zA-Z0-9_-]+$", username):
        raise HTTPException(status_code=400, detail="Username must contain only Latin letters, digits, underscores, or hyphens")
    if not validate_password(password):
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters long, contain at least one uppercase Latin letter and one special character")
    existing_admin = await admins_collection.find_one({"username": username})
    if existing_admin:
        raise HTTPException(status_code=400, detail="Username already exists")
    password_encrypted = fernet.encrypt(password.encode()).decode()
    new_admin = {
        "username": username,
        "password_encrypted": password_encrypted,
        "role": "admin"
    }
    result = await admins_collection.insert_one(new_admin)
    await admin_logs_collection.insert_one({
        "admin_id": admin["_id"],
        "action": "create_user",
        "details": {"username": username, "role": "admin", "new_admin_id": result.inserted_id},
        "timestamp": datetime.utcnow()
    })
    response = RedirectResponse(url="/admin-panel/set-admin", status_code=303)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@admin_router.get("/set-admin/edit/{id}", response_class=HTMLResponse)
async def edit_admin_form(request: Request, id: str, admin: dict = Depends(check_auth)):
    if admin["role"] != "superadmin":
        raise HTTPException(status_code=403, detail="Access denied: superadmin role required")
    try:
        admin_data = await admins_collection.find_one({"_id": ObjectId(id)})
        if not admin_data:
            raise HTTPException(status_code=404, detail="Admin not found")
        admin_data = convert_objectid_to_str(admin_data)
        response = templates.TemplateResponse("edit_admin.html", {
            "request": request,
            "admin_data": admin_data,
            "username": admin["username"]
        })
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid admin ID: {str(e)}")

@admin_router.post("/set-admin/edit/{id}", response_class=RedirectResponse)
async def edit_admin(
    request: Request,
    id: str,
    username: str = Form(...),
    password: str = Form(None),
    admin: dict = Depends(check_auth)
):
    if admin["role"] != "superadmin":
        raise HTTPException(status_code=403, detail="Access denied: superadmin role required")
    try:
        existing_admin = await admins_collection.find_one({"_id": ObjectId(id)})
        if not existing_admin:
            raise HTTPException(status_code=404, detail="Admin not found")
        if not re.match(r"^[a-zA-Z0-9_-]+$", username):
            raise HTTPException(status_code=400, detail="Username must contain only Latin letters, digits, underscores, or hyphens")
        if username != existing_admin["username"]:
            username_check = await admins_collection.find_one({"username": username})
            if username_check:
                raise HTTPException(status_code=400, detail="Username already exists")
        update_data = {"username": username}
        log_details = {"old_username": existing_admin["username"], "new_username": username}
        if password:
            if not validate_password(password):
                raise HTTPException(status_code=400, detail="Password must be at least 8 characters long, contain at least one uppercase Latin letter and one special character")
            update_data["password_encrypted"] = fernet.encrypt(password.encode()).decode()
            log_details["password_changed"] = True
        await admins_collection.update_one({"_id": ObjectId(id)}, {"$set": update_data})
        await admin_logs_collection.insert_one({
            "admin_id": admin["_id"],
            "action": "edit_user",
            "details": log_details,
            "timestamp": datetime.utcnow()
        })
        response = RedirectResponse(url="/admin-panel/set-admin", status_code=303)
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid admin ID or data: {str(e)}")

@admin_router.delete("/set-admin/delete/{id}", response_class=RedirectResponse)
async def delete_admin(request: Request, id: str, admin: dict = Depends(check_auth)):
    if admin["role"] != "superadmin":
        raise HTTPException(status_code=403, detail="Access denied: superadmin role required")
    try:
        admin_data = await admins_collection.find_one({"_id": ObjectId(id)})
        if not admin_data:
            raise HTTPException(status_code=404, detail="Admin not found")
        if admin_data["role"] == "superadmin":
            raise HTTPException(status_code=403, detail="Cannot delete superadmin")
        await admins_collection.delete_one({"_id": ObjectId(id)})
        await admin_logs_collection.insert_one({
            "admin_id": admin["_id"],
            "action": "delete_user",
            "details": {"username": admin_data["username"], "role": admin_data["role"]},
            "timestamp": datetime.utcnow()
        })
        response = RedirectResponse(url="/admin-panel/set-admin", status_code=303)
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid admin ID: {str(e)}")

SECTOR_LIST = [
    '101', '102', '103', '104', '105', '106', '107', '108', '110', '111', '112', '113', '114', '115', '116', '117', '118', '119', '120', '122', '123', '124',
    '201', '202', '203', '204', '205', '206', '207', '208', '209', '210', '211', '212', '213', '214', '215', '216', '217', '218', '219', '220', '221', '222', '223', '224'
]

@app.get("/admin-panel/bulk_add_sectors/{match_slug}", response_class=HTMLResponse)
async def bulk_add_sectors_form(request: Request, match_slug: str, admin: dict = Depends(check_auth)):
    match = await matches_collection.find_one({"slug": match_slug})
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    return templates.TemplateResponse(
        "bulk_add_sectors.html",
        {"request": request, "match": match, "sectors": SECTOR_LIST}
    )

@app.post("/admin-panel/bulk_add_sectors/{match_slug}", response_class=RedirectResponse)
async def bulk_add_sectors(
    request: Request,
    match_slug: str,
    admin: dict = Depends(check_auth)
):
    form = await request.form()
    sector_names = form.getlist("sector_name")
    rows = form.getlist("row")
    places = form.getlist("places")
    prices = form.getlist("price")

    match = await matches_collection.find_one({"slug": match_slug})
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    for sector_name, row, places_str, price in zip(sector_names, rows, places, prices):
        seat_numbers = []
        for part in places_str.split(","):
            if "-" in part:
                start, end = map(int, part.split("-"))
                seat_numbers.extend(range(start, end + 1))
            else:
                seat_numbers.append(int(part))
        # Создаём места с индивидуальной ценой
        seats = [{"number": (int(row) - 1) * 35 + s, "available": True, "price": int(price)} for s in seat_numbers]
        for sector in match["sectors"]:
            if sector["name"] == sector_name:
                # Добавляем новые места, сохраняя существующие
                existing_seat_numbers = {seat["number"] for seat in sector["seats"]}
                seats = [seat for seat in seats if seat["number"] not in existing_seat_numbers]
                sector["seats"].extend(seats)
                break
        else:
            match["sectors"].append({"name": sector_name, "seats": seats})
    await matches_collection.update_one({"slug": match_slug}, {"$set": {"sectors": match["sectors"]}})
    return RedirectResponse(url=f"/admin-panel/edit_match/{match_slug}", status_code=303)

@admin_router.post("/add_match", response_class=HTMLResponse)
async def add_match(
    request: Request,
    teams: str = Form(...),
    date: str = Form(...),
    time: str = Form(...),
    tournament: str = Form(...),
    slug: str = Form(None),
    image: Optional[UploadFile] = File(None),
    admin: dict = Depends(check_auth)
):
    match_id = str(await matches_collection.count_documents({}) + 1)
    image_filename = "default_match.jpg"
    if image and image.filename:
        image_filename = f"match_{match_id}.jpg"
        with open(f"static/backgrounds/{image_filename}", "wb") as f:
            f.write(await image.read())
    if not slug or slug.strip() == "":
        slug = translit(teams, 'ru', reversed=True).lower().replace(' ', '-').replace(':', '-').replace('/', '-')
    match = {
        "id": match_id,
        "teams": teams,
        "date": date,
        "time": time,
        "tournament": tournament,
        "image": image_filename,
        "sectors": [],
        "is_active": True,
        "slug": slug
    }
    await matches_collection.insert_one(match)
    response = RedirectResponse(url="/admin-panel", status_code=303)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@admin_router.get("/edit_match/{match_slug}", response_class=HTMLResponse)
async def edit_match_form(
    request: Request,
    match_slug: str,
    admin: dict = Depends(check_auth)
):
    match = await matches_collection.find_one({"slug": match_slug})
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    # Проверка даты матча
    if match.get('date'):
        try:
            match_date = datetime.strptime(match['date'], '%Y-%m-%d')
            if match_date < datetime.now():
                await matches_collection.update_one(
                    {"slug": match_slug},
                    {"$set": {"is_active": False}}
                )
                match['is_active'] = False
        except ValueError:
            pass
    match = convert_objectid_to_str(match)
    response = templates.TemplateResponse("edit_match.html", {
        "request": request,
        "match": match,
        "username": admin["username"]
    })
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@admin_router.post("/edit_match/{match_slug}", response_class=HTMLResponse)
async def edit_match(
    request: Request,
    match_slug: str,
    teams: str = Form(...),
    date: str = Form(...),
    time: str = Form(...),
    tournament: str = Form(...),
    is_active: bool = Form(False),
    slug: str = Form(None),
    image: Optional[UploadFile] = File(None),
    admin: dict = Depends(check_auth)
):
    match = await matches_collection.find_one({"slug": match_slug})
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    update_data = {"teams": teams, "date": date, "time": time, "tournament": tournament, "is_active": is_active}
    if not slug or slug.strip() == "":
        slug = translit(teams, 'ru', reversed=True).lower().replace(' ', '-').replace(':', '-').replace('/', '-')
    update_data["slug"] = slug
    if image and image.filename:
        if match.get("image"):
            try:
                os.remove(f"static/backgrounds/{match['image']}")
            except FileNotFoundError:
                pass
        image_filename = f"match_{match['id']}.jpg"
        with open(f"static/backgrounds/{image_filename}", "wb") as f:
            f.write(await image.read())
        update_data["image"] = image_filename
    await matches_collection.update_one({"slug": match_slug}, {"$set": update_data})
    response = RedirectResponse(url="/admin-panel", status_code=303)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@admin_router.delete("/delete_match/{match_slug}", response_class=HTMLResponse)
async def delete_match(
    request: Request,
    match_slug: str,
    admin: dict = Depends(check_auth)
):
    match = await matches_collection.find_one({"slug": match_slug})
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    if match.get("image"):
        try:
            image_path = f"static/backgrounds/{match['image']}"
            if match['image'] != "default_match.jpg" and os.path.exists(image_path):
                os.remove(image_path)
        except FileNotFoundError:
            pass
    await matches_collection.delete_one({"slug": match_slug})
    response = RedirectResponse(url="/admin-panel", status_code=303)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@admin_router.get("/deactivate_seat/{match_slug}/{sector_name}/{seat_number}", response_class=RedirectResponse)
async def deactivate_seat(
    request: Request,
    match_slug: str,
    sector_name: str,
    seat_number: int,
    admin: dict = Depends(check_auth)
):
    try:
        match = await matches_collection.find_one({"slug": match_slug})
        if not match:
            raise HTTPException(status_code=404, detail="Match not found")
        for sector in match["sectors"]:
            if sector["name"] == sector_name:
                for st in sector["seats"]:
                    if st["number"] == seat_number:
                        st["available"] = False
                        break
                else:
                    raise HTTPException(status_code=404, detail=f"Seat {seat_number} not found in sector")
                break
        else:
            raise HTTPException(status_code=404, detail="Sector not found")
        await matches_collection.update_one({"slug": match_slug}, {"$set": {"sectors": match["sectors"]}})
        response = RedirectResponse(url=f"/admin-panel/edit_match/{match_slug}", status_code=303)
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    except Exception as e:
        print(f"Error in deactivate_seat: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@admin_router.get("/activate_seat/{match_slug}/{sector_name}/{seat_number}", response_class=RedirectResponse)
async def activate_seat(
    request: Request,
    match_slug: str,
    sector_name: str,
    seat_number: int,
    admin: dict = Depends(check_auth)
):
    try:
        match = await matches_collection.find_one({"slug": match_slug})
        if not match:
            raise HTTPException(status_code=404, detail="Match not found")
        for sector in match["sectors"]:
            if sector["name"] == sector_name:
                for st in sector["seats"]:
                    if st["number"] == seat_number:
                        st["available"] = True
                        break
                else:
                    raise HTTPException(status_code=404, detail=f"Seat {seat_number} not found in sector")
                break
        else:
            raise HTTPException(status_code=404, detail="Sector not found")
        await matches_collection.update_one({"slug": match_slug}, {"$set": {"sectors": match["sectors"]}})
        response = RedirectResponse(url=f"/admin-panel/edit_match/{match_slug}", status_code=303)
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    except Exception as e:
        print(f"Error in activate_seat: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@admin_router.post("/update_seats/{match_slug}", response_class=JSONResponse)
async def update_seats(
    request: Request,
    match_slug: str,
    admin: dict = Depends(check_auth)
):
    try:
        match = await matches_collection.find_one({"slug": match_slug})
        if not match:
            raise HTTPException(status_code=404, detail="Match not found")
        data = await request.json()
        seat_changes = data.get("seat_changes", {})
        total_seats = data.get("total_seats")
        if total_seats is None:
            raise HTTPException(status_code=400, detail="total_seats is required")
        if not isinstance(total_seats, int) or total_seats < 0:
            raise HTTPException(status_code=400, detail="total_seats must be a non-negative integer")
        for sector_name, seats in seat_changes.items():
            for sector in match["sectors"]:
                if sector["name"] == sector_name:
                    for seat_number, change in seats.items():
                        seat_number = int(seat_number)
                        new_status = change["status"]
                        new_price = change.get("price")
                        for st in sector["seats"]:
                            if st["number"] == seat_number:
                                st["available"] = (new_status == "available")
                                if new_price is not None:
                                    st["price"] = new_price
                                break
                    break
        await matches_collection.update_one(
            {"slug": match_slug},
            {"$set": {"sectors": match["sectors"], "total_seats": total_seats}}
        )
        return {"status": "success"}
    except json.JSONDecodeError as e:
        print(f"JSON decode error in update_seats: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Invalid JSON format: {str(e)}")
    except Exception as e:
        print(f"Error in update_seats: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@admin_router.post("/delete_sector/{match_slug}/{sector_name}", response_class=RedirectResponse)
async def delete_sector(request: Request, match_slug: str, sector_name: str, admin: dict = Depends(check_auth)):
    match = await matches_collection.find_one({"slug": match_slug})
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    sectors = match.get("sectors", [])
    new_sectors = [sector for sector in sectors if sector["name"] != sector_name]
    await matches_collection.update_one({"slug": match_slug}, {"$set": {"sectors": new_sectors}})
    return RedirectResponse(url=f"/admin-panel/edit_match/{match_slug}", status_code=303)

@admin_router.post("/update_seat_price/{match_slug}/{sector_name}/{seat_number}", response_class=JSONResponse)
async def update_seat_price(
    request: Request,
    match_slug: str,
    sector_name: str,
    seat_number: int,
    admin: dict = Depends(check_auth)
):
    try:
        data = await request.json()
        new_price = data.get("price")
        if new_price is None or not isinstance(new_price, (int, float)) or new_price <= 0:
            raise HTTPException(status_code=400, detail="Некорректная цена")
        match = await matches_collection.find_one({"slug": match_slug})
        if not match:
            raise HTTPException(status_code=404, detail="Матч не найден")
        for sector in match["sectors"]:
            if sector["name"] == sector_name:
                for seat in sector["seats"]:
                    if seat["number"] == seat_number:
                        seat["price"] = new_price
                        await matches_collection.update_one({"slug": match_slug}, {"$set": {"sectors": match["sectors"]}})
                        return {"status": "success"}
                raise HTTPException(status_code=404, detail="Место не найдено в секторе")
        raise HTTPException(status_code=404, detail="Сектор не найден")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Ошибка: {str(e)}")

app.include_router(admin_router, prefix="/admin-panel")

@app.get("/admin-panel/", include_in_schema=False)
async def redirect_admin_panel():
    return RedirectResponse(url="/admin-panel")