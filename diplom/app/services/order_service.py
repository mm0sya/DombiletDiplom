from app.utils.exceptions import NotFoundException, BadRequestException
from datetime import datetime, timedelta
import json

async def process_order(name, email, phone, selected_seats, matches_collection, orders_collection, fan_id=None, comment=None):
    if not isinstance(selected_seats, list):
        raise BadRequestException("selected_seats must be a list")
    for seat_info in selected_seats:
        required_fields = ["match_id", "sector_name", "row", "seat", "price"]
        for field in required_fields:
            if field not in seat_info:
                raise BadRequestException(f"Missing field {field} in seat_info: {seat_info}")
            if not isinstance(seat_info["match_id"], str):
                raise BadRequestException(f"match_id must be a string, got {seat_info['match_id']}")
            if not isinstance(seat_info["sector_name"], str):
                raise BadRequestException(f"sector_name must be a string, got {seat_info['sector_name']}")
            if not isinstance(seat_info["row"], int):
                raise BadRequestException(f"row must be an integer, got {seat_info['row']}")
            if not isinstance(seat_info["seat"], int):
                raise BadRequestException(f"seat must be an integer, got {seat_info['seat']}")
            if not isinstance(seat_info["price"], (int, float)):
                raise BadRequestException(f"price must be a number, got {seat_info['price']}")
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
            raise NotFoundException(f"Match not found: {match_id}")
        for sector in match["sectors"]:
            if sector["name"] == sector_name:
                for seat_info in seats:
                    row = seat_info["row"]
                    seat_num = seat_info["seat"]
                    for st in sector["seats"]:
                        if st["row"] == row and st["seat"] == seat_num:
                            if not st["available"]:
                                raise BadRequestException(f"Место {row}-{seat_num} уже занято")
                            if st["price"] != seat_info["price"]:
                                raise BadRequestException(f"Несоответствие цены для места {row}-{seat_num}")
                            st["available"] = False
                            break
                    else:
                        raise NotFoundException(f"Место {row}-{seat_num} не найдено в секторе")
                break
        else:
            raise NotFoundException(f"Сектор не найден: {sector_name}")
        await matches_collection.update_one({"slug": match_id}, {"$set": {"sectors": match["sectors"]}})
        for seat_info in seats:
            order = {
                "match_id": match_id,
                "name": name,
                "email": email,
                "phone": phone,
                "sector": sector_name,
                "row": seat_info["row"],
                "seat": seat_info["seat"],
                "price": seat_info["price"],
                "timestamp": datetime.utcnow() + timedelta(hours=3),
                "fan_id": fan_id,
                "comment": comment
            }
            await orders_collection.insert_one(order)
    return True
