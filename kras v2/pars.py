import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup


login_url = "https://ticket.fckrasnodar.ru/ru/Account/LoginPage"  # Уточните URL
target_url = "https://ticket.fckrasnodar.ru/ru/Arena/be40af22-f4ff-4090-bc2f-bbff4fe874d5"
#target_url = 'https://ticket.fckrasnodar.ru/ru/Arena/b2385467-401a-4b00-87c4-9ef8bf0f09ca'
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))

try:
    # 2. Открываем страницу логина
    driver.get(login_url)

    # 3. Заполняем форму логина
    email_field = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, "log_e-mail"))
    )
    email_field.clear()
    email_field.send_keys("9330157047")

    password_field = driver.find_element(By.ID, "log_password")
    password_field.clear()
    password_field.send_keys("javend1159")

    # 4. Нажимаем кнопку "Войти"
    login_button = driver.find_element(By.ID, "login")
    login_button.click()

    # 5. Ждем редиректа или появления ошибки
    try:
        WebDriverWait(driver, 10).until(
            EC.url_changes(login_url)
        )
        print("Авторизация успешна")
    except Exception as e:
        print(f"Ошибка авторизации: {e}")
        print("Проверьте CAPTCHA или данные. HTML сохранен для анализа.")
        with open("login_error.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        driver.quit()
        exit()

    # 6. Открываем целевую страницу
    driver.get(target_url)

    # 7. Ждем загрузки SVG
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "svg"))
        )
        #print("SVG загружено")
    except Exception as e:
        print(f"Ошибка ожидания SVG: {e}")

    # 8. Даем время на выполнение AJAX-запроса и применение цветов
    time.sleep(5)  # Задержка в 5 секунд для загрузки данных

    # 9. Получаем HTML после рендеринга
    html = driver.page_source
    soup = BeautifulSoup(html, "html.parser")

#    10. Сохраняем HTML для анализа
#    with open("page.html", "w", encoding="utf-8") as f:
#        f.write(html)
#    print("HTML сохранен в page.html")


    # 11. Ищем сектора в SVG
    svg = soup.find("svg")
    if svg:
        sectors = svg.find_all("g")
        if not sectors:
            print("Сектора не найдены в SVG. Проверьте структуру страницы.")
        else:
            for sector in sectors:
                sector_id = sector.get("id")
                rect = sector.find("rect")
                text = sector.find("text")
                sector_name = text.find("tspan").text if text and text.find("tspan") else "Неизвестный сектор"

                fill_color = None
                # Проверяем цвет у группы <g>
                style = sector.get("style", "")
                for style_item in style.split(";"):
                    if "fill:" in style_item:
                        fill_color = style_item.split(":")[1].strip()
                        break

                # Если цвет не найден в <g>, проверяем <rect>
                if not fill_color and rect:
                    style = rect.get("style", "")
                    for style_item in style.split(";"):
                        if "fill:" in style_item:
                            fill_color = style_item.split(":")[1].strip()
                            break
                    if not fill_color:
                        fill_color = rect.get("fill", "")

                # Определяем статус по цвету
                status = "Неизвестный статус"
                if fill_color:
                    #print(f"Цвет сектора {sector_name} (ID: {sector_id}): {fill_color}")
                    if fill_color in ["#00C000", "rgb(0, 192, 0)"]:
                        status = "Доступен"
                    elif fill_color in ["#f90606", "rgb(249, 6, 6)"]:
                        status = "Занят"

                #if fill_color:
                #    print(f"Сектор {sector_name} (ID: {sector_id}): {status}")
                #else:
                #    print(f"Сектор {sector_name} (ID: {sector_id}): Нет данных о цвете")
    else:
        print("SVG не найдено на странице.")

    

except Exception as e:
    #print(f"Общая ошибка: {e}")
    with open("error.html", "w", encoding="utf-8") as f:
        f.write(driver.page_source)
    driver.quit()
    exit()


# 11.5. Обрабатываем сектора и собираем доступные
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

    status = "Неизвестный статус"
    if fill_color:
        #print(f"Цвет сектора {sector_name} (ID: {sector_id}): {fill_color}")
        if fill_color in ["rgb(0, 192, 0)", "#00C000"]:
            status = "Доступен"
            available_sectors.append((sector_id, sector_name))
        elif fill_color in ["rgb(249, 6, 6)", "#f90606"]:
            status = "Занят"
    else:
        print(f"Сектор {sector_name} (ID: {sector_id}): Нет данных о цвете")

    print(f"Сектор {sector_name} (ID: {sector_id}): {status}")

# 11.6. Входим в доступные сектора и парсим свободные места
for sector_id, sector_name in available_sectors:
    print(f"\nОбрабатываем сектор {sector_name} (ID: {sector_id})")
    try:
        # Находим элемент сектора на странице
        sector_element = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, sector_id))
        )

        # Прокручиваем к элементу и кликаем
        driver.execute_script("arguments[0].scrollIntoView(true);", sector_element)
        ActionChains(driver).move_to_element(sector_element).click().perform()

        # Проверяем, открылось ли модальное окно
        try:
            modal = WebDriverWait(driver, 5).until(
                EC.visibility_of_element_located((By.ID, "openModal"))
            )
            print(f"Модальное окно открылось для сектора {sector_name}")
            # Находим кнопку "Показать все места"
            show_all_button = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.ID, "ModalHref"))
            )
            # Кликаем по кнопке
            show_all_button.click()
        except:
            print(f"Модальное окно не открылось для сектора {sector_name}, предполагаем прямую загрузку страницы мест")

        # Ждем загрузки страницы с местами
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, "svg"))
        )
        time.sleep(3)  # Дополнительная задержка для полной загрузки

        # Получаем HTML страницы с местами
        seats_html = driver.page_source
        seats_soup = BeautifulSoup(seats_html, "html.parser")

        # Сохраняем HTML для анализа
        #with open(f"seats_{sector_name}_{sector_id}.html", "w", encoding="utf-8") as f:
        #    f.write(seats_html)

        # Ищем SVG и элементы мест
        svg = seats_soup.find("svg")
        if not svg:
            print(f"SVG не найдено в секторе {sector_name}.") #  Проверьте seats_{sector_name}_{sector_id}.html
            driver.get(target_url)
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "svg")))
            time.sleep(2)
            continue

        # Ищем <g> с классом GrpPolygon
        seats = svg.find_all("g", class_="GrpPolygon")
        if not seats:
            print(f"Элементы <g class='GrpPolygon'> (места) не найдены в секторе {sector_name}.") #  Проверьте seats_{sector_name}_{sector_id}.html
            driver.get(target_url)
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "svg")))
            time.sleep(2)
            continue

        available_seats = []
        for seat in seats:
            seat_id = seat.get("id", "Нет ID")
            rect = seat.find("rect")
            text = seat.find("text")

            # Проверяем цвет
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

            # Проверяем, свободно ли место
            if fill_color not in ["rgb(0, 192, 0)", "#00C000"]:
                continue

            # Извлекаем номер места и ряд
            seat_name = seat.get("seat", "Неизвестное место")
            row_name = seat.get("row", "Неизвестный ряд")

            # Если атрибуты seat или row отсутствуют, пробуем взять из <text>
            if seat_name == "Неизвестное место" and text and text.text.strip():
                seat_name = text.text.strip()
            if row_name == "Неизвестный ряд" and text and text.get("data-row"):
                row_name = text.get("data-row", "Неизвестный ряд")

            available_seats.append((seat_id, seat_name, row_name))

        # Выводим информацию о свободных местах
        if available_seats:
            print(f"Свободные места в секторе {sector_name}:")
            for seat_id, seat_name, row_name in available_seats:
                print(f"  Ряд: {row_name}, Место: {seat_name}")#(ID: {seat_id})
        else:
            print(f"Свободных мест в секторе {sector_name} не найдено.") # Проверьте seats_{sector_name}_{sector_id}.html

        # Возвращаемся на страницу секторов
        driver.get(target_url)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "svg"))
        )
        time.sleep(2)

    except Exception as e:
        print(f"Ошибка при обработке сектора {sector_name}: {e}")
        #with open(f"error_seats_{sector_name}_{sector_id}.html", "w", encoding="utf-8") as f:
        #    f.write(driver.page_source)
        #driver.get(target_url)
        #WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "svg")))
        time.sleep(2)
        continue

# 12. Закрываем браузер
driver.quit()