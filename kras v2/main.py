from fastapi import FastAPI, Request, Form, File, UploadFile, HTTPException, Depends, APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Optional
import motor.motor_asyncio
from passlib.context import CryptContext
import os
import re
from datetime import datetime
import json
import traceback
from bson import ObjectId
import secrets

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

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

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

def get_seats_per_row_for_sector_201(row):
    if row <= 14:
        return 35
    elif row == 15:
        return 35
    elif row == 16:
        return 34
    elif row == 17:
        return 33
    elif row == 18:
        return 32
    elif row == 19:
        return 31
    elif row == 20:
        return 30
    elif row == 21:
        return 29
    elif row == 22:
        return 28
    elif row == 23:
        return 27
    elif row == 24:
        return 26
    return 0

admin_router = APIRouter()

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    matches = await matches_collection.find().to_list(1000)
    matches = convert_objectid_to_str(matches)
    return templates.TemplateResponse("index.html", {"request": request, "matches": matches})

@app.get("/matches", response_class=HTMLResponse)
async def read_matches(request: Request):
    matches = await matches_collection.find().to_list(1000)
    matches = convert_objectid_to_str(matches)
    return templates.TemplateResponse("matches.html", {"request": request, "matches": matches})

@app.get("/stadium", response_class=HTMLResponse)
async def stadium(request: Request):
    return templates.TemplateResponse("stadium.html", {"request": request})

@app.get("/tickets/{match_id}", response_class=HTMLResponse)
async def get_tickets(request: Request, match_id: str):
    match = await matches_collection.find_one({"id": match_id})
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    match = convert_objectid_to_str(match)
    return templates.TemplateResponse("tickets.html", {"request": request, "match": match})

@app.get("/sector_view/{match_id}/{sector_name}", response_class=HTMLResponse)
async def get_sector_view(request: Request, match_id: str, sector_name: str):
    match = await matches_collection.find_one({"id": match_id})
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    match = convert_objectid_to_str(match)
    for sector in match["sectors"]:
        if sector["name"] == sector_name:
            if not sector.get("seats"):
                raise HTTPException(status_code=400, detail="No seats available in this sector")
            return templates.TemplateResponse("sector_view.html", {
                "request": request,
                "match": match,
                "sector_name": sector_name,
                "sector": sector
            })
    raise HTTPException(status_code=404, detail="Sector not found")

@app.get("/check_seat/{match_id}/{sector_name}/{row}/{seat}", response_class=JSONResponse)
async def check_seat(match_id: str, sector_name: str, row: int, seat: int):
    match = await matches_collection.find_one({"id": match_id})
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    for sector in match["sectors"]:
        if sector["name"] == sector_name:
            seat_number = (row - 1) * 35 + seat
            for st in sector["seats"]:
                if st["number"] == seat_number:
                    return {"available": st["available"]}
            return {"available": False}
    raise HTTPException(status_code=404, detail="Sector not found")

@app.post("/sector_view/{match_id}/{sector_name}/select_seat", response_class=HTMLResponse)
async def select_seat(match_id: str, sector_name: str, row: int = Form(...), seat: int = Form(...)):
    match = await matches_collection.find_one({"id": match_id})
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
    return RedirectResponse(url=f"/sector_view/{match_id}/{sector_name}", status_code=303)

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
            match = await matches_collection.find_one({"id": match_id})
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
                                st["available"] = False
                                break
                        else:
                            raise HTTPException(status_code=404, detail=f"Seat {seat_number} not found in sector")
                    break
            else:
                raise HTTPException(status_code=404, detail=f"Sector not found: {sector_name}")
            await matches_collection.update_one({"id": match_id}, {"$set": {"sectors": match["sectors"]}})
            for seat_info in seats:
                order = {
                    "match_id": match_id,
                    "name": name,
                    "email": email,
                    "phone": phone,
                    "sector": sector_name,
                    "seat": (seat_info["row"] - 1) * 35 + seat_info["seat"],
                    "timestamp": datetime.utcnow()
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
            "timestamp": datetime.utcnow()
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
    admin = await admins_collection.find_one({"username": username})
    if not admin or not verify_password(password, admin["password_hash"]):
        response = templates.TemplateResponse("admin_login.html", {"request": request, "error": "Неверный логин или пароль"})
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
    admin: dict = Depends(check_auth)
):
    query = {}
    if tournament and tournament != "Все лиги":
        query["tournament"] = tournament
    if date:
        query["date"] = date
    matches = await matches_collection.find(query).to_list(1000)
    matches = convert_objectid_to_str(matches)
    return templates.TemplateResponse("admin_panel.html", {
        "request": request,
        "matches": matches,
        "username": admin["username"]
    })

@admin_router.get("/", response_class=HTMLResponse)
async def admin_panel_root(request: Request, admin: dict = Depends(check_auth)):
    matches = await matches_collection.find().to_list(1000)
    for match in matches:
        if match.get("tournament") == "Кубок регионов":
            match["tournament"] = "Товарищеские матчи"
            await matches_collection.update_one({"id": match["id"]}, {"$set": {"tournament": "Товарищеские матчи"}})
    matches = convert_objectid_to_str(matches)
    response = templates.TemplateResponse("admin_panel.html", {
        "request": request,
        "matches": matches,
        "username": admin["username"]
    })
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

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
    password_hash = pwd_context.hash(password)
    new_admin = {
        "username": username,
        "password_hash": password_hash,
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
            update_data["password_hash"] = pwd_context.hash(password)
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

@admin_router.post("/add_match", response_class=HTMLResponse)
async def add_match(
    request: Request,
    teams: str = Form(...),
    date: str = Form(...),
    time: str = Form(...),
    tournament: str = Form(...),
    image: Optional[UploadFile] = File(None),
    admin: dict = Depends(check_auth)
):
    match_id = str(await matches_collection.count_documents({}) + 1)
    image_filename = "default_match.jpg"  # Устанавливаем дефолтное изображение
    if image and image.filename:  # Проверяем, загружено ли изображение
        image_filename = f"match_{match_id}.jpg"
        with open(f"static/backgrounds/{image_filename}", "wb") as f:
            f.write(await image.read())
    match = {
        "id": match_id,
        "teams": teams,
        "date": date,
        "time": time,
        "tournament": tournament,
        "image": image_filename,
        "sectors": []
    }
    await matches_collection.insert_one(match)
    response = RedirectResponse(url="/admin-panel", status_code=303)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@admin_router.post("/add_sector/{match_id}", response_class=HTMLResponse)
async def add_sector(
    request: Request,
    match_id: str,
    sector_name: str = Form(...),
    rows_and_seats: str = Form(...),
    price: int = Form(...),
    admin: dict = Depends(check_auth)
):
    try:
        match = await matches_collection.find_one({"id": match_id})
        if not match:
            raise HTTPException(status_code=404, detail="Match not found")
        pattern = r'^(\d+:((\d+-\d+)|(\d+))(,\d+:((\d+-\d+)|(\d+)))*)$'
        if not re.match(pattern, rows_and_seats):
            raise HTTPException(status_code=400, detail="Invalid format for rows_and_seats. Use format like '20:14-18,23:16,27'")
        if price <= 0:
            raise HTTPException(status_code=400, detail="Price must be a positive number")
        seats = []
        rows_seats = rows_and_seats.split(",")
        for row_seat in rows_seats:
            row, seat_nums = row_seat.split(":")
            row = int(row)
            if row < 1 or row > 24:
                raise HTTPException(status_code=400, detail=f"Row {row} is out of range (1-24)")
            max_seats = get_seats_per_row_for_sector_201(row) if sector_name == "201" else 35
            seat_nums = seat_nums.split(",")
            for seat in seat_nums:
                if "-" in seat:
                    start, end = map(int, seat.split("-"))
                    if start > end or start < 1 or end > 35:
                        raise HTTPException(status_code=400, detail=f"Seat range {start}-{end} is invalid (must be between 1-35)")
                    for s in range(start, end + 1):
                        if sector_name == "201" and s > max_seats:
                            continue
                        seat_number = (row - 1) * 35 + s
                        seats.append({"number": seat_number, "available": True})
                else:
                    s = int(seat)
                    if s < 1 or s > 35:
                        raise HTTPException(status_code=400, detail=f"Seat {s} is out of range (1-35)")
                    if sector_name == "201" and s > max_seats:
                        continue
                    seat_number = (row - 1) * 35 + s
                    seats.append({"number": seat_number, "available": True})
        if not seats:
            raise HTTPException(status_code=400, detail="No valid seats were added. Check the seat ranges for sector restrictions (e.g., sector 201 has row-specific limits).")
        for sector in match["sectors"]:
            if sector["name"] == sector_name:
                existing_seat_numbers = {seat["number"] for seat in sector["seats"]}
                new_seats = [seat for seat in seats if seat["number"] not in existing_seat_numbers]
                sector["seats"].extend(new_seats)
                sector["price"] = price
                break
        else:
            match["sectors"].append({"name": sector_name, "seats": seats, "price": price})
        await matches_collection.update_one({"id": match_id}, {"$set": {"sectors": match["sectors"]}})
        response = RedirectResponse(url=f"/admin-panel/edit_match/{match_id}", status_code=303)
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    except Exception as e:
        print(f"Error in add_sector: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@admin_router.post("/edit_sector/{match_id}/{sector_name}", response_class=HTMLResponse)
async def edit_sector(
    request: Request,
    match_id: str,
    sector_name: str,
    price: int = Form(...),
    rows_and_seats: Optional[str] = Form(None),
    admin: dict = Depends(check_auth)
):
    match = await matches_collection.find_one({"id": match_id})
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    if price <= 0:
        raise HTTPException(status_code=400, detail="Price must be a positive number")
    seats = []
    if rows_and_seats:
        pattern = r'^(\d+:((\d+-\d+)|(\d+))(,\d+:((\d+-\d+)|(\d+)))*)$'
        if not re.match(pattern, rows_and_seats):
            raise HTTPException(status_code=400, detail="Invalid format for rows_and_seats")
        rows_seats = rows_and_seats.split(",")
        for row_seat in rows_seats:
            row, seat_nums = row_seat.split(":")
            row = int(row)
            if row < 1 or row > 24:
                raise HTTPException(status_code=400, detail=f"Row {row} is out of range (1-24)")
            max_seats = get_seats_per_row_for_sector_201(row) if sector_name == "201" else 35
            seat_nums = seat_nums.split(",")
            for seat in seat_nums:
                if "-" in seat:
                    start, end = map(int, seat.split("-"))
                    if start > end or start < 1 or end > 35:
                        raise HTTPException(status_code=400, detail=f"Seat range {start}-{end} is invalid")
                    for s in range(start, end + 1):
                        if sector_name == "201" and s > max_seats:
                            continue
                        seat_number = (row - 1) * 35 + s
                        seats.append({"number": seat_number, "available": True})
                else:
                    s = int(seat)
                    if s < 1 or s > 35:
                        raise HTTPException(status_code=400, detail=f"Seat {s} is out of range")
                    if sector_name == "201" and s > max_seats:
                        continue
                    seat_number = (row - 1) * 35 + s
                    seats.append({"number": seat_number, "available": True})
    for sector in match["sectors"]:
        if sector["name"] == sector_name:
            if seats:
                existing_seat_numbers = {seat["number"] for seat in sector["seats"]}
                new_seats = [seat for seat in seats if seat["number"] not in existing_seat_numbers]
                sector["seats"].extend(new_seats)
            sector["price"] = price
            break
    else:
        raise HTTPException(status_code=404, detail="Sector not found")
    await matches_collection.update_one({"id": match_id}, {"$set": {"sectors": match["sectors"]}})
    return RedirectResponse(url="/admin-panel", status_code=303)

@admin_router.post("/delete_sector/{match_id}/{sector_name}", response_class=HTMLResponse)
async def delete_sector(
    request: Request,
    match_id: str,
    sector_name: str,
    admin: dict = Depends(check_auth)
):
    match = await matches_collection.find_one({"id": match_id})
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    match["sectors"] = [sector for sector in match["sectors"] if sector["name"] != sector_name]
    await matches_collection.update_one({"id": match_id}, {"$set": {"sectors": match["sectors"]}})
    response = RedirectResponse(url=f"/admin-panel/edit_match/{match_id}", status_code=303)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@admin_router.post("/edit_match/{match_id}", response_class=HTMLResponse)
async def edit_match(
    request: Request,
    match_id: str,
    teams: str = Form(...),
    date: str = Form(...),
    time: str = Form(...),
    tournament: str = Form(...),
    image: Optional[UploadFile] = File(None),
    admin: dict = Depends(check_auth)
):
    match = await matches_collection.find_one({"id": match_id})
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    update_data = {"teams": teams, "date": date, "time": time, "tournament": tournament}
    if image and image.filename:
        if match.get("image"):
            try:
                os.remove(f"static/backgrounds/{match['image']}")
            except FileNotFoundError:
                pass
        image_filename = f"match_{match_id}.jpg"
        with open(f"static/backgrounds/{image_filename}", "wb") as f:
            f.write(await image.read())
        update_data["image"] = image_filename
    await matches_collection.update_one({"id": match_id}, {"$set": update_data})
    response = RedirectResponse(url="/admin-panel", status_code=303)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@admin_router.get("/edit_match/{match_id}", response_class=HTMLResponse)
async def edit_match_form(
    request: Request,
    match_id: str,
    admin: dict = Depends(check_auth)
):
    match = await matches_collection.find_one({"id": match_id})
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
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


@admin_router.delete("/delete_match/{match_id}", response_class=HTMLResponse)
async def delete_match(
    request: Request,
    match_id: str,
    admin: dict = Depends(check_auth)
):
    match = await matches_collection.find_one({"id": match_id})
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    if match.get("image"):
        try:
            image_path = f"static/backgrounds/{match['image']}"
            if match['image'] != "default_match.jpg" and os.path.exists(image_path):
                os.remove(image_path)
        except FileNotFoundError:
            pass
    await matches_collection.delete_one({"id": match_id})
    response = RedirectResponse(url="/admin-panel", status_code=303)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@admin_router.get("/deactivate_seat/{match_id}/{sector_name}/{seat_number}", response_class=RedirectResponse)
async def deactivate_seat(
    request: Request,
    match_id: str,
    sector_name: str,
    seat_number: int,
    admin: dict = Depends(check_auth)
):
    try:
        match = await matches_collection.find_one({"id": match_id})
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
        await matches_collection.update_one({"id": match_id}, {"$set": {"sectors": match["sectors"]}})
        response = RedirectResponse(url=f"/admin-panel/edit_match/{match_id}", status_code=303)
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    except Exception as e:
        print(f"Error in deactivate_seat: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@admin_router.get("/activate_seat/{match_id}/{sector_name}/{seat_number}", response_class=RedirectResponse)
async def activate_seat(
    request: Request,
    match_id: str,
    sector_name: str,
    seat_number: int,
    admin: dict = Depends(check_auth)
):
    try:
        match = await matches_collection.find_one({"id": match_id})
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
        await matches_collection.update_one({"id": match_id}, {"$set": {"sectors": match["sectors"]}})
        response = RedirectResponse(url=f"/admin-panel/edit_match/{match_id}", status_code=303)
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    except Exception as e:
        print(f"Error in activate_seat: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@admin_router.post("/update_seats/{match_id}", response_class=JSONResponse)
async def update_seats(
    request: Request,
    match_id: str,
    admin: dict = Depends(check_auth)
):
    try:
        match = await matches_collection.find_one({"id": match_id})
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
                        for st in sector["seats"]:
                            if st["number"] == seat_number:
                                st["available"] = (new_status == "available")
                                break
                    break
        await matches_collection.update_one(
            {"id": match_id},
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

app.include_router(admin_router, prefix="/admin-panel")