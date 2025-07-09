import asyncio
import json
import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from datetime import datetime
from playwright.async_api import async_playwright

OPENROUTER_API_KEY = "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"
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

async def summarize_text(title: str, description: str, max_length: int = 1000) -> str:
    combined_text = f"{title}\n\n{description}"
    prompt = (
        f"Ти — редактор популярного новинного Telegram-каналу. "
        f"Стисни текст нижче до {max_length} символів, але постарайся використати майже всю доступну довжину — не скорочуй надмірно. "
        f"1. Створи окремий яскравий, динамічний заголовок, який одразу привертає увагу. Уникай перевантаження деталями. "
        f"2. Далі — опис: змістовний, логічно завершений, емоційний, без зайвого канцеляризму. "
        f"Якщо в тексті згадується стать особи (наприклад: чоловік або жінка), не змінюй її. Не плутай персонажів. "
        f"Не обривай думки або речення. Уникай сухості або повторів. "
        f"Не додавай емодзі, хештеги або спеціальне форматування — бот це зробить сам. "
        f"Розділи заголовок і опис двома переносами рядка. Пиши Українською - без помилок\n\n{combined_text}"
    )


    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://your-telegram-bot.com",
        "X-Title": "TelegramNewsBot",
    }

    json_data = {
        "model": "mistralai/mistral-small-3.2-24b-instruct-2506:free",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 1500
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(OPENROUTER_API_URL, headers=headers, json=json_data) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["choices"][0]["message"]["content"].strip()
                else:
                    print(f"❌ OpenRouter API error: {resp.status}")
                    print(await resp.text())
                    return combined_text[:max_length]
    except Exception as e:
        print(f"❌ Ошибка при запросе к OpenRouter: {e}")
        return combined_text[:max_length]


MAX_CAPTION_LENGTH = 1024
MAX_MESSAGE_LENGTH = 4096

TOKEN = "7897173101:AAEVo5DdY8vucYS8F83lQn5JDJSSN6GKk1E"
CHAT_ID = '-1002672492906'
BASE_URL = "https://glavcom.ua"
NEWS_URL = "https://glavcom.ua/country/criminal.html"
UNN_URL = "https://unn.ua/criminal"
UNN_BASE_URL = "https://unn.ua"
NEWS_FILE = "sent_news.json"

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())


def load_sent_news():
    try:
        with open(NEWS_FILE, "r", encoding="utf-8") as file:
            return set(json.load(file))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()

def save_sent_news(sent_news):
    with open(NEWS_FILE, "w", encoding="utf-8") as file:
        json.dump(list(sent_news), file, ensure_ascii=False, indent=4)

sent_news = load_sent_news()

async def fetch_news_list():
    news_items = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(NEWS_URL, timeout=30000)
        await page.wait_for_selector(".article_body", timeout=10000)

        articles = await page.query_selector_all(".article_body")

        for article in articles[:1]:
            title_el = await article.query_selector(".article_title a")
            time_el = await article.query_selector(".article_date")

            title = await title_el.inner_text() if title_el else "Без заголовка"
            link = BASE_URL + await title_el.get_attribute("href") if title_el else None
            pub_time = await time_el.inner_text() if time_el else "Время неизвестно"

            full_description = ""
            image_urls = []

            if link:
                article_page = await browser.new_page()
                try:
                    await article_page.goto(link, timeout=30000)
                    await article_page.wait_for_selector("article.post", timeout=10000)

                    article_container = await article_page.query_selector("article.post")
                    if article_container:
                        paragraphs = await article_container.query_selector_all("p, ul li")
                        for p in paragraphs:
                            is_in_reference = await p.evaluate("""
                                (node) => {
                                    let parent = node.parentElement;
                                    while(parent) {
                                        if (parent.classList && parent.classList.contains('post_reference') && parent.classList.contains('lgrey')) {
                                            return true;
                                        }
                                        parent = parent.parentElement;
                                    }
                                    return false;
                                }
                            """)
                            if is_in_reference:
                                continue

                            text = (await p.inner_text()).strip()
                            if not text or len(text) < 30:
                                continue
                            full_description += text + "\n\n"

                    image_elements = await article_page.query_selector_all(".post_img img, .post_photo img, .glide__slide img")
                    for img in image_elements:
                        img_url = await img.get_attribute("src")
                        if img_url:
                            if not img_url.startswith("http"):
                                img_url = BASE_URL + img_url
                            image_urls.append(img_url)

                except Exception as e:
                    print(f"⚠️ Ошибка при загрузке статьи: {link}\n{e}")
                finally:
                    await article_page.close()

            news_items.append((title.strip(), link, full_description.strip(), image_urls, pub_time.strip()))

        await browser.close()
    return news_items


async def fetch_unn_news():
    news_items = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(UNN_URL, timeout=30000)
        await page.wait_for_selector(".home-page_main__3lEa_", timeout=10000)

        news_links = await page.eval_on_selector_all(
            ".home-page_main__3lEa_ a.news-card_root__S0MnP.news-card_primary__3IGip:not(.carousel_root__jPlpy)",
            "els => els.map(el => el.href)"
        )

        for link in news_links[:1]:
            article_page = await browser.new_page()
            try:
                await article_page.goto(link, timeout=30000)
                await article_page.wait_for_selector(".single-news-card_newsTitle__qeEWY", timeout=10000)

                title = await article_page.text_content(".single-news-card_newsTitle__qeEWY")
                short_desc_el = await article_page.query_selector(".single-news-card_announce__f7WVB p")
                body_paragraphs = await article_page.query_selector_all(".single-news-card_body__w0_Jb p")

                description = ""
                if short_desc_el:
                    description += (await short_desc_el.text_content()).strip() + "\n\n"
                for p in body_paragraphs:
                    text = (await p.text_content()).strip()
                    if text and len(text) > 30:
                        description += text + "\n\n"

                image_elements = await article_page.query_selector_all(".single-news-card_body__w0_Jb img")
                image_urls = []
                for img in image_elements:
                    src = await img.get_attribute("src")
                    if src and src.startswith("http"):
                        image_urls.append(src)

                pub_time = datetime.now().strftime("%d.%m.%Y %H:%M")
                news_items.append((title.strip(), link, description.strip(), image_urls, pub_time))

            except Exception as e:
                print(f"⚠️ Ошибка при загрузке UNN статьи: {link}\n{e}")
            finally:
                await article_page.close()

        await browser.close()
    return news_items


async def send_news_item(title, link, description, image_urls, pub_time, source=""):
    summary = await summarize_text(title, description, max_length=1000)

    if image_urls:
        for img_url in image_urls:
            await bot.send_photo(chat_id=CHAT_ID, photo=img_url, caption=None, parse_mode="HTML")

    text_main = summary
    main_msg = await bot.send_message(chat_id=CHAT_ID, text=text_main, parse_mode="HTML")

    source_text = f"📰 Джерело: {source}\n" if source else ""
    text_info = f"{source_text}🕒 {pub_time}\n🔗 <a href='{link}'>Читати повністю</a>"

    await bot.send_message(
        chat_id=CHAT_ID,
        text=text_info,
        parse_mode="HTML",
        reply_to_message_id=main_msg.message_id,
        disable_notification=True
    )


async def send_initial_news():
    glavcom_news = await fetch_news_list()
    unn_news = await fetch_unn_news()
    news_list = glavcom_news + unn_news

    new_news = [news for news in news_list if news[1] not in sent_news]

    for title, link, description, image_urls, pub_time in new_news:
        sent_news.add(link)
        save_sent_news(sent_news)
        source = "UNN" if "unn.ua" in link else "Главком"
        summary = await summarize_text(title, description, max_length=1000)
        text = f"📖 <code>{summary}</code>\n\n🕒 {pub_time}\n🔗 <a href='{link}'>Читати повністю</a>"

        try:
            if image_urls:
                for img_url in image_urls:
                    await bot.send_photo(chat_id=CHAT_ID, photo=img_url, caption="", parse_mode="HTML")
                await bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="HTML")
            else:
                await bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="HTML")
        except Exception as e:
            print(f"Ошибка при отправке новости: {e}")


async def check_for_updates():
    global sent_news
    while True:
        glavcom_news = await fetch_news_list()
        unn_news = await fetch_unn_news()
        news_list = glavcom_news + unn_news

        new_news_found = False

        for title, link, description, image_urls, pub_time in news_list:
            print(f"Проверка новости: {title} — {link}")

            if link not in sent_news:
                sent_news.add(link)
                save_sent_news(sent_news)
                new_news_found = True

                source = "UNN" if "unn.ua" in link else "Главком"
                await send_news_item(title, link, description, image_urls, pub_time, source=source)

        if not new_news_found:
            print("Новых новостей нет.")

        await asyncio.sleep(300)  # Проверяем каждые 5 минут


@dp.message(Command("news"))
async def send_news(message: Message):
    glavcom_news = await fetch_news_list()
    unn_news = await fetch_unn_news()
    news_list = glavcom_news + unn_news

    new_news = [news for news in news_list if news[1] not in sent_news]

    if not new_news:
        await message.answer("Новостей пока нет.")
        return

    for title, link, description, image_urls, pub_time in new_news:
        sent_news.add(link)
        save_sent_news(sent_news)
        source = "UNN" if "unn.ua" in link else "Главком"
        summary = await summarize_text(title, description, max_length=1000)
        text = f"📖 <code>{summary}</code>\n\n🕒 {pub_time}\n🔗 <a href='{link}'>Читати повністю</a>"

        if image_urls:
            for img_url in image_urls:
                await message.answer_photo(img_url, caption="", parse_mode="HTML")
            await message.answer(text, parse_mode="HTML")
        else:
            await message.answer(text, parse_mode="HTML")


async def main():
    news_list = await fetch_news_list()
    unn_news = await fetch_unn_news()
    combined_news = news_list + unn_news

    for title, link, description, image_urls, pub_time in combined_news:
        if link not in sent_news:
            sent_news.add(link)
            save_sent_news(sent_news)
            source = "UNN" if "unn.ua" in link else "Главком"
            await send_news_item(title, link, description, image_urls, pub_time, source=source)
            break

    asyncio.create_task(check_for_updates())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
