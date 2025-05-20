import motor.motor_asyncio

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