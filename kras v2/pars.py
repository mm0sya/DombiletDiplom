import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import motor.motor_asyncio
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler

MONGO_URL = "mongodb://localhost:27017"
DB_NAME = "krasnodar_tickets"
COLLECTION_NAME = "matches"

login_url = "https://ticket.fckrasnodar.ru/ru/Account/LoginPage"

busy_colors = [
    "#f90606", "rgb(249, 6, 6)",  # красные
    "#bdbdbd", "rgb(189, 189, 189)", "#cccccc", "rgb(204, 204, 204)"  # серые
]

# --- Функция парсинга одного матча ---
async def parse_match(match, matches_collection):
    official_url = match.get("official_url")
    if not official_url:
        return
    print(f"Парсинг матча: {match['teams']} ({official_url})")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))
    try:
        driver.get(login_url)
        email_field = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "log_e-mail"))
        )
        email_field.clear()
        email_field.send_keys("9330157047")
        password_field = driver.find_element(By.ID, "log_password")
        password_field.clear()
        password_field.send_keys("javend1159")
        login_button = driver.find_element(By.ID, "login")
        login_button.click()
        try:
            WebDriverWait(driver, 10).until(EC.url_changes(login_url))
            print("Авторизация успешна")
        except Exception as e:
            print(f"Ошибка авторизации: {e}")
            driver.quit()
            return
        driver.get(official_url)
        try:
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "svg")))
        except Exception as e:
            print(f"Ошибка ожидания SVG: {e}")
        time.sleep(5)
        html = driver.page_source
        soup = BeautifulSoup(html, "html.parser")
        svg = soup.find("svg")
        if not svg:
            print("SVG не найдено на странице.")
            driver.quit()
            return
        sectors = svg.find_all("g")
        available_sectors = []
        for sector in sectors:
            sector_id = sector.get("id")
            rect = sector.find("rect")
            text = sector.find("text")
            sector_name = text.find("tspan").text if text and text.find("tspan") else "Неизвестный сектор"
            fill_color = None
            style = sector.get("style", "")
            for style_item in style.split(";"):
                if "fill:" in style_item:
                    fill_color = style_item.split(":")[1].strip()
                    break
            if not fill_color and rect:
                style = rect.get("style", "")
                for style_item in style.split(";"):
                    if "fill:" in style_item:
                        fill_color = style_item.split(":")[1].strip()
                        break
                if not fill_color:
                    fill_color = rect.get("fill", "")
            if fill_color not in busy_colors:
                available_sectors.append((sector_id, sector_name))
        # --- Сбор мест по секторам ---
        all_sectors = {}
        for sector_id, sector_name in available_sectors:
            try:
                sector_element = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.ID, sector_id))
                )
                driver.execute_script("arguments[0].scrollIntoView(true);", sector_element)
                ActionChains(driver).move_to_element(sector_element).click().perform()
                try:
                    modal = WebDriverWait(driver, 5).until(
                        EC.visibility_of_element_located((By.ID, "openModal"))
                    )
                    show_all_button = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.ID, "ModalHref"))
                    )
                    show_all_button.click()
                except:
                    pass
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.TAG_NAME, "svg"))
                )
                time.sleep(3)
                seats_html = driver.page_source
                seats_soup = BeautifulSoup(seats_html, "html.parser")
                svg = seats_soup.find("svg")
                if not svg:
                    driver.get(official_url)
                    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "svg")))
                    time.sleep(2)
                    continue
                seats = svg.find_all("g", class_="GrpPolygon")
                if not seats:
                    driver.get(official_url)
                    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "svg")))
                    time.sleep(2)
                    continue
                available_seats = []
                for seat in seats:
                    seat_id = seat.get("id", "Нет ID")
                    rect = seat.find("rect")
                    text = seat.find("text")
                    fill_color = None
                    style = seat.get("style", "")
                    for style_item in style.split(";"):
                        if "fill:" in style_item:
                            fill_color = style_item.split(":")[1].strip()
                            break
                    if not fill_color and rect:
                        style = rect.get("style", "")
                        for style_item in style.split(";"):
                            if "fill:" in style_item:
                                fill_color = style_item.split(":")[1].strip()
                                break
                        if not fill_color:
                            fill_color = rect.get("fill", "")
                    if fill_color not in ["rgb(0, 192, 0)", "#00C000"]:
                        continue
                    seat_name = seat.get("seat", "Неизвестное место")
                    row_name = seat.get("row", "Неизвестный ряд")
                    if seat_name == "Неизвестное место" and text and text.text.strip():
                        seat_name = text.text.strip()
                    if row_name == "Неизвестный ряд" and text and text.get("data-row"):
                        row_name = text.get("data-row", "Неизвестный ряд")
                    available_seats.append({
                        "row": int(row_name) if str(row_name).isdigit() else row_name,
                        "seat": int(seat_name) if str(seat_name).isdigit() else seat_name,
                        "available": True,
                        "price": 0,  # цену можно доработать
                        "source": "parser"
                    })
                if available_seats:
                    all_sectors[sector_name] = available_seats
                driver.get(official_url)
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "svg")))
                time.sleep(2)
            except Exception as e:
                print(f"Ошибка при обработке сектора {sector_name}: {e}")
                time.sleep(2)
                continue
        # --- Обновление в базе ---
        # Удаляем старые parser-места
        sectors = match.get("sectors", [])
        for sector in sectors:
            sector["seats"] = [seat for seat in sector["seats"] if seat.get("source") != "parser"]
        # Добавляем новые parser-места
        for sector_name, seats in all_sectors.items():
            found = False
            for sector in sectors:
                if sector["name"] == sector_name:
                    sector["seats"].extend(seats)
                    found = True
                    break
            if not found:
                sectors.append({"name": sector_name, "seats": seats})
        await matches_collection.update_one({"_id": match["_id"]}, {"$set": {"sectors": sectors}})
        print(f"Обновлено мест для матча {match['teams']}")
    finally:
        driver.quit()

# --- Главная функция ---
async def main():
    client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    matches_collection = db[COLLECTION_NAME]
    matches = await matches_collection.find({"official_url": {"$ne": None, "$ne": ""}}).to_list(100)
    for match in matches:
        await parse_match(match, matches_collection)

# --- Периодический запуск ---
def start_scheduler():
    scheduler = AsyncIOScheduler()
    scheduler.add_job(lambda: asyncio.create_task(main()), 'interval', hours=1)
    scheduler.start()
    print("Парсер будет запускаться раз в час.")
    asyncio.get_event_loop().run_forever()

if __name__ == "__main__":
    start_scheduler()