from app.utils.exceptions import NotFoundException, BadRequestException, ForbiddenException
from app.core.security import verify_password
from app.utils.helpers import convert_objectid_to_str
from bson import ObjectId
from datetime import datetime
import secrets
import re

# Пример: логика логина администратора
async def login_admin(username, password, admins_collection, SUPERADMIN_USERNAME, SUPERADMIN_PASSWORD_ENCRYPTED, fernet):
    if username == SUPERADMIN_USERNAME:
        if verify_password(password, SUPERADMIN_PASSWORD_ENCRYPTED):
            auth_token = secrets.token_hex(16)
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
            return admin, auth_token
        else:
            raise BadRequestException("Неверный логин или пароль")
    admin = await admins_collection.find_one({"username": username})
    if not admin or not verify_password(password, admin["password_encrypted"]):
        raise BadRequestException("Неверный логин или пароль")
    auth_token = secrets.token_hex(16)
    await admins_collection.update_one(
        {"_id": admin["_id"]},
        {"$set": {"auth_token": auth_token}}
    )
    return admin, auth_token

# Пример: создание администратора
async def create_admin(username, password, admins_collection, admin_logs_collection, admin, validate_password, fernet):
    if admin["role"] != "superadmin":
        raise ForbiddenException("Access denied: superadmin role required")
    if not re.match(r"^[a-zA-Z0-9_-]+$", username):
        raise BadRequestException("Username must contain only Latin letters, digits, underscores, or hyphens")
    if not validate_password(password):
        raise BadRequestException("Password must be at least 8 characters long, contain at least one uppercase Latin letter and one special character")
    existing_admin = await admins_collection.find_one({"username": username})
    if existing_admin:
        raise BadRequestException("Username already exists")
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
    return result

async def edit_admin(id, username, password, admins_collection, admin_logs_collection, admin, validate_password, fernet):
    if admin["role"] != "superadmin":
        raise ForbiddenException("Access denied: superadmin role required")
    existing_admin = await admins_collection.find_one({"_id": ObjectId(id)})
    if not existing_admin:
        raise NotFoundException("Admin not found")
    if not re.match(r"^[a-zA-Z0-9_-]+$", username):
        raise BadRequestException("Username must contain only Latin letters, digits, underscores, or hyphens")
    if username != existing_admin["username"]:
        username_check = await admins_collection.find_one({"username": username})
        if username_check:
            raise BadRequestException("Username already exists")
    update_data = {"username": username}
    log_details = {"old_username": existing_admin["username"], "new_username": username}
    if password:
        if not validate_password(password):
            raise BadRequestException("Password must be at least 8 characters long, contain at least one uppercase Latin letter and one special character")
        update_data["password_encrypted"] = fernet.encrypt(password.encode()).decode()
        log_details["password_changed"] = True
    await admins_collection.update_one({"_id": ObjectId(id)}, {"$set": update_data})
    await admin_logs_collection.insert_one({
        "admin_id": admin["_id"],
        "action": "edit_user",
        "details": log_details,
        "timestamp": datetime.utcnow()
    })
    return True

async def delete_admin(id, admins_collection, admin_logs_collection, admin):
    if admin["role"] != "superadmin":
        raise ForbiddenException("Access denied: superadmin role required")
    admin_data = await admins_collection.find_one({"_id": ObjectId(id)})
    if not admin_data:
        raise NotFoundException("Admin not found")
    if admin_data["role"] == "superadmin":
        raise ForbiddenException("Cannot delete superadmin")
    await admins_collection.delete_one({"_id": ObjectId(id)})
    await admin_logs_collection.insert_one({
        "admin_id": admin["_id"],
        "action": "delete_user",
        "details": {"username": admin_data["username"], "role": admin_data["role"]},
        "timestamp": datetime.utcnow()
    })
    return True

async def bulk_add_sectors(match_slug, sector_data, matches_collection):
    match = await matches_collection.find_one({"slug": match_slug})
    if not match:
        raise NotFoundException("Match not found")
    for sector_name, row, places_str, price in sector_data:
        seat_numbers = []
        for part in places_str.split(","):
            if "-" in part:
                start, end = map(int, part.split("-"))
                seat_numbers.extend(range(start, end + 1))
            else:
                seat_numbers.append(int(part))
        # Новая структура хранения мест
        seats = [{
            "row": int(row),
            "seat": seat_num,
            "available": True,
            "price": int(price),
            "source": "manual"
        } for seat_num in seat_numbers]
        
        for sector in match["sectors"]:
            if sector["name"] == sector_name:
                existing_seats = {(seat["row"], seat["seat"]) for seat in sector["seats"]}
                seats = [seat for seat in seats if (seat["row"], seat["seat"]) not in existing_seats]
                sector["seats"].extend(seats)
                break
        else:
            match["sectors"].append({"name": sector_name, "seats": seats})
    await matches_collection.update_one({"slug": match_slug}, {"$set": {"sectors": match["sectors"]}})
    return True

async def deactivate_seat(match_slug, sector_name, row, seat, matches_collection):
    match = await matches_collection.find_one({"slug": match_slug})
    if not match:
        raise NotFoundException("Match not found")
    for sector in match["sectors"]:
        if sector["name"] == sector_name:
            for st in sector["seats"]:
                if st["row"] == row and st["seat"] == seat:
                    st["available"] = False
                    await matches_collection.update_one({"slug": match_slug}, {"$set": {"sectors": match["sectors"]}})
                    return True
            raise NotFoundException(f"Место {row}-{seat} не найдено в секторе")
    raise NotFoundException("Сектор не найден")

async def activate_seat(match_slug, sector_name, row, seat, matches_collection):
    match = await matches_collection.find_one({"slug": match_slug})
    if not match:
        raise NotFoundException("Match not found")
    for sector in match["sectors"]:
        if sector["name"] == sector_name:
            for st in sector["seats"]:
                if st["row"] == row and st["seat"] == seat:
                    st["available"] = True
                    await matches_collection.update_one({"slug": match_slug}, {"$set": {"sectors": match["sectors"]}})
                    return True
            raise NotFoundException(f"Место {row}-{seat} не найдено в секторе")
    raise NotFoundException("Сектор не найден")

async def update_seats(match_slug, seat_changes, total_seats, matches_collection):
    match = await matches_collection.find_one({"slug": match_slug})
    if not match:
        raise NotFoundException("Match not found")
    for sector_name, seats in seat_changes.items():
        for sector in match["sectors"]:
            if sector["name"] == sector_name:
                for seat_key, change in seats.items():
                    # seat_key должен быть в формате row-seat
                    if '-' in str(seat_key):
                        row, seat = map(int, str(seat_key).split('-'))
                    else:
                        continue
                    new_status = change["status"]
                    new_price = change.get("price")
                    for st in sector["seats"]:
                        if st["row"] == row and st["seat"] == seat:
                            st["available"] = (new_status == "available")
                            if new_price is not None:
                                st["price"] = new_price
                            break
                break
    await matches_collection.update_one(
        {"slug": match_slug},
        {"$set": {"sectors": match["sectors"], "total_seats": total_seats}}
    )
    return True

async def delete_sector(match_slug, sector_name, matches_collection):
    match = await matches_collection.find_one({"slug": match_slug})
    if not match:
        raise NotFoundException("Match not found")
    sectors = match.get("sectors", [])
    new_sectors = [sector for sector in sectors if sector["name"] != sector_name]
    await matches_collection.update_one({"slug": match_slug}, {"$set": {"sectors": new_sectors}})
    return True

async def update_seat_price(match_slug, sector_name, row, seat, new_price, matches_collection):
    if new_price is None or not isinstance(new_price, (int, float)) or new_price <= 0:
        raise BadRequestException("Некорректная цена")
    match = await matches_collection.find_one({"slug": match_slug})
    if not match:
        raise NotFoundException("Матч не найден")
    for sector in match["sectors"]:
        if sector["name"] == sector_name:
            for st in sector["seats"]:
                if st["row"] == row and st["seat"] == seat:
                    st["price"] = new_price
                    await matches_collection.update_one({"slug": match_slug}, {"$set": {"sectors": match["sectors"]}})
                    return True
            raise NotFoundException("Место не найдено в секторе")
    raise NotFoundException("Сектор не найден")

async def delete_seat(match_slug, sector_name, row, seat, matches_collection):
    match = await matches_collection.find_one({"slug": match_slug})
    if not match:
        raise NotFoundException("Match not found")
    for sector in match["sectors"]:
        if sector["name"] == sector_name:
            original_len = len(sector["seats"])
            sector["seats"] = [st for st in sector["seats"] if not (st["row"] == row and st["seat"] == seat)]
            if len(sector["seats"]) == original_len:
                raise NotFoundException(f"Место {row}-{seat} не найдено в секторе")
            await matches_collection.update_one({"slug": match_slug}, {"$set": {"sectors": match["sectors"]}})
            return True
    raise NotFoundException("Сектор не найден")

