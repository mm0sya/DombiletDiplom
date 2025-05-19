import os
from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import re
from datetime import datetime, timedelta
import traceback
from app.services.match_service import get_match_by_slug, get_sector_from_match, check_seat_availability, select_seat_logic
from app.utils.exceptions import NotFoundException, BadRequestException
from app.database.mongodb import matches_collection, contact_requests_collection
from app.utils.helpers import convert_objectid_to_str

templates = Jinja2Templates(directory="templates")

public_router = APIRouter()

@public_router.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    matches = await matches_collection.find({"is_active": True}).to_list(1000)
    matches = convert_objectid_to_str(matches)
    return templates.TemplateResponse("index.html", {"request": request, "matches": matches})

@public_router.get("/matches", response_class=HTMLResponse)
async def read_matches(request: Request):
    matches = await matches_collection.find({"is_active": True}).to_list(1000)
    matches = convert_objectid_to_str(matches)
    return templates.TemplateResponse("matches.html", {"request": request, "matches": matches})

@public_router.get("/stadium", response_class=HTMLResponse)
async def stadium(request: Request):
    return templates.TemplateResponse("stadium.html", {"request": request})

@public_router.get("/tickets/{match_slug}", response_class=HTMLResponse)
async def get_tickets(request: Request, match_slug: str):
    try:
        match = await get_match_by_slug(match_slug, matches_collection)
        match = convert_objectid_to_str(match)
        return templates.TemplateResponse("tickets.html", {"request": request, "match": match})
    except NotFoundException as e:
        raise NotFoundException(str(e.detail))

@public_router.get("/sector_view/{match_slug}/{sector_name}", response_class=HTMLResponse)
async def get_sector_view(request: Request, match_slug: str, sector_name: str):
    try:
        match = await get_match_by_slug(match_slug, matches_collection)
        match = convert_objectid_to_str(match)
        sector = await get_sector_from_match(match, sector_name)
        if not sector.get("seats"):
            raise BadRequestException("No seats available in this sector")
        svg_path = os.path.join("static", "svg", f"{sector_name}.svg")
        try:
            with open(svg_path, encoding="utf-8") as f:
                svg_code = f.read()
        except Exception:
            svg_code = "<svg><!-- SVG не найден --></svg>"
        available_seats = [
            {
                "row": seat["row"],
                "seat": seat["seat"],
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
    except (NotFoundException, BadRequestException) as e:
        raise BadRequestException(str(e.detail))

@public_router.get("/check_seat/{match_slug}/{sector_name}/{row}/{seat}", response_class=JSONResponse)
async def check_seat(match_slug: str, sector_name: str, row: int, seat: int):
    try:
        match = await get_match_by_slug(match_slug, matches_collection)
        result = await check_seat_availability(match, sector_name, row, seat)
        return result
    except NotFoundException as e:
        raise NotFoundException(str(e.detail))

@public_router.post("/sector_view/{match_slug}/{sector_name}/select_seat", response_class=HTMLResponse)
async def select_seat(match_slug: str, sector_name: str, row: int = Form(...), seat: int = Form(...)):
    try:
        match = await get_match_by_slug(match_slug, matches_collection)
        await select_seat_logic(match, sector_name, row, seat)
        return RedirectResponse(url=f"/sector_view/{match_slug}/{sector_name}", status_code=303)
    except (NotFoundException, BadRequestException) as e:
        raise BadRequestException(str(e.detail))

@public_router.post("/submit_contact", response_class=RedirectResponse)
async def submit_contact(
    request: Request,
    name: str = Form(...),
    phone: str = Form(...),
    email: str = Form(...),
    consent: bool = Form(...)
):
    try:
        if not re.match(r"^[a-zA-Zа-яА-ЯёЁ\s'-]+$", name):
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