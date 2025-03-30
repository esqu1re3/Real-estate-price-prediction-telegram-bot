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

async def parse_page(page_number, session, semaphore, results):
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
            
            # Извлекаем этаж (например, "15 этаж из 16")
            floor_info = ""
            title_tag = listing.find("p", class_="title")
            if title_tag:
                title_text = title_tag.get_text(separator=" ", strip=True)
                match = re.search(r'(\d+)\s*этаж\s*из\s*(\d+)', title_text)
                if match:
                    floor_info = f"{match.group(1)} этаж из {match.group(2)}"
            
            # Извлекаем полный адрес
            address_tag = listing.find("div", class_="address")
            full_address = address_tag.get_text(separator=" ", strip=True) if address_tag else ""
            
            # Извлекаем цены (доллары и сомы)
            price_dollars = ""
            price_soms = ""
            prices_block = listing.find("div", class_="listing-prices-block")
            if prices_block:
                price_tag = prices_block.find("div", class_="price")
                if price_tag:
                    price_dollars = price_tag.get_text(strip=True)
                price_add_tag = prices_block.find("div", class_="price-addition")
                if price_add_tag:
                    price_soms = price_add_tag.get_text(strip=True)
            
            results.append({
                "Количество комнат": rooms,
                "Площадь": area,
                "Этаж": floor_info,
                "Полный адрес": full_address,
                "Цена (доллары)": price_dollars,
                "Цена (сомы)": price_soms
            })
    except Exception as e:
        print(f"Ошибка на странице {page_number}: {e}")

async def main():
    semaphore = asyncio.Semaphore(15)
    results = []
    async with aiohttp.ClientSession() as session:
        tasks = [parse_page(page, session, semaphore, results) for page in range(1, 900)]
        # Обходим завершённые задачи с обновлением прогресс-бара
        for task in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="Парсинг страниц"):
            await task

    # Сохраняем данные в CSV файл
    fieldnames = ["Количество комнат", "Площадь", "Этаж", "Полный адрес", "Цена (доллары)", "Цена (сомы)"]
    with open("house_kyrgyzstan.csv", "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)
    print("Парсинг завершен. Данные сохранены в файле house_kyrgyzstan.csv.")

if __name__ == "__main__":
    asyncio.run(main())