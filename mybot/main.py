import asyncio
import json
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import Command
from datetime import datetime
from playwright.async_api import async_playwright
import logging

API_TOKEN = '7897173101:AAEVo5DdY8vucYS8F83lQn5JDJSSN6GKk1E'  # <-- вставь сюда свой токен
STORAGE_FILE = 'sent_news.json'

bot = Bot(API_TOKEN)
dp = Dispatcher()

# Загружаем ранее отправленные новости
def load_sent_news():
    if os.path.exists(STORAGE_FILE):
        try:
            with open(STORAGE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return set(data)
        except (json.JSONDecodeError, ValueError):
            print("[!] Файл sent_news.json пустой или поврежден. Начинаем с пустого списка.")
            return set()
    return set()

# Сохраняем отправленные новости
def save_sent_news(news_ids):
    with open(STORAGE_FILE, 'w', encoding='utf-8') as f:
        json.dump(list(news_ids), f, ensure_ascii=False, indent=4)

sent_news_ids = load_sent_news()


async def fetch_news_list():
    url = "https://glavcom.ua/country/criminal.html"
    news_links = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        page = await browser.new_page()
        await page.goto(url, wait_until="domcontentloaded")

        items = await page.locator('div.article_title a').all()

        for item in items:
            href = await item.get_attribute('href')
            if href and href.startswith('/country/'):
                full_url = f'https://glavcom.ua{href}'
                news_links.append(full_url)

        await browser.close()

    return news_links


async def parse_news_page(news_url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        page = await browser.new_page()
        await page.goto(news_url, wait_until="domcontentloaded")

        try:
            title = await page.locator('h1.post_title').inner_text()
        except:
            title = 'Без заголовка'

        try:
            date_raw = await page.locator('time.article_date').get_attribute('datetime')
            date = datetime.fromisoformat(date_raw).strftime('%d.%m.%Y, %H:%M')
        except:
            date = 'Дата неизвестна'

        try:
            image_url = await page.locator('div.full-article img').get_attribute('src')
            if image_url and not image_url.startswith('http'):
                image_url = 'https://glavcom.ua' + image_url
        except:
            image_url = None

        try:
            paragraphs = await page.locator('div.article_content p').all()
            description = ''
            for p_elem in paragraphs:
                text = await p_elem.inner_text()
                description += text + '\n\n'
        except:
            description = 'Описание не найдено'

        await browser.close()

        return {
            'id': news_url,
            'title': title.strip(),
            'description': description.strip(),
            'date': date,
            'image_url': image_url,
            'portal': 'glavcom.ua'
        }



async def send_news(news, chat_id):
    try:
        # Сначала отправляем фото отдельно (если есть)
        if news['image_url']:
            await bot.send_photo(
                chat_id=chat_id,
                photo=news['image_url']
            )
        
        # Отправляем заголовок, описание и дату в одном сообщении
        text = (
            f"<b>{news['title']}</b>\n\n"
            f"{news['description']}\n\n"
            f"🗓 Дата: {news['date']}"
        )
        
        await bot.send_message(
            chat_id,
            text,
            parse_mode='HTML'
        )
    except Exception as e:
        logging.error(f"Ошибка при отправке новости: {e}")


async def news_checker():
    global sent_news_ids
    target_chat_id = None  # <-- сюда можно прописать ID чата, если хочешь отправлять в конкретный чат по умолчанию

    while True:
        news_links = await fetch_news_list()

        new_items = [link for link in news_links if link not in sent_news_ids]

        for link in reversed(new_items):  # Сначала самые старые новые
            news = await parse_news_page(link)
            if target_chat_id:
                await send_news(news, target_chat_id)
            sent_news_ids.add(news['id'])
            save_sent_news(sent_news_ids)

        await asyncio.sleep(300)  # Каждые 5 минут


@dp.message(Command('start'))
async def start_cmd(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='📰 Последняя новость', callback_data='latest_news')]
    ])

    await message.answer("Привет! Я бот новостей.\nБуду присылать свежие криминальные новости с glavcom.ua", reply_markup=keyboard)


@dp.callback_query(F.data == 'latest_news')
async def latest_news_callback(callback: types.CallbackQuery):
    await callback.answer(text="Загружаю новость...")

    latest_news_links = await fetch_news_list()

    if latest_news_links:
        latest_news_url = latest_news_links[0]
        news = await parse_news_page(latest_news_url)  # <- парсим всю статью
        await send_news(news, callback.message.chat.id)  # <- отправляем красиво
    else:
        await callback.message.answer("Не удалось получить последнюю новость.")




async def main():
    loop = asyncio.get_event_loop()
    loop.create_task(news_checker())
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
