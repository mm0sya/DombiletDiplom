from app.utils.exceptions import NotFoundException, BadRequestException
from datetime import datetime
import os
from transliterate import translit

async def get_match_by_slug(match_slug, matches_collection):
    match = await matches_collection.find_one({"slug": match_slug})
    if not match:
        raise NotFoundException("Match not found")
    return match

async def get_sector_from_match(match, sector_name):
    for sector in match["sectors"]:
        if sector["name"] == sector_name:
            return sector
    raise NotFoundException("Sector not found")

async def check_seat_availability(match, sector_name, row, seat):
    sector = await get_sector_from_match(match, sector_name)
    for st in sector["seats"]:
        if st["row"] == row and st["seat"] == seat:
            return {"available": st["available"], "price": st["price"]}
    return {"available": False}

async def select_seat_logic(match, sector_name, row, seat):
    sector = await get_sector_from_match(match, sector_name)
    for st in sector["seats"]:
        if st["row"] == row and st["seat"] == seat:
            if not st["available"]:
                raise BadRequestException(f"Место {row}-{seat} уже занято")
            return True
    raise NotFoundException(f"Место {row}-{seat} не найдено в секторе")

async def get_matches(query, matches_collection):
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
    return matches

async def add_match(teams, date, time, tournament, slug, image, matches_collection, translit, official_url=None):
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
        "slug": slug,
        "official_url": official_url
    }
    await matches_collection.insert_one(match)
    return match

async def edit_match(match_slug, teams, date, time, tournament, is_active, slug, image, matches_collection, translit, official_url=None):
    match = await matches_collection.find_one({"slug": match_slug})
    if not match:
        raise NotFoundException("Match not found")
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
    update_data["official_url"] = official_url
    await matches_collection.update_one({"slug": match_slug}, {"$set": update_data})
    return update_data

async def delete_match(match_slug, matches_collection):
    match = await matches_collection.find_one({"slug": match_slug})
    if not match:
        raise NotFoundException("Match not found")
    if match.get("image"):
        try:
            image_path = f"static/backgrounds/{match['image']}"
            if match['image'] != "default_match.jpg" and os.path.exists(image_path):
                os.remove(image_path)
        except FileNotFoundError:
            pass
    await matches_collection.delete_one({"slug": match_slug})
    return True

async def get_match_for_edit(match_slug, matches_collection):
    match = await matches_collection.find_one({"slug": match_slug})
    if not match:
        raise NotFoundException("Match not found")
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
    return match
