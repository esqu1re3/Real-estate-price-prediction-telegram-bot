import asyncio
import aiohttp
from bs4 import BeautifulSoup
import csv
import re
from tqdm import tqdm

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.93 Safari/537.36"
}

async def fetch(session, url, semaphore):
    async with semaphore:
        async with session.get(url, headers=HEADERS) as response:
            response.raise_for_status()
            return await response.text()

async def parse_page(page_number, session, semaphore, csv_writer, csv_file, csv_lock):
    url = f"https://www.house.kg/kupit-kvartiru?page={page_number}"
    try:
        html = await fetch(session, url, semaphore)
        soup = BeautifulSoup(html, "lxml")
        listings = soup.find_all("div", itemscope=True, itemtype="https://schema.org/Apartment", class_="listing")
        for listing in listings:
            # Извлекаем количество комнат
            rooms_tag = listing.find("meta", itemprop="numberOfRooms")
            rooms = rooms_tag.get("content", "").strip() if rooms_tag else ""
            
            # Извлекаем площадь
            area_tag = listing.find("meta", itemprop="floorSize")
            area = area_tag.get("content", "").strip() if area_tag else ""
            area = area.replace("м2", "") if area else ""
            area = area.replace(" ", "") if area else ""
            
            # Извлекаем номер этажа (просто число, например, "15")
            floor_number = ""
            title_tag = listing.find("p", class_="title")
            if title_tag:
                title_text = title_tag.get_text(separator=" ", strip=True)
                match = re.search(r'(\d+)\s*этаж', title_text)
                if match:
                    floor_number = match.group(1)
            
            # Извлекаем полный адрес
            address_tag = listing.find("div", class_="address")
            full_address = address_tag.get_text(separator=" ", strip=True) if address_tag else ""
            
            # Извлекаем цены (доллары и сом) и оставляем только цифры и пробелы
            price_dollars = ""
            price_soms = ""
            prices_block = listing.find("div", class_="listing-prices-block")
            if prices_block:
                price_tag = prices_block.find("div", class_="price")
                if price_tag:
                    raw_price = price_tag.get_text(strip=True)
                    # Оставляем только цифры и пробелы, затем нормализуем пробелы
                    price_dollars = " ".join(re.sub(r'[^\d\s]', '', raw_price).split())
                price_add_tag = prices_block.find("div", class_="price-addition")
                if price_add_tag:
                    raw_price_add = price_add_tag.get_text(strip=True)
                    price_soms = " ".join(re.sub(r'[^\d\s]', '', raw_price_add).split())
            
            row = {
                "Количество комнат": rooms,
                "Площадь (м²)": area,
                "Этаж": floor_number,
                "Адрес": full_address,
                "Цена ($)": price_dollars,
                "Цена (сом)": price_soms
            }
            # Синхронно записываем строку в CSV файл
            async with csv_lock:
                csv_writer.writerow(row)
                csv_file.flush()
    except Exception as e:
        print(f"Ошибка на странице {page_number}: {e}")

async def main():
    # Здесь semaphore позволяет запускать до 1000 задач, 
    # но фактическое количество одновременных TCP-соединений будет ограничено TCPConnector.
    semaphore = asyncio.Semaphore(100)
    csv_lock = asyncio.Lock()
    fieldnames = ["Количество комнат", "Площадь (м²)", "Этаж", "Адрес", "Цена ($)", "Цена (сом)"]

    # Настраиваем TCPConnector с увеличенным лимитом соединений
    # Параметр limit=30 задаёт максимальное количество одновременных TCP-соединений.
    connector = aiohttp.TCPConnector(limit=50)
    async with aiohttp.ClientSession(connector=connector) as session:
        with open("apartment_data.csv", "w", newline="", encoding="utf-8") as csv_file:
            csv_writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            csv_writer.writeheader()
            csv_file.flush()
            tasks = [parse_page(page, session, semaphore, csv_writer, csv_file, csv_lock) for page in range(1, 900)]
            for task in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="Парсинг страниц"):
                await task
    print("Парсинг завершен. Данные сохранены в файле apartment_data.csv.")

if __name__ == "__main__":
    asyncio.run(main())
