import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
from collections import Counter
import requests
from bs4 import BeautifulSoup


SOURCE_NAME = "5 Колесо — LiveJournal"
BASE_URL = "https://5koleso.livejournal.com/"
DOMAIN = "5koleso.livejournal.com"
OUTPUT_FILE = Path("data/5koleso.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}

TIMEOUT = 20
MAX_ARTICLES = 10


def fetch_page(session, page_url):
    """Загружает страницу сайта."""
    try:
        response = session.get(
            page_url,
            timeout=TIMEOUT
        )
        response.raise_for_status()
        return response

    except requests.RequestException as error:
        print(f"Ошибка загрузки {page_url}: {error}")
        return None


def clean_text(value):
    """Удаляет лишние пробелы."""
    if not value:
        return None

    return re.sub(r"\s+", " ", value).strip() or None


def get_meta(soup, *names):
    """Извлекает значение из meta-тегов."""
    for name in names:
        tag = soup.find("meta", attrs={"property": name})

        if not tag:
            tag = soup.find("meta", attrs={"name": name})

        if tag and tag.get("content"):
            return clean_text(tag["content"])

    return None


def find_article_urls(soup):
    """Находит ссылки на отдельные публикации."""
    article_urls = set()

    for link in soup.find_all("a", href=True):
        article_url = urljoin(BASE_URL, link["href"])
        parsed = urlparse(article_url)

        if parsed.netloc.lower().split(":")[0] != DOMAIN:
            continue

        if re.fullmatch(r"/\d+\.html", parsed.path):
            article_urls.add(
                f"https://{DOMAIN}{parsed.path}"
            )

    return sorted(article_urls)

def extract_keywords(text, limit=10):
    """Выделяет повторяющиеся значимые слова и фразы."""
    if not text:
        return []

    stop_words = {
        "это", "как", "что", "для", "при", "или", "его",
        "она", "они", "этот", "эта", "эти", "также",
        "уже", "еще", "ещё", "все", "всё", "всех",
        "более", "менее", "который", "которая", "которые",
        "можно", "быть", "было", "были", "есть", "только",
        "очень", "свой", "свои", "своего", "после", "перед",
        "через", "между", "если", "когда", "потом", "здесь",
        "там", "него", "нее", "неё", "потому", "поэтому",
        "этом", "тогда", "даже", "тоже", "вообще", "просто",
        "именно", "например", "конечно", "сейчас", "теперь",
        "правда", "хотя", "немного", "много", "самый", "сама",
        "само", "сами", "стал", "стала", "стали", "стало",
        "будет", "будут", "может", "могут", "того", "этого",
        "такой", "такая", "такие", "таких", "того", "тоже",
        "всегда", "иногда", "часто", "почти", "вместе",
        "вроде", "вовсе", "поскольку", "поэтому", "однако",
        "кстати", "значит", "разумеется", "пока", "себя",
        "себе", "мне", "тебе", "нам", "вам", "них", "ним",
        "бы", "ли", "же", "не", "ни", "да", "нет", "ну",
        "машина", "машины"
    }

    # Находим слова в тексте
    words = re.findall(
        r"[а-яёa-z][а-яёa-z0-9-]{2,}",
        text.lower()
    )

    # Считаем только слова, не входящие в стоп-список
    word_counts = Counter(
        word for word in words
        if len(word) >= 4 and word not in stop_words
    )

    # Оставляем слова, которые встречаются хотя бы дважды
    word_keywords = [
        word
        for word, count in word_counts.most_common()
        if count >= 2
    ]

    # Ищем часто повторяющиеся пары соседних слов
    phrase_counts = Counter()

    for i in range(len(words) - 1):
        first = words[i]
        second = words[i + 1]

        if (
            len(first) >= 4
            and len(second) >= 4
            and first not in stop_words
            and second not in stop_words
        ):
            phrase_counts[f"{first} {second}"] += 1

    phrase_keywords = [
        phrase
        for phrase, count in phrase_counts.most_common()
        if count >= 2
    ]

    # Сначала значимые отдельные слова,
    # затем полезные повторяющиеся фразы
    result = word_keywords[:max(0, limit - 3)]

    for phrase in phrase_keywords:
        if phrase not in result and len(result) < limit:
            result.append(phrase)

    return result
def extract_important_sentences(text, keywords, title=None, limit=3):
    """Выбирает предложения, содержащие больше ключевых слов."""
    if not text:
        return []

    sentences = re.split(r"(?<=[.!?])\s+", text)
    scored_sentences = []

    for sentence in sentences:
        sentence = clean_text(sentence)

        if not sentence or len(sentence) < 50:
            continue

        # Не выводим заголовок как отдельный результат
        if title and sentence.strip() == title.strip():
            continue

        sentence_lower = sentence.lower()
        score = 0

        for keyword in keywords:
            if keyword.lower() in sentence_lower:
                if " " in keyword:
                    score += 2
                else:
                    score += 1

        if score > 0:
            scored_sentences.append((score, sentence))

    # Сначала выбираем предложения с большим числом совпадений
    scored_sentences.sort(
        key=lambda item: item[0],
        reverse=True
    )

    result = []

    for score, sentence in scored_sentences:
        if sentence not in result:
            result.append(sentence)

        if len(result) >= limit:
            break

    return result
def classify_topic(title, text):
    """Определяет тему статьи по заголовку."""

    # Если заголовок отсутствует, анализируем начало текста
    content = (title or "").lower()

    if not content:
        content = (text or "")[:500].lower()

    # Статьи об автомобильных добавках и сомнительных устройствах
    if any(word in content for word in [
        "улучшител",
        "турбин",
        "присадк",
        "бензин",
        "омагнич",
        "ионизатор",
        "лохотрон"
    ]):
        return "Автоаксессуары и присадки"

    # Обзоры конкретных автомобилей
    if any(word in content for word in [
        "haval",
        "кроссовер",
        "тест-драйв",
        "рестайлинг",
        "мультимедиа",
        "обновленный"
    ]):
        return "Обзоры автомобилей"

    # История автомобилей и автомобильного рынка
    if any(word in content for word in [
        "ссср",
        "советск",
        "послевоенное",
        "автопарк",
        "частных машин"
    ]):
        return "История автомобильного рынка"

    return "Другая тема"

def extract_article(article_url, html):
    """Извлекает данные отдельной публикации."""
    soup = BeautifulSoup(html, "lxml")

    # Заголовок
    title = (
        get_meta(soup, "og:title", "twitter:title")
        or (
            clean_text(soup.title.get_text(" ", strip=True))
            if soup.title
            else None
        )
    )

    # Ищем основной блок публикации
    article_container = (
        soup.select_one("article")
        or soup.select_one(".entry")
        or soup.select_one(".entry-content")
        or soup.select_one(".article")
    )

    text_container = article_container or soup.body or soup

    # Убираем технические элементы из текста публикации
    if article_container:
        for element in article_container.select(
            "script, style, nav, .comments, "
            ".b-comments, .entry-footer"
        ):
            element.decompose()

    raw_text = clean_text(
        text_container.get_text(" ", strip=True)
    )

    # Убираем всё перед заголовком статьи
    if raw_text and title:
        title_position = raw_text.find(title)

        if title_position != -1:
            raw_text = raw_text[title_position:]

    # Убираем рекомендации в конце, если они есть
    if raw_text:
        raw_text = raw_text.split(
            "Что еще почитать", 1
        )[0]

    text = clean_text(raw_text)

    # Автор
    author = get_meta(
        soup,
        "article:author",
        "author",
        "parsely-author"
    )

    if not author:
        author_tag = (
            soup.select_one(".ljuser")
            or soup.select_one(".author")
            or soup.select_one("[rel='author']")
        )

        if author_tag:
            author = clean_text(
                author_tag.get_text(" ", strip=True)
            )

    # Дата публикации
    published_at = get_meta(
        soup,
        "article:published_time",
        "og:published_time",
        "datePublished"
    )

    if not published_at:
        time_tag = soup.find("time")

        if time_tag:
            published_at = clean_text(
                time_tag.get("datetime")
                or time_tag.get_text(" ", strip=True)
            )

    return {
        "source_name": SOURCE_NAME,
        "source_type": "blog",
        "url": article_url,
        "title": title,
        "topic": classify_topic(title, text),
        "text": text,
        "important_phrases": extract_keywords(text),
        "important_sentences": extract_important_sentences(
    text,
    extract_keywords(text),
    title
),
        "author": author,
        "published_at": published_at,
        "collected_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "metadata": {
            "description": get_meta(
                soup,
                "og:description",
                "description"
            ),
            "language": (
                soup.html.get("lang")
                if soup.html
                else None
            )
        },
        "status": "success" if text else "partial"
    }


def main():
    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    articles = []

    with requests.Session() as session:
        session.headers.update(HEADERS)

        print("Загружаем:", BASE_URL)

        response = fetch_page(session, BASE_URL)

        if response is None:
            print("Не удалось загрузить главную страницу.")
            return

        homepage = BeautifulSoup(
            response.text,
            "lxml"
        )

        article_urls = find_article_urls(homepage)

        print("HTTP-код:", response.status_code)
        print(
            "Найдено публикаций:",
            len(article_urls)
        )

        if not article_urls:
            print(
                "Ссылки не найдены. "
                "Возможно, изменилась структура HTML "
                "или сайт ограничил доступ."
            )

        urls_to_process = article_urls[:MAX_ARTICLES]

        for index, article_url in enumerate(
            urls_to_process,
            start=1
        ):
            print(
                f"[{index}/{len(urls_to_process)}] "
                f"{article_url}"
            )

            article_response = fetch_page(
                session,
                article_url
            )

            if article_response is None:
                articles.append({
                    "source_name": SOURCE_NAME,
                    "source_type": "blog",
                    "url": article_url,
                    "title": None,
                    "text": None,
                    "author": None,
                    "published_at": None,
                    "collected_at": datetime.now(
                        timezone.utc
                    ).isoformat(),
                    "metadata": {},
                    "status": "error"
                })

                continue

            article = extract_article(
                article_url,
                article_response.text
            )

            article["http_status"] = (
                article_response.status_code
            )

            articles.append(article)

            # Не отправляем запросы слишком часто
            time.sleep(1)

    result = {
        "source_name": SOURCE_NAME,
        "source_url": BASE_URL,
        "retrieved_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "articles_found": len(article_urls),
        "articles_processed": len(articles),
        "articles": articles
    }

    with OUTPUT_FILE.open(
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            result,
            file,
            ensure_ascii=False,
            indent=2
        )

    successful = sum(
        article["status"] == "success"
        for article in articles
    )

    print("\nСбор завершён.")
    print("Обработано:", len(articles))
    print("С текстом:", successful)
    print("Файл сохранён:", OUTPUT_FILE.resolve())


if __name__ == "__main__":
    main()