from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import re
import traceback
from app.services.order_service import process_order
from app.utils.exceptions import NotFoundException, BadRequestException
from app.database.mongodb import matches_collection, orders_collection
from app.utils.helpers import convert_objectid_to_str
import aiosmtplib
from email.message import EmailMessage

templates = Jinja2Templates(directory="templates")

cart_router = APIRouter()

@cart_router.get("/cart", response_class=HTMLResponse)
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
    
@cart_router.post("/cart/clear", response_class=RedirectResponse)
async def clear_cart():
    return RedirectResponse(url="/cart", status_code=303)


@cart_router.post("/submit_order", response_class=HTMLResponse)
async def submit_order(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    selected_seats: int = Form(...),
    fan_id: str = Form(None),
    comment: str = Form(None)
):
    import json
    try:
        selected_seats_data = json.loads(selected_seats)
        await process_order(name, email, phone, selected_seats_data, matches_collection, orders_collection, fan_id, comment)
        # Отправка письма пользователю
        message = EmailMessage()
        message["From"] = "foot_bilet@mail.ru"  # тот же адрес, что и username SMTP
        message["To"] = email
        message["Subject"] = "Ваш заказ получен"
        message.set_content(f"Здравствуйте, {name}! Ваш заказ успешно оформлен.\nСкоро наш менеджер свяжется с вами для подтверждения.\n\nСпасибо за покупку!")

        await aiosmtplib.send(
            message,
            hostname="smtp.mail.ru",
            port=465,
            username="foot_bilet@mail.ru",
            password="C3gZs5uDsyKyy9ea8V4B",
            use_tls=True,
        )
        return RedirectResponse(url="/cart?success=true", status_code=303)
    except json.JSONDecodeError as e:
        print(f"JSON decode error in submit_order: {str(e)}")
        print(f"Selected seats data: {selected_seats}")
        raise BadRequestException(f"Invalid selected_seats format: {str(e)}")
    except BadRequestException as e:
        raise BadRequestException(str(e.detail))
    except NotFoundException as e:
        raise NotFoundException(str(e.detail))
    except Exception as e:
        print(f"Error in submit_order: {str(e)}")
        import traceback
        print(traceback.format_exc())
        raise BadRequestException(f"Internal server error: {str(e)}")

@cart_router.post("/checkout", response_class=RedirectResponse)
async def checkout(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    selected_seats: str = Form(...),
    fan_id: str = Form(None),
    comment: str = Form(None)
):
    try:
        if not re.match(r'^\+?\d{10,15}$', phone):
            raise HTTPException(status_code=400, detail="Invalid phone number format")
        response = await submit_order(
            request=request,
            name=full_name,
            email=email,
            phone=phone,
            selected_seats=selected_seats,
            fan_id=fan_id,
            comment=comment
        )
        return response
    except Exception as e:
        print(f"Error in checkout: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")