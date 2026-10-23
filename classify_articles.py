import json
from pathlib import Path
from collections import Counter

DATA_DIR = Path("data")

INPUT_FILE = DATA_DIR / "normalized_articles.json"
OUTPUT_FILE = DATA_DIR / "classified_articles.json"
SUMMARY_FILE = DATA_DIR / "classification_summary.json"


# Тематические категории и ключевые слова
TOPICS = {
    "Автомобили и транспорт": [
        "автомоб", "машин", "дтп", "краш-тест",
        "автокресл", "changan", "deepal",
        "geely", "suzuki", "volvo", "двигател",
        "трасс", "пешеход", "drive2",
    ],
    "Технологии и ПО": [
    "компьютер", "смартфон", "android",
    "windows", "процессор", "планшет",
    "bitwarden", "keepass", "парол", "wi-fi",
    ],
    "Финансы и банки": [
        "банк", "сбер", "кредит", "вклад",
        "банковск", "перевод", "дебетовая карта",
    ],
    "Туризм и путешествия": [
        "путешеств", "туризм", "отель",
        "отпуск", "ozon travel", "билет",
        "бронирован", "перелёт", "перелет",
    ],
    "Потребительский опыт": [
        "отзыв", "покуп", "заказ", "доставк",
        "поддержк", "качество", "обслуживан",
    ],
}

POSITIVE_WORDS = [
    "отличн", "прекрасн", "понравил",
    "удобн", "доволен", "довольна",
    "качествен", "спасибо", "рекомендую",
]

NEGATIVE_WORDS = [
    "ужас", "плох", "разочарован",
    "проблем", "ошибк", "не работает",
    "неудобн", "обман", "жалоб",
    "бесполез", "не понравил",
]

def classify_article(article):
    title = article.get("title") or ""
    text = article.get("text") or ""

    title_lower = title.casefold()
    body_lower = text.casefold()
    content = f"{title} {text}".casefold()

    topics = []
    matched_keywords = set()

    for topic, keywords in TOPICS.items():
        # Совпадения в заголовке считаем более показательными
        title_hits = {
            word for word in keywords
            if word.casefold() in title_lower
        }

        # Совпадения в тексте проверяем отдельно
        body_hits = {
            word for word in keywords
            if word.casefold() in body_lower
        }

        matched_keywords.update(title_hits)
        matched_keywords.update(body_hits)

        # В тексте нужно минимум два разных ключевых слова
        if title_hits or len(body_hits) >= 2:
            topics.append(topic)

    # Простая предварительная оценка тональности
    positive = sum(
        content.count(word) for word in POSITIVE_WORDS
    )

    negative = sum(
        content.count(word) for word in NEGATIVE_WORDS
    )

    if positive > negative:
        sentiment = "положительная"
    elif negative > positive:
        sentiment = "отрицательная"
    else:
        sentiment = "нейтральная/не определена"

    article["topics"] = topics or ["прочее"]
    article["matched_keywords"] = sorted(matched_keywords)
    article["sentiment"] = sentiment

    return article

def main():
    with INPUT_FILE.open(encoding="utf-8") as file:
        data = json.load(file)

    articles = [
        classify_article(article)
        for article in data.get("articles", [])
    ]

    topic_counts = Counter()
    sentiment_counts = Counter()
    source_counts = Counter()

    for article in articles:
        # Все публикации учитываем в статистике источников
        source_counts.update([article.get("source_key", "unknown")])

    # Повторное содержимое не учитываем дважды в аналитике
        if article.get("duplicate_content"):
            continue

        topic_counts.update(article["topics"])
        sentiment_counts.update([article["sentiment"]])

    with OUTPUT_FILE.open("w", encoding="utf-8") as file:
        json.dump(
            {
                "articles_count": len(articles),
                "articles": articles,
            },
            file,
            ensure_ascii=False,
            indent=2,
        )

    with SUMMARY_FILE.open("w", encoding="utf-8") as file:
        json.dump(
            {
                "articles_count": len(articles),
                "topics": dict(topic_counts.most_common()),
                "sentiment": dict(sentiment_counts),
                "sources": dict(source_counts),
            },
            file,
            ensure_ascii=False,
            indent=2,
        )

    print("Классификация завершена.")
    print("Обработано записей:", len(articles))
    print("\nТемы:")

    for topic, count in topic_counts.most_common():
        print(f"- {topic}: {count}")

    print("\nТональность:")

    for sentiment, count in sentiment_counts.items():
        print(f"- {sentiment}: {count}")

    print("\nРезультаты:")
    print(OUTPUT_FILE)
    print(SUMMARY_FILE)


if __name__ == "__main__":
    main()