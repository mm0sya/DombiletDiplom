from fastapi import APIRouter, Request, Form, File, UploadFile, Depends, HTTPException, FastAPI
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from typing import Optional
from bson import ObjectId
import re
from datetime import datetime, timedelta
import os
from transliterate import translit
from app.services.admin_service import login_admin, create_admin, edit_admin, delete_admin, bulk_add_sectors, deactivate_seat, activate_seat, update_seats, delete_sector, update_seat_price, delete_seat
from app.utils.exceptions import NotFoundException, BadRequestException, ForbiddenException
from app.core.dependencies import get_current_admin
from app.services.match_service import get_matches, add_match, edit_match, delete_match, get_match_for_edit
from app.database.mongodb import matches_collection, admins_collection, admin_logs_collection
from app.utils.helpers import convert_objectid_to_str
from app.utils.validators import validate_password
from app.core.security import fernet
from app.config import SUPERADMIN_USERNAME, SUPERADMIN_PASSWORD_ENCRYPTED
from fastapi.templating import Jinja2Templates
from pars import parse_match as run_parse_match

templates = Jinja2Templates(directory="templates")

admin_router = APIRouter()

@admin_router.get("/login", response_class=HTMLResponse)
async def admin_login(request: Request):
    response = templates.TemplateResponse("admin_login.html", {"request": request})
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@admin_router.post("/login", response_class=HTMLResponse)
async def admin_login_post(request: Request, username: str = Form(...), password: str = Form(...)):
    try:
        admin, auth_token = await login_admin(
            username, password, admins_collection, SUPERADMIN_USERNAME, SUPERADMIN_PASSWORD_ENCRYPTED, fernet
        )
        response = RedirectResponse(url="/admin-panel", status_code=303)
        response.set_cookie(key="auth_token", value=auth_token, httponly=True, secure=False)
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    except BadRequestException as e:
        response = templates.TemplateResponse(
            "admin_login.html",
            {"request": request, "error": str(e.detail)}
        )
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

@admin_router.get("/logout", response_class=RedirectResponse)
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
    admin: dict = Depends(get_current_admin)
):
    query = {}
    if tournament and tournament != "Все лиги":
        query["tournament"] = tournament
    if date:
        query["date"] = date
    show_inactive_bool = str(show_inactive).lower() in ['1', 'true', 'yes']
    if not show_inactive_bool:
        query["is_active"] = {"$eq": True}
    matches = await get_matches(query, matches_collection)
    matches = convert_objectid_to_str(matches)
    return templates.TemplateResponse("admin_panel.html", {
        "request": request,
        "matches": matches,
        "username": admin["username"]
    })

@admin_router.get("/set-admin/", response_class=HTMLResponse)
@admin_router.get("/set-admin", response_class=HTMLResponse)
async def set_admin(request: Request, admin: dict = Depends(get_current_admin)):
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
async def create_admin_route(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    admin: dict = Depends(get_current_admin)
):
    result = await create_admin(
        username, password, admins_collection, admin_logs_collection, admin, validate_password, fernet
    )
    response = RedirectResponse(url="/admin-panel/set-admin", status_code=303)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@admin_router.get("/set-admin/edit/{id}", response_class=HTMLResponse)
async def edit_admin_form(request: Request, id: str, admin: dict = Depends(get_current_admin)):
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
async def edit_admin_route(
    request: Request,
    id: str,
    username: str = Form(...),
    password: str = Form(None),
    admin: dict = Depends(get_current_admin)
):
    try:
        await edit_admin(id, username, password, admins_collection, admin_logs_collection, admin, validate_password, fernet)
        response = RedirectResponse(url="/admin-panel/set-admin", status_code=303)
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    except (BadRequestException, ForbiddenException, NotFoundException) as e:
        raise BadRequestException(str(e.detail))
    except Exception as e:
        raise BadRequestException(f"Invalid admin ID or data: {str(e)}")

@admin_router.delete("/set-admin/delete/{id}", response_class=RedirectResponse)
async def delete_admin_route(request: Request, id: str, admin: dict = Depends(get_current_admin)):
    try:
        await delete_admin(id, admins_collection, admin_logs_collection, admin)
        response = RedirectResponse(url="/admin-panel/set-admin", status_code=303)
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    except (BadRequestException, ForbiddenException, NotFoundException) as e:
        raise BadRequestException(str(e.detail))
    except Exception as e:
        raise BadRequestException(f"Invalid admin ID: {str(e)}")

SECTOR_LIST = [
    '101', '102', '103', '104', '105', '106', '107', '108', '110', '111', '112', '113', '114', '115', '116', '117', '118', '119', '120', '122', '123', '124',
    '201', '202', '203', '204', '205', '206', '207', '208', '209', '210', '211', '212', '213', '214', '215', '216', '217', '218', '219', '220', '221', '222', '223', '224'
]

@admin_router.get("/bulk_add_sectors/{match_slug}", response_class=HTMLResponse)
async def bulk_add_sectors_form(request: Request, match_slug: str, admin: dict = Depends(get_current_admin)):
    match = await matches_collection.find_one({"slug": match_slug})
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    return templates.TemplateResponse(
        "bulk_add_sectors.html",
        {"request": request, "match": match, "sectors": SECTOR_LIST, "username": admin["username"]}
    )

@admin_router.post("/bulk_add_sectors/{match_slug}", response_class=RedirectResponse)
async def bulk_add_sectors_route(
    request: Request,
    match_slug: str,
    admin: dict = Depends(get_current_admin)
):
    form = await request.form()
    sector_names = form.getlist("sector_name")
    rows = form.getlist("row")
    places = form.getlist("places")
    prices = form.getlist("price")
    sector_data = list(zip(sector_names, rows, places, prices))
    await bulk_add_sectors(match_slug, sector_data, matches_collection)
    return RedirectResponse(url=f"/admin-panel/edit_match/{match_slug}", status_code=303)

@admin_router.post("/add_match", response_class=HTMLResponse)
async def add_match_route(
    request: Request,
    teams: str = Form(...),
    date: str = Form(...),
    time: str = Form(...),
    tournament: str = Form(...),
    slug: str = Form(None),
    image: Optional[UploadFile] = File(None),
    official_url: str = Form(None),
    admin: dict = Depends(get_current_admin)
):
    await add_match(teams, date, time, tournament, slug, image, matches_collection, translit, official_url)
    response = RedirectResponse(url="/admin-panel", status_code=303)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@admin_router.get("/edit_match/{match_slug}", response_class=HTMLResponse)
async def edit_match_form(
    request: Request,
    match_slug: str,
    admin: dict = Depends(get_current_admin)
):
    match = await get_match_for_edit(match_slug, matches_collection)
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
async def edit_match_route(
    request: Request,
    match_slug: str,
    teams: str = Form(...),
    date: str = Form(...),
    time: str = Form(...),
    tournament: str = Form(...),
    is_active: Optional[str] = Form(None),
    slug: str = Form(None),
    image: Optional[UploadFile] = File(None),
    official_url: str = Form(None),
    admin: dict = Depends(get_current_admin)
):
    is_active_bool = is_active == "true"
    await edit_match(match_slug, teams, date, time, tournament, is_active_bool, slug, image, matches_collection, translit, official_url)
    response = RedirectResponse(url="/admin-panel", status_code=303)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@admin_router.delete("/delete_match/{match_slug}", response_class=HTMLResponse)
async def delete_match_route(
    request: Request,
    match_slug: str,
    admin: dict = Depends(get_current_admin)
):
    await delete_match(match_slug, matches_collection)
    response = RedirectResponse(url="/admin-panel", status_code=303)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@admin_router.get("/deactivate_seat/{match_slug}/{sector_name}/{row}/{seat}", response_class=RedirectResponse)
async def deactivate_seat_route(
    request: Request,
    match_slug: str,
    sector_name: str,
    row: int,
    seat: int,
    admin: dict = Depends(get_current_admin)
):
    await deactivate_seat(match_slug, sector_name, row, seat, matches_collection)
    response = RedirectResponse(url=f"/admin-panel/edit_match/{match_slug}", status_code=303)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@admin_router.get("/activate_seat/{match_slug}/{sector_name}/{row}/{seat}", response_class=RedirectResponse)
async def activate_seat_route(
    request: Request,
    match_slug: str,
    sector_name: str,
    row: int,
    seat: int,
    admin: dict = Depends(get_current_admin)
):
    await activate_seat(match_slug, sector_name, row, seat, matches_collection)
    response = RedirectResponse(url=f"/admin-panel/edit_match/{match_slug}", status_code=303)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@admin_router.post("/update_seats/{match_slug}", response_class=JSONResponse)
async def update_seats_route(
    request: Request,
    match_slug: str,
    admin: dict = Depends(get_current_admin)
):
    data = await request.json()
    seat_changes = data.get("seat_changes", {})
    total_seats = data.get("total_seats")
    await update_seats(match_slug, seat_changes, total_seats, matches_collection)
    return {"status": "success"}

@admin_router.post("/delete_sector/{match_slug}/{sector_name}", response_class=RedirectResponse)
async def delete_sector_route(request: Request, match_slug: str, sector_name: str, admin: dict = Depends(get_current_admin)):
    await delete_sector(match_slug, sector_name, matches_collection)
    return RedirectResponse(url=f"/admin-panel/edit_match/{match_slug}", status_code=303)

@admin_router.post("/update_seat_price/{match_slug}/{sector_name}/{row}/{seat}", response_class=JSONResponse)
async def update_seat_price_route(
    request: Request,
    match_slug: str,
    sector_name: str,
    row: int,
    seat: int,
    admin: dict = Depends(get_current_admin)
):
    data = await request.json()
    new_price = data.get("price")
    await update_seat_price(match_slug, sector_name, row, seat, new_price, matches_collection)
    return {"status": "success"}

@admin_router.get("/delete_seat/{match_slug}/{sector_name}/{row}/{seat}", response_class=RedirectResponse)
async def delete_seat_route(
    request: Request,
    match_slug: str,
    sector_name: str,
    row: int,
    seat: int,
    admin: dict = Depends(get_current_admin)
):
    await delete_seat(match_slug, sector_name, row, seat, matches_collection)
    response = RedirectResponse(url=f"/admin-panel/edit_match/{match_slug}", status_code=303)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@admin_router.get("/admin-panel/", include_in_schema=False)
async def redirect_admin_panel():
    return RedirectResponse(url="/admin-panel")

@admin_router.post("/manual_parse/{match_slug}", response_class=JSONResponse)
async def manual_parse_match(match_slug: str):
    from app.database.mongodb import matches_collection
    match = await matches_collection.find_one({"slug": match_slug})
    if not match or not match.get("official_url"):
        return {"status": "error", "error": "Нет ссылки на официальный сайт"}
    try:
        await run_parse_match(match, matches_collection)
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "error": str(e)}

def verify_password(plain_password: str, encrypted_password: str) -> bool:
    try:
        decrypted_password = fernet.decrypt(encrypted_password.encode()).decode()
        return plain_password == decrypted_password
    except Exception as e:
        return False