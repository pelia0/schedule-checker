# -*- coding: utf-8 -*-
"""
Schedule Checker Bot — Телеграм-бот для моніторингу розкладу
Харківського житлово-комунального коледжу ім. Бекетова.

Основні можливості:
- Щоденна перевірка Google Sheets таблиці розкладу на наявність вашої групи
- Автоматичні привітання з днем народження
- Розумний пошук: враховує кирилицю/латиницю, різні тире, пробіли
- Не спамить на вихідних (субота, неділя)

Автор: ХЖКК ім. Бекетова
"""

import time
import sys
import re
import schedule
import requests
import os
import json
import pandas as pd
from datetime import datetime, date, timedelta
from io import StringIO
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from dotenv import load_dotenv

# Завантажуємо змінні оточення з файлу .env
load_dotenv()

# --- Конфігурація з .env файлу ---
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')       # Токен Телеграм-бота
CHANNEL_ID = os.getenv('CHANNEL_ID')               # ID Телеграм-групи/каналу
# HTML-версія старої таблиці замін, яка використовується для скріншота.
# SCHEDULE_URL збережено як назву для сумісності зі старим .env.
SCHEDULE_URL = os.getenv('SCHEDULE_URL')
REPLACEMENTS_HTML_URL = os.getenv('REPLACEMENTS_HTML_URL') or SCHEDULE_URL
BIRTHDAY_SHEET_URL = os.getenv('BIRTHDAY_SHEET_URL')  # Посилання на таблицю днів народження
BIRTHDAY_CHECK_TIME = os.getenv('BIRTHDAY_CHECK_TIME', '08:00')  # Час перевірки ДН
# Ранковий анонс розкладу і вечірня перевірка замін — різні задачі.
SCHEDULE_ANNOUNCEMENT_TIME = os.getenv('SCHEDULE_ANNOUNCEMENT_TIME', '08:00')
# SCHEDULE_CHECK_TIME — стара назва вечірньої перевірки; залишаємо fallback,
# щоб оновлення .env не було обов'язковим для старих інсталяцій.
REPLACEMENTS_CHECK_TIME = os.getenv(
    'REPLACEMENTS_CHECK_TIME',
    os.getenv('SCHEDULE_CHECK_TIME', '17:00'),
)
# Публічне ім'я для старих викликів/інтеграцій.
SCHEDULE_CHECK_TIME = REPLACEMENTS_CHECK_TIME

# Назва групи для пошуку (наприклад: "Т-22", "А-31", "КІ-15")
SCHEDULE_GROUP = os.getenv('SCHEDULE_GROUP', 'T-32')

# Файл для збереження стану бота (що вже перевірено, кого привітано)
STATE_FILE = "bot_state.json"

# Таблиця відповідності візуально однакових кириличних та латинських літер.
# Це потрібно, тому що в таблиці розкладу група може бути написана
# як кирилицею ("Т-22"), так і латиницею ("T-22"), і бот повинен
# знаходити обидва варіанти.
CYRILLIC_TO_LATIN = {
    'А': 'A', 'В': 'B', 'С': 'C', 'Е': 'E', 'Н': 'H',
    'І': 'I', 'К': 'K', 'М': 'M', 'О': 'O', 'Р': 'P',
    'Т': 'T', 'Х': 'X',
    'а': 'a', 'в': 'b', 'с': 'c', 'е': 'e', 'н': 'h',
    'і': 'i', 'к': 'k', 'м': 'm', 'о': 'o', 'р': 'p',
    'т': 't', 'х': 'x',
}
# Зворотня таблиця: латиниця → кирилиця
LATIN_TO_CYRILLIC = {v: k for k, v in CYRILLIC_TO_LATIN.items()}


def log(message):
    """Виводить повідомлення з поточним часом у консоль."""
    rendered = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}"
    try:
        print(rendered)
    except UnicodeEncodeError:
        encoding = getattr(getattr(sys, "stdout", None), "encoding", None) or "utf-8"
        print(rendered.encode(encoding, errors="replace").decode(encoding, errors="replace"))


# =============================================================================
#  РОБОТА ЗІ СТАНОМ БОТА (збереження/завантаження)
# =============================================================================

def load_state():
    """
    Завантажує стан бота з JSON-файлу.
    Стан містить: дату останньої перевірки розкладу та список привітаних.
    """
    if not os.path.exists(STATE_FILE):
        return {"last_schedule_check": "", "greeted_birthdays": []}
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {"last_schedule_check": "", "greeted_birthdays": []}


def save_state(state):
    """Зберігає стан бота у JSON-файл."""
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=4)


def mark_schedule_announcement(target_day=None):
    """Позначає успішний ранковий анонс базового розкладу."""
    target_day = target_day or _kyiv_now().date()
    state = load_state()
    state['last_schedule_announcement'] = target_day.isoformat()
    save_state(state)
    log("💾 Ранковий анонс розкладу позначено виконаним.")


def mark_replacements_checked(target_day=None):
    """Позначає успішну вечірню перевірку таблиці замін."""
    target_day = target_day or _kyiv_now().date()
    state = load_state()
    state['last_replacements_check'] = target_day.isoformat()
    save_state(state)
    log("💾 Перевірку замін позначено виконаною.")


def mark_schedule_checked():
    """Сумісність зі старою версією: маркер перевірки розкладу."""
    state = load_state()
    state['last_schedule_check'] = _kyiv_now().date().isoformat()
    save_state(state)
    log("💾 Записав у файл: Розклад на сьогодні перевірено.")


def mark_birthday_greeted(key):
    """Позначає, що людину вже привітали з ДН у цьому році."""
    state = load_state()
    if key not in state['greeted_birthdays']:
        state['greeted_birthdays'].append(key)
        save_state(state)
        log(f"💾 Записав у файл: Привітання для '{key}' відправлено.")


# =============================================================================
#  РОБОТА З ТАБЛИЦЕЮ ДНІВ НАРОДЖЕННЯ
# =============================================================================

def get_birthday_data():
    """
    Завантажує таблицю днів народження з Google Sheets.
    Таблиця повинна мати стовпці: Ім'я, Прізвище, Дата народження.
    """
    try:
        response = requests.get(BIRTHDAY_SHEET_URL)
        response.encoding = 'utf-8'
        if response.status_code != 200:
            return pd.DataFrame()
        df = pd.read_csv(StringIO(response.text), on_bad_lines='skip')
        df.columns = df.columns.str.strip()
        return df
    except Exception as e:
        log(f"⚠️ Помилка скачування таблиці ДН: {e}")
        return pd.DataFrame()


# =============================================================================
#  ДІАГНОСТИКА ПРИ ЗАПУСКУ
# =============================================================================

def print_startup_status():
    """
    Виводить діагностичну інформацію при запуску бота:
    - Дата останньої перевірки розкладу
    - Кількість привітаних у цьому році
    - Назва групи для пошуку
    - Найближчий день народження
    """
    print("\n" + "=" * 50)
    log("🤖 БОТ ЗАПУЩЕНИЙ. ДІАГНОСТИКА СТАНУ:")

    state = load_state()
    print(f"   📅 Останній ранковий анонс: {state.get('last_schedule_announcement', 'Ніколи')}")
    print(f"   🔎 Остання перевірка замін: {state.get('last_replacements_check', 'Ніколи')}")
    print(f"   ⏰ Анонс / ДН / заміни: {SCHEDULE_ANNOUNCEMENT_TIME} / {BIRTHDAY_CHECK_TIME} / {REPLACEMENTS_CHECK_TIME}")
    print(f"   🎂 Вже привітали в цьому році: {len(state.get('greeted_birthdays', []))} людей")
    print(f"   🔍 Група для пошуку: {SCHEDULE_GROUP}")

    df = get_birthday_data()
    if not df.empty:
        today = _kyiv_now().replace(hour=0, minute=0, second=0, microsecond=0)
        upcoming = []
        for index, row in df.iterrows():
            try:
                name = str(row["Ім'я"]).strip()
                surname = str(row['Прізвище']).strip()
                dob = datetime.strptime(str(row['Дата народження']).strip(), '%d/%m/%Y')

                bday_this = dob.replace(year=today.year)
                if bday_this < today:
                    next_bday = dob.replace(year=today.year + 1)
                else:
                    next_bday = bday_this

                days = (next_bday - today).days
                upcoming.append({'name': f"{name} {surname}", 'days': days, 'date': next_bday.strftime('%d.%m')})
            except Exception:
                continue

        if upcoming:
            upcoming.sort(key=lambda x: x['days'])
            near = upcoming[0]
            print(f"   👉 Найближче свято: {near['name']} (через {near['days']} днів, {near['date']})")

    print("=" * 50 + "\n")


# =============================================================================
#  ВІДПРАВКА ПОВІДОМЛЕНЬ У ТЕЛЕГРАМ
# =============================================================================

def _legacy_send_message(text):
    """Legacy wrapper: send to the configured group exactly once."""
    if not TELEGRAM_TOKEN or not CHANNEL_ID:
        return False
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": CHANNEL_ID, "text": text},
            timeout=25,
        )
        return response.ok
    except Exception:
        return False


def _legacy_send_photo(photo_path, caption):
    """Legacy wrapper: send a photo to the configured group exactly once."""
    if not TELEGRAM_TOKEN or not CHANNEL_ID:
        return False
    try:
        with open(photo_path, "rb") as photo:
            response = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto",
                data={"chat_id": CHANNEL_ID, "caption": caption, "parse_mode": "Markdown"},
                files={"photo": photo},
                timeout=30,
            )
        return response.ok
    except Exception:
        return False


# =============================================================================
#  РОЗУМНИЙ ПОШУК ГРУПИ В ТЕКСТІ
# =============================================================================

def is_schedule_check_allowed():
    """
    Перевіряє, чи дозволено сьогодні перевіряти розклад.

    Логіка вихідних:
    - П'ятниця: перевіряємо (зміни на понеділок)
    - Субота: НЕ перевіряємо (щоб не спамити)
    - Неділя: НЕ перевіряємо (щоб не спамити)
    - Інші дні: перевіряємо як зазвичай
    """
    today = _kyiv_now()
    weekday = today.weekday()  # 0=Пн, 1=Вт, 2=Ср, 3=Чт, 4=Пт, 5=Сб, 6=Нд

    if weekday in (5, 6):  # Субота або Неділя
        log("📅 Сьогодні вихідний — пропускаю перевірку розкладу (зміни на понеділок перевіряються у п'ятницю).")
        return False

    return True


def build_group_pattern(group_name):
    """
    Будує регулярний вираз (regex) для пошуку назви групи в тексті.

    Враховує всі можливі варіації написання:
    - Кирилиця та латиниця: Т↔T, К↔K, І↔I, А↔A тощо
    - Різні тире: дефіс (-), коротке тире (–), довге тире (—)
    - Пробіли навколо тире або без них
    - Запис без тире (наприклад, Т22 замість Т-22)

    Приклади для групи "Т-22":
    ✅ Знайде: Т-22, T-22, т - 22, Т—22, T – 22, Т22, T22
    ❌ НЕ знайде: трова І.Л. 22, тєєва Н.В. 22, ПТ-22, Т-221

    Аргументи:
        group_name: Назва групи з .env (наприклад, "Т-22", "КІ-15")

    Повертає:
        Рядок з regex-патерном для re.findall()
    """
    # Розбиваємо назву групи на літерну частину та номер
    # Наприклад: "Т-22" → літери="Т", номер="22"
    #            "КІ-15" → літери="КІ", номер="15"
    match = re.match(r'^([A-Za-zА-Яа-яІіЇїЄєҐґ]+)\s*[-–—]?\s*(\d+)$', group_name.strip())
    if not match:
        # Якщо формат не розпізнано — шукаємо як є
        log(f"⚠️ Не вдалося розпарсити групу '{group_name}', шукаю як точний текст.")
        return re.escape(group_name)

    letters = match.group(1)  # Літерна частина (наприклад, "Т" або "КІ")
    number = match.group(2)   # Числова частина (наприклад, "22" або "15")

    # Для кожної літери створюємо набір варіантів (кирилиця + латиниця)
    # Наприклад: "Т" → [TtТт], "К" → [KkКк]
    letter_patterns = []
    for char in letters:
        upper = char.upper()
        lower = char.lower()
        variants = {upper, lower}

        # Додаємо двійника (кирилиця↔латиниця)
        if upper in CYRILLIC_TO_LATIN:
            lat = CYRILLIC_TO_LATIN[upper]
            variants.add(lat)
            variants.add(lat.lower())
        elif upper in LATIN_TO_CYRILLIC:
            cyr = LATIN_TO_CYRILLIC[upper]
            variants.add(cyr)
            variants.add(cyr.lower())

        if len(variants) > 1:
            letter_patterns.append(f"[{''.join(sorted(variants))}]")
        else:
            letter_patterns.append(re.escape(char))

    letters_regex = ''.join(letter_patterns)
    number_escaped = re.escape(number)

    # Фінальний патерн складається з двох альтернатив:
    # 1) ЛІТЕРИ + (пробіли)? + тире + (пробіли)? + ЦИФРИ   → "Т - 22", "T—22"
    # 2) ЛІТЕРИ + ЦИФРИ (без тире)                          → "Т22", "T22"
    #
    # (?<![літери]) — перед групою не повинно бути іншої літери (щоб "ПТ-22" не матчилось)
    # (?!\d) — після номера не повинна йти ще цифра (щоб "Т-221" не матчилось)
    lookbehind = r'(?<![A-Za-zА-Яа-яІіЇїЄєҐґ])'
    lookahead = r'(?!\d)'

    pattern = (
        rf'{lookbehind}{letters_regex}\s*[-–—]\s*{number_escaped}{lookahead}'
        rf'|'
        rf'{lookbehind}{letters_regex}{number_escaped}{lookahead}'
    )

    return pattern


def find_group_in_text(text):
    """
    Шукає згадку групи у тексті розкладу.

    Використовує розумний regex, побудований функцією build_group_pattern(),
    який враховує всі варіації написання.

    Повертає:
        Список знайдених входжень (рядки) або порожній список.
    """
    pattern = build_group_pattern(SCHEDULE_GROUP)
    matches = re.findall(pattern, text, re.IGNORECASE)
    return matches


# =============================================================================
#  ПЕРЕВІРКА РОЗКЛАДУ (основна функція)
# =============================================================================

def check_replacements_screenshot(force=False):
    """Перевіряє стару таблицю замін і надсилає її скріншот для нашої групи."""
    log("🔎 Починаю перевірку таблиці замін...")

    if not force and not is_schedule_check_allowed():
        return False

    target_day = _kyiv_now().date()
    today_str = target_day.isoformat()
    state = load_state()
    if not force and state.get("last_replacements_check") == today_str:
        log("✅ Таблицю замін за сьогодні вже перевірено. Пропускаю.")
        return False

    if not REPLACEMENTS_HTML_URL:
        log("❌ Не задано REPLACEMENTS_HTML_URL або SCHEDULE_URL; скріншот не зроблено.")
        return False

    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--window-size=1000,1300")
    chrome_options.add_argument("--disable-dev-shm-usage")

    driver = None
    filename = None
    try:
        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=chrome_options,
        )
        driver.get(REPLACEMENTS_HTML_URL)

        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.TAG_NAME, "td"))
            )
        except Exception:
            pass

        full_text = driver.find_element(By.TAG_NAME, "body").text
        clean_text = full_text.replace("\xa0", " ")
        found_matches = find_group_in_text(clean_text)

        if found_matches:
            found_str = ", ".join(sorted(set(found_matches)))
            log(f"🚨 ЗНАЙДЕНО ГРУПУ В ЗАМІНАХ: {found_str}")
            filename = f"replacements_{int(time.time())}.png"
            driver.save_screenshot(filename)
            caption = "🚨 *Зміни в розкладі!*\nЗнайдено: " + found_str
            if force:
                caption += "\n_(Перевірка після відновлення роботи бота)_"
            if not send_photo(filename, caption):
                log("⚠️ Скріншот замін не підтверджено Telegram.")
        else:
            log(f"💤 Групу {SCHEDULE_GROUP} у таблиці замін не знайдено (розклад чистий).")

        mark_replacements_checked(target_day)
        return True
    except Exception as exc:
        log(f"❌ Помилка перевірки таблиці замін: {exc}")
        return False
    finally:
        if filename and os.path.exists(filename):
            try:
                os.remove(filename)
            except OSError:
                pass
        if driver:
            driver.quit()

# Legacy startup task runner was replaced by run_missed_tasks below, which handles
# the morning announcement, daily birthdays, and evening replacement screenshot
# independently.

# =============================================================================
#  ПРИВІТАННЯ З ДНЕМ НАРОДЖЕННЯ
# =============================================================================

def process_birthdays():
    """
    Перевіряє таблицю днів народження та відправляє привітання.

    Логіка:
    - Якщо ДН сьогодні — вітає в день народження
    - Якщо ДН було 1-2 дні тому і не привітали — вітає із запізненням
    - Якщо вже привітали цього року — пропускає
    """
    log("🎂 Починаю перевірку днів народження...")
    df = get_birthday_data()
    if df.empty:
        log("❌ Таблиця ДН пуста або недоступна.")
        return

    today = _kyiv_now().replace(hour=0, minute=0, second=0, microsecond=0)
    current_year = today.year
    state = load_state()

    for index, row in df.iterrows():
        try:
            name = str(row["Ім'я"]).strip()
            surname = str(row['Прізвище']).strip()
            dob_str = str(row['Дата народження']).strip()

            # Підтримка двох форматів дати: ДД/ММ/РРРР та ДД.ММ.РРРР
            try:
                dob = datetime.strptime(dob_str, '%d/%m/%Y')
            except ValueError:
                dob = datetime.strptime(dob_str, '%d.%m.%Y')

            bday_this_year = dob.replace(year=current_year)
            delta = (today - bday_this_year).days

            # ДН сьогодні (delta=0) або було 1-2 дні тому (delta=1,2)
            if 0 <= delta <= 2:
                unique_key = f"{name}_{surname}_{current_year}"

                # Перевіряємо чи вже привітали
                if unique_key in state['greeted_birthdays']:
                    log(f"ℹ️ {name} {surname} (ДН: {dob_str}) - Вже привітано. Пропуск.")
                    continue

                age = current_year - dob.year

                if delta == 0:
                    # ДН сьогодні
                    msg = (f"Всім привіт! Сьогодні свій {age}-й День Народження святкує "
                           f"{name} {surname}! 🥳\n\nДавайте всі разом привітаємо!")
                    log(f"🎉 СЬОГОДНІ ДН: {name} {surname}. Відправляю вітання!")
                else:
                    # ДН було нещодавно — вітаємо із запізненням
                    msg = (f"Всім привіт! 🐢 Вибачте за запізнення!\n"
                           f"Нещодавно ({bday_this_year.strftime('%d.%m')}) свій {age}-й День Народження "
                           f"відсвяткував(ла) {name} {surname}! 🥳\n\nВітаємо!")
                    log(f"🐢 ПРОПУЩЕНИЙ ДН: {name} {surname}. Відправляю з вибаченням.")

                if send_message(msg):
                    mark_birthday_greeted(unique_key)
                else:
                    log(f"⚠️ Вітання для {name} {surname} не підтверджено Telegram; повторимо пізніше.")

        except Exception:
            continue
    log("🏁 Перевірка ДН завершена.")


# =============================================================================
#  ТОЧКА ВХОДУ — ЗАПУСК БОТА
# =============================================================================

from schedule_announcements import build_daily_announcement, ScheduleDataError


def _kyiv_now():
    try:
        from zoneinfo import ZoneInfo
        try:
            return datetime.now(ZoneInfo("Europe/Kyiv"))
        except Exception:
            return datetime.now(ZoneInfo("Europe/Kiev"))
    except Exception:
        return datetime.now()


def _time_reached(now, value):
    try:
        hour, minute = (int(part) for part in value.strip().split(":", 1))
        return (now.hour, now.minute) >= (hour, minute)
    except (AttributeError, TypeError, ValueError):
        log(f"⚠️ Некоректний час у конфігурації: {value!r}")
        return False


def _next_school_day(day):
    candidate = day + timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate


def send_message(text, chat_id=None, parse_mode=None):
    """Send exactly one Telegram message to the requested chat."""
    target = str(chat_id if chat_id is not None else CHANNEL_ID or "").strip()
    if not target:
        log("❌ Не задано Telegram chat_id; повідомлення не відправлено.")
        return False
    if not TELEGRAM_TOKEN:
        log("❌ Не задано TELEGRAM_TOKEN; повідомлення не відправлено.")
        return False

    payload = {"chat_id": target, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json=payload,
            timeout=25,
        )
        data = response.json()
        if response.ok and data.get("ok"):
            log(f"✅ Повідомлення відправлено в Telegram chat_id={target}.")
            return True
        log(f"❌ Telegram не прийняв повідомлення: {data.get('description', response.status_code)}")
    except Exception as exc:
        log(f"❌ Помилка відправки повідомлення в Telegram: {exc}")
    return False


def send_photo(photo_path, caption, chat_id=None):
    """Compatibility helper that also sends to exactly one target."""
    target = str(chat_id if chat_id is not None else CHANNEL_ID or "").strip()
    if not target or not TELEGRAM_TOKEN:
        log("❌ Не задано Telegram target/token; фото не відправлено.")
        return False
    try:
        with open(photo_path, "rb") as photo:
            response = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto",
                data={"chat_id": target, "caption": caption, "parse_mode": "Markdown"},
                files={"photo": photo},
                timeout=30,
            )
        data = response.json()
        if response.ok and data.get("ok"):
            return True
        log(f"❌ Telegram не прийняв фото: {data.get('description', response.status_code)}")
    except Exception as exc:
        log(f"❌ Помилка відправки фото в Telegram: {exc}")
    return False


def check_schedule(force=False, target_chat_id=None, dry_run=False, target_day=None):
    """Build and send the data-driven daily schedule announcement."""
    now = _kyiv_now()
    target_day = target_day or now.date()
    if not force and target_day.weekday() >= 5:
        log("🛌 Вихідний: анонс розкладу не потрібен.")
        return False

    state = load_state()
    today_str = target_day.isoformat()
    if not force and state.get("last_schedule_announcement") == today_str:
        log("✅ Анонс розкладу за сьогодні вже відправлено. Пропускаю.")
        return False

    try:
        message, diagnostics = build_daily_announcement(target_day)
    except ScheduleDataError as exc:
        log(f"❌ Не вдалося побудувати анонс розкладу: {exc}")
        return False
    except Exception as exc:
        log(f"❌ Непередбачена помилка побудови розкладу: {exc}")
        return False

    if dry_run:
        try:
            print(message)
            print("\n[diagnostics]", diagnostics)
        except UnicodeEncodeError:
            encoding = getattr(getattr(sys, "stdout", None), "encoding", None) or "utf-8"
            rendered = message + "\n\n[diagnostics] " + repr(diagnostics)
            print(rendered.encode(encoding, errors="replace").decode(encoding, errors="replace"))
        return True

    target = target_chat_id if target_chat_id is not None else CHANNEL_ID
    if not send_message(message, chat_id=target, parse_mode="HTML"):
        return False

    # A private test must never mark the group announcement as complete.
    if target_chat_id is None:
        mark_schedule_announcement(target_day)
    return True


def _run_scheduled_schedule_announcement():
    """Плановий ранковий анонс розкладу лише в робочі дні."""
    now = _kyiv_now()
    if now.weekday() >= 5:
        log("🛌 Вихідний: ранковий анонс розкладу не потрібен.")
        return False
    return check_schedule(target_day=now.date())


def _run_scheduled_replacements_check():
    """Планова вечірня перевірка старої таблиці замін лише в робочі дні."""
    now = _kyiv_now()
    if now.weekday() >= 5:
        log("🛌 Вихідний: перевірку замін пропускаю.")
        return False
    return check_replacements_screenshot()


def run_missed_tasks():
    """Run each independent job if its Kyiv-time deadline has passed."""
    now = _kyiv_now()
    log("🔄 Перевіряю пропущені завдання...")
    state = load_state()
    today_str = now.date().isoformat()
    is_weekday = now.weekday() < 5

    # 1. Ранковий анонс розкладу: понеділок-п'ятниця о 08:00.
    if is_weekday:
        if _time_reached(now, SCHEDULE_ANNOUNCEMENT_TIME):
            if state.get("last_schedule_announcement") != today_str:
                check_schedule(target_day=now.date())
            else:
                log("✅ Ранковий анонс розкладу за сьогодні вже відправлено.")
        else:
            log(f"🕒 Для ранкового анонсу ще рано; час запуску {SCHEDULE_ANNOUNCEMENT_TIME}.")
    else:
        log("🛌 Вихідний: ранковий анонс розкладу пропускаю.")

    # 2. Дні народження: щодня о 08:00, включно з вихідними.
    if _time_reached(now, BIRTHDAY_CHECK_TIME):
        process_birthdays()
    else:
        log(f"🕒 Для привітань ще рано; час запуску {BIRTHDAY_CHECK_TIME}.")

    # 3. Стара перевірка таблиці замін зі скріншотом: робочі дні о 17:00.
    if is_weekday:
        if _time_reached(now, REPLACEMENTS_CHECK_TIME):
            if state.get("last_replacements_check") != today_str:
                check_replacements_screenshot()
            else:
                log("✅ Таблицю замін за сьогодні вже перевірено.")
        else:
            log(f"🕒 Для перевірки замін ще рано; час запуску {REPLACEMENTS_CHECK_TIME}.")
    else:
        log("🛌 Вихідний: вечірню перевірку замін пропускаю.")

def _resolve_private_test_target(username=None):
    """Resolve @username to a private chat id from updates, never to CHANNEL_ID."""
    explicit = (os.getenv("PRIVATE_TEST_CHAT_ID") or "").strip()
    candidate = (username or explicit or os.getenv("PRIVATE_TEST_USERNAME") or "@pelia0").strip()
    if candidate and not candidate.startswith("@"):
        if not candidate.isdigit():
            raise RuntimeError("PRIVATE_TEST_CHAT_ID має бути додатним числовим private chat_id")
        return candidate
    if not TELEGRAM_TOKEN:
        raise RuntimeError("для приватного тесту потрібен TELEGRAM_TOKEN")

    wanted = candidate.lstrip("@").casefold()
    response = requests.get(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
        params={"limit": 100},
        timeout=20,
    )
    data = response.json()
    if not response.ok or not data.get("ok"):
        raise RuntimeError("Telegram getUpdates не повернув дані")
    for update in data.get("result", []):
        for key in ("message", "edited_message", "channel_post", "edited_channel_post"):
            event = update.get(key) or {}
            chat = event.get("chat") or {}
            sender = event.get("from") or {}
            if chat.get("type") != "private":
                continue
            usernames = {
                str(chat.get("username") or "").lstrip("@").casefold(),
                str(sender.get("username") or "").lstrip("@").casefold(),
            }
            if wanted in usernames and chat.get("id") is not None:
                return str(chat["id"])
    raise RuntimeError(
        f"Не знайдено {candidate} у getUpdates. Напишіть боту /start, "
        "або задайте PRIVATE_TEST_CHAT_ID числовим chat_id."
    )


def _schedule_daily(job, clock):
    try:
        return schedule.every().day.at(clock, "Europe/Kyiv").do(job)
    except (TypeError, ValueError):
        return schedule.every().day.at(clock).do(job)


_INSTANCE_LOCK_HANDLE = None


def _acquire_single_instance():
    """Prevent two local bot processes from sending duplicate messages."""
    global _INSTANCE_LOCK_HANDLE
    try:
        handle = open("bot.instance.lock", "a+")
        try:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except ImportError:
            import msvcrt
            handle.seek(0)
            handle.write("0")
            handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except (BlockingIOError, OSError):
            handle.close()
            return False
        _INSTANCE_LOCK_HANDLE = handle
        return True
    except OSError:
        return False


if __name__ == "__main__":
    if "--preview-schedule" in sys.argv or "--test-schedule" in sys.argv:
        if "--test-schedule" in sys.argv:
            try:
                index = sys.argv.index("--test-schedule")
                argument = sys.argv[index + 1] if index + 1 < len(sys.argv) else None
                target = _resolve_private_test_target(argument)
                raise SystemExit(0 if check_schedule(force=True, target_chat_id=target) else 1)
            except Exception as exc:
                log(f"❌ Приватний тест не виконано: {exc}")
                raise SystemExit(1)
        try:
            index = sys.argv.index("--preview-schedule")
            argument = sys.argv[index + 1] if index + 1 < len(sys.argv) else None
            preview_day = date.fromisoformat(argument) if argument and not argument.startswith("--") else None
            result = check_schedule(force=True, dry_run=True, target_day=preview_day)
            raise SystemExit(0 if result else 1)
        except ValueError:
            log("❌ Дата preview має формат YYYY-MM-DD.")
            raise SystemExit(1)

    # Перевірка наявності обов'язкових змінних оточення
    missing = []
    for var in ['TELEGRAM_TOKEN', 'CHANNEL_ID', 'BIRTHDAY_SHEET_URL', 'SCHEDULE_GROUP',
                'BASE_SCHEDULE_CSV_URL', 'SUBJECTS_CSV_URL', 'SEMESTER_CSV_URL',
                'REPLACEMENTS_CSV_URL']:
        if not os.getenv(var):
            missing.append(var)
    if missing:
        print(f"❌ Помилка: Не знайдено обов'язкових змінних у .env: {', '.join(missing)}")
        print("   Скопіюйте .env.example в .env та заповніть значення.")
        exit(1)

    if not _acquire_single_instance():
        print("❌ Інший екземпляр бота вже працює; запуск скасовано.")
        raise SystemExit(2)

    # Діагностика при запуску
    print_startup_status()

    # Виконуємо пропущені завдання (якщо бот був вимкнений)
    run_missed_tasks()

    # Плануємо три незалежні завдання.
    _schedule_daily(_run_scheduled_schedule_announcement, SCHEDULE_ANNOUNCEMENT_TIME)
    _schedule_daily(process_birthdays, BIRTHDAY_CHECK_TIME)
    _schedule_daily(_run_scheduled_replacements_check, REPLACEMENTS_CHECK_TIME)

    log(f"📅 Планувальник активовано. Чекаю наступну задачу...")

    # Головний цикл — перевіряємо кожну хвилину, чи не час виконати завдання
    while True:
        schedule.run_pending()
        time.sleep(60)










