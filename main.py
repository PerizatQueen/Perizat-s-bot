from flask import Flask, request
import requests
import os
import csv
import json
from datetime import datetime

app = Flask(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
OPENAI_KEY = os.environ.get("OPENAI_KEY", "")
TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
CSV_PATH = "/tmp/leads.csv"
CSV_HEADERS = ["Дата", "Компания", "Сфера", "Размер", "Страна",
               "Оценка", "Приоритет", "Причины", "Следующий шаг", "Срочность звонка"]


def tg_send(chat_id, text):
    requests.post(f"{TG_API}/sendMessage",
                  json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
                  timeout=10)


def gpt_analyze(company_name):
    prompt = f"""Ты эксперт B2B продаж. Проанализируй компанию "{company_name}" для продажи CRM-системы.
Наш продукт: CRM для отделов продаж. Целевые клиенты: компании 50+ сотрудников. Приоритет: IT, Финтех, Ритейл, Логистика, СНГ.

Верни ТОЛЬКО валидный JSON без markdown:
{{
  "company_name": "официальное название",
  "industry": "сфера",
  "size": "Стартап / Малая / Средняя / Крупная / Корпорация",
  "country": "страна",
  "founded_year": "год или null",
  "score": число 1-10,
  "priority": "🔥 Горячий / 🟡 Тёплый / 🧊 Холодный",
  "reasons": ["причина 1", "причина 2", "причина 3"],
  "risks": ["риск 1", "риск 2"],
  "recommended_action": "конкретное следующее действие",
  "call_urgency": "Сегодня / На этой неделе / Не срочно / Пропустить"
}}"""

    resp = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"},
        json={"model": "gpt-4o", "messages": [{"role": "user", "content": prompt}],
              "temperature": 0.2, "max_tokens": 600},
        timeout=40
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"].strip()
    if "```" in content:
        for part in content.split("```"):
            p = part.strip().lstrip("json").strip()
            if p.startswith("{"):
                return json.loads(p)
    return json.loads(content)


def save_csv(data):
    file_exists = os.path.exists(CSV_PATH)
    row = {
        "Дата": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "Компания": data.get("company_name", ""),
        "Сфера": data.get("industry", ""),
        "Размер": data.get("size", ""),
        "Страна": data.get("country", ""),
        "Оценка": data.get("score", 0),
        "Приоритет": data.get("priority", ""),
        "Причины": "; ".join(data.get("reasons", [])),
        "Следующий шаг": data.get("recommended_action", ""),
        "Срочность звонка": data.get("call_urgency", "")
    }
    with open(CSV_PATH, mode="a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)
    with open(CSV_PATH, encoding="utf-8-sig") as f:
        return sum(1 for _ in f) - 1


@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.get_json()
    msg = update.get("message", {})
    text = (msg.get("text") or "").strip()
    chat_id = msg.get("chat", {}).get("id")

    if not text or not chat_id:
        return "ok"

    if text.startswith("/start"):
        tg_send(chat_id,
                "👋 <b>Квалификатор лидов</b>\n\n"
                "Введите команду:\n<code>/lead Название компании</code>\n\n"
                "Пример: <code>/lead Kaspi.kz</code>\n\nОтвет придёт через ~10 сек ✅")

    elif text.lower().startswith("/lead"):
        parts = text.split(None, 1)
        if len(parts) < 2:
            tg_send(chat_id, "⚠️ Укажите название.\nПример: <code>/lead Kaspi.kz</code>")
            return "ok"

        company_name = parts[1].strip()
        tg_send(chat_id, f"🔍 Анализирую <b>{company_name}</b>...")

        try:
            data = gpt_analyze(company_name)
            total = save_csv(data)
            reasons_lines = "\n".join([f"  ✅ {r}" for r in data.get("reasons", [])])
            risks_lines = "\n".join([f"  ⚠️ {r}" for r in data.get("risks", [])])
            reply = (
                f"🏢 <b>{data.get('company_name', company_name)}</b>\n\n"
                f"📊 Сфера: {data.get('industry','—')}\n"
                f"🌍 Страна: {data.get('country','—')}\n"
                f"📏 Размер: {data.get('size','—')}\n"
                f"📅 Основана: {data.get('founded_year','—')}\n\n"
                f"<b>Оценка: {data.get('score','?')}/10  {data.get('priority','')}</b>\n"
                f"📞 Звонить: {data.get('call_urgency','—')}\n\n"
                f"➕ Почему стоит:\n{reasons_lines}\n\n"
                f"➖ Риски:\n{risks_lines}\n\n"
                f"🎯 Действие: {data.get('recommended_action','—')}\n\n"
                f"💾 Сохранено в leads.csv (всего: {total})"
            )
            tg_send(chat_id, reply)
        except Exception as e:
            tg_send(chat_id, f"❌ Ошибка: <code>{str(e)[:200]}</code>")

    return "ok"


@app.route("/")
def index():
    return "Lead Bot работает ✅"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
