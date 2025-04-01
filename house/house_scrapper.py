import asyncio
import aiohttp
from bs4 import BeautifulSoup
import csv
import re
from tqdm import tqdm

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/90.0.4430.93 Safari/537.36"
}

async def fetch(session, url, semaphore):
    async with semaphore:
        async with session.get(url, headers=HEADERS) as response:
            response.raise_for_status()
            return await response.text()

async def parse_page(page_number, session, semaphore, csv_writer, csv_file, csv_lock):
    url = f"https://www.house.kg/kupit-dom?page={page_number}"
    try:
        html = await fetch(session, url, semaphore)
        soup = BeautifulSoup(html, "lxml")
        # Ищем объявления с типом House
        listings = soup.find_all("div", itemscope=True, itemtype="https://schema.org/House", class_="listing")
        for listing in listings:
            # Извлекаем количество комнат
            rooms_tag = listing.find("meta", itemprop="numberOfRooms")
            rooms = rooms_tag.get("content", "").strip() if rooms_tag else ""
            
            # Извлекаем площадь (floor size)
            area_tag = listing.find("meta", itemprop="floorSize")
            area = area_tag.get("content", "").strip() if area_tag else ""
            # Убираем единицы измерения и пробелы
            if area:
                area = area.replace("м2", "").replace("м²", "").strip()
            
            # Извлекаем адрес: сначала пробуем meta-тег, затем div с классом "address"
            address = ""
            address_tag = listing.find("meta", itemprop="address")
            if address_tag:
                address = address_tag.get("content", "").strip()
            else:
                div_address = listing.find("div", class_="address")
                if div_address:
                    address = div_address.get_text(separator=" ", strip=True)
            
            # Извлекаем цены: долларовая цена и цена в сомах
            price_dollars = ""
            price_soms = ""
            prices_block = listing.find("div", class_="listing-prices-block")
            if prices_block:
                price_tag = prices_block.find("div", class_="price")
                if price_tag:
                    raw_price = price_tag.get_text(strip=True)
                    # Оставляем только цифры и пробелы, нормализуем их
                    price_dollars = " ".join(re.sub(r'[^\d\s]', '', raw_price).split())
                price_add_tag = prices_block.find("div", class_="price-addition")
                if price_add_tag:
                    raw_price_add = price_add_tag.get_text(strip=True)
                    price_soms = " ".join(re.sub(r'[^\d\s]', '', raw_price_add).split())
            
            row = {
                "Количество комнат": rooms,
                "Площадь (м²)": area,
                "Адрес": address,
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
    # Разрешаем до 100 одновременных задач; фактическое число соединений ограничено TCPConnector.
    semaphore = asyncio.Semaphore(100)
    csv_lock = asyncio.Lock()
    fieldnames = ["Количество комнат", "Площадь (м²)", "Адрес", "Цена ($)", "Цена (сом)"]

    # Настраиваем TCPConnector с лимитом соединений, например, 50.
    connector = aiohttp.TCPConnector(limit=50)
    async with aiohttp.ClientSession(connector=connector) as session:
        with open("house/house_data.csv", "w", newline="", encoding="utf-8") as csv_file:
            csv_writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            csv_writer.writeheader()
            csv_file.flush()
            # Всего 226 страниц для парсинга
            tasks = [parse_page(page, session, semaphore, csv_writer, csv_file, csv_lock) for page in range(1, 227)]
            for task in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="Парсинг страниц"):
                await task
    print("Парсинг завершен. Данные сохранены в файле house_data.csv.")

if __name__ == "__main__":
    asyncio.run(main())
