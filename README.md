# 📅 Schedule Checker Bot

**Телеграм-бот для автоматичного моніторингу розкладу** Харківського житлово-комунального коледжу ім. Бекетова.

Бот щодня формує текстовий анонс розкладу вашої групи з Google Sheets і надсилає
його в Telegram. Окремо автоматично вітає одногрупників з днем народження! 🎂

---

## 🌟 Можливості

- **📅 Анонс розкладу** — читає базовий розклад, тиждень і заміни та надсилає готові пари, викладачів і посилання.
- **🎂 Привітання з ДН** — автоматично вітає одногрупників з днем народження.
- **🧠 Не спамить на вихідних** — не надсилає повідомлення в суботу та неділю. Зміни на понеділок перевіряються у п'ятницю.
- **💾 Пам'ять** — запам'ятовує, що вже перевірено та кого привітано. При перезапуску наздоганяє пропущені перевірки.
- **🔤 Розумний пошук** — знаходить групу незалежно від того, як її написали:
  - Кирилиця чи латиниця (`Т` або `T`, `К` або `K`, `І` або `I`)
  - Будь-яке тире: дефіс `-`, коротке тире `–`, довге тире `—`
  - З пробілами чи без: `Т-32`, `Т - 32`, `Т32`
- **⚙️ Універсальний** — працює з будь-якою групою. Просто змініть назву в налаштуваннях.

---

## 📋 Вимоги

- **Python 3.9** або новіше
- **Доступ до опублікованих Google Sheets CSV**
- **Телеграм-бот** (створюється безкоштовно)
- **Доступ до інтернету**

---

## 🚀 Покрокова інструкція з нуля

### Крок 1: Встановіть Python

#### Windows:
1. Перейдіть на [python.org/downloads](https://www.python.org/downloads/)
2. Натисніть жовту кнопку **"Download Python 3.x.x"**
3. Запустіть завантажений `.exe` файл
4. **⚠️ ОБОВ'ЯЗКОВО** поставте галочку **"Add Python to PATH"** внизу вікна установки
5. Натисніть **"Install Now"**
6. Перевірте, що Python встановився. Відкрийте **Командний рядок** (Win+R → `cmd` → Enter) і введіть:
   ```
   python --version
   ```
   Має з'явитися щось на кшталт: `Python 3.12.4`

#### Linux (Ubuntu/Debian):
```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv
```

### Крок 2: Встановіть залежності

Актуальна логіка читає опубліковані CSV напряму й не потребує Chrome для
формування анонсу. Chrome/Selenium залишені в requirements.txt для сумісності
зі старим режимом.

#### Windows:
- Завантажте з [google.com/chrome](https://www.google.com/chrome/) та встановіть

#### Linux (Ubuntu/Debian):
```bash
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo apt install ./google-chrome-stable_current_amd64.deb
```

### Крок 3: Створіть Телеграм-бота

1. Відкрийте Телеграм і знайдіть бота **[@BotFather](https://t.me/BotFather)**
2. Напишіть йому `/newbot`
3. Введіть **назву** бота (наприклад: `Розклад Т-22`)
4. Введіть **username** бота (наприклад: `t22_schedule_bot`). Має закінчуватися на `bot`
5. BotFather видасть вам **токен** — рядок виду `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`. **Збережіть його!**

### Крок 4: Додайте бота у Телеграм-групу та дізнайтеся ID групи

1. Створіть Телеграм-групу (або використайте існуючу)
2. Додайте вашого бота у групу
3. Зробіть бота **адміністратором** групи (Налаштування групи → Адміністратори → Додати → виберіть бота)
4. Щоб дізнатися **ID групи**, відкрийте у браузері:
   ```
   https://api.telegram.org/bot<ВАШ_ТОКЕН>/getUpdates
   ```
   Замініть `<ВАШ_ТОКЕН>` на токен з Кроку 3. Напишіть будь-яке повідомлення у групу, оновіть сторінку і знайдіть поле `"chat":{"id":-1234567890}`. Число з мінусом — це ID вашої групи.

### Крок 5: Завантажте бота

#### Варіант А: Через Git
```bash
git clone https://github.com/your-username/schedule-checker.git
cd schedule-checker
```

#### Варіант Б: Без Git
1. Завантажте ZIP з GitHub (зелена кнопка **"Code"** → **"Download ZIP"**)
2. Розпакуйте архів
3. Відкрийте папку в терміналі/командному рядку

### Крок 6: Встановіть залежності

#### Windows:
```bash
pip install -r requirements.txt
```

#### Linux:
```bash
pip3 install -r requirements.txt
```

Якщо отримали помилку `pip not found`, спробуйте:
```bash
python -m pip install -r requirements.txt
```

### Крок 7: Налаштуйте бота

1. Скопіюйте файл `.env.example` і назвіть його `.env`:
   
   **Windows:**
   ```bash
   copy .env.example .env
   ```
   
   **Linux:**
   ```bash
   cp .env.example .env
   ```

2. Відкрийте файл `.env` у будь-якому текстовому редакторі (Блокнот, VS Code, nano) і заповніть значення:

```env
# Токен вашого Телеграм-бота (з Кроку 3)
TELEGRAM_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz

# ID Телеграм-групи (з Кроку 4)
CHANNEL_ID=-1234567890

# Базовий розклад (CSV)
BASE_SCHEDULE_CSV_URL=https://docs.google.com/spreadsheets/d/YOUR_ID/export?format=csv&gid=0

# Предмети, скорочення, викладачі й посилання (CSV)
SUBJECTS_CSV_URL=https://docs.google.com/spreadsheets/d/YOUR_ID/export?format=csv&gid=832675788

# Діапазони НАД РИСКОЮ / ПІД РИСКОЮ (CSV)
SEMESTER_CSV_URL=https://docs.google.com/spreadsheets/d/YOUR_ID/export?format=csv&gid=1002009379

# Таблиця замін (CSV)
REPLACEMENTS_CSV_URL=https://docs.google.com/spreadsheets/d/e/YOUR_PUBLISHED_ID/pub?output=csv&gid=0

# Посилання на таблицю днів народження (CSV експорт)
BIRTHDAY_SHEET_URL=https://docs.google.com/spreadsheets/d/YOUR_ID/export?format=csv&gid=YOUR_GID

# Час перевірки розкладу (формат ГГ:ХХ)
SCHEDULE_CHECK_TIME=17:00

# Час перевірки днів народження (формат ГГ:ХХ)
BIRTHDAY_CHECK_TIME=08:00

# Назва вашої групи
SCHEDULE_GROUP=T-32

# Числовий приватний chat_id для python bot.py --test-schedule (не група)
PRIVATE_TEST_CHAT_ID=
PRIVATE_TEST_USERNAME=@pelia0
```

### Крок 8: Запустіть бота

```bash
python bot.py
```

Якщо все налаштовано правильно, ви побачите:
```
==================================================
[2026-04-02 20:00:00] 🤖 БОТ ЗАПУЩЕНИЙ. ДІАГНОСТИКА СТАНУ:
   📅 Остання перевірка розкладу: Ніколи
   🎂 Вже привітали в цьому році: 0 людей
   🔍 Група для пошуку: T-32
==================================================
```

**🎉 Вітаємо! Бот працює!**

---

## 📊 Налаштування Google Sheets

### Таблиця розкладу

1. Створіть або відкрийте Google Sheets таблицю з розкладом
2. Опублікуйте її: **Файл → Опублікувати в Інтернеті → Опублікувати**
3. Для нового режиму заповніть чотири CSV-змінні BASE_SCHEDULE_CSV_URL,
   SUBJECTS_CSV_URL, SEMESTER_CSV_URL і REPLACEMENTS_CSV_URL у `.env`.

### Таблиця днів народження

Таблиця повинна мати такі стовпці:

| Ім'я | Прізвище | Дата народження |
|------|----------|-----------------|
| Іван | Петренко | 15/03/2005 |
| Олена | Коваленко | 22/11/2004 |

1. Створіть Google Sheets з такою структурою
2. Скопіюйте посилання для CSV-експорту:
   - Відкрийте таблицю
   - У адресному рядку замініть `/edit...` на `/export?format=csv&gid=НОМЕР_АРКУША`
   - GID аркуша можна побачити в URL при перемиканні аркушів
3. Вставте посилання у `BIRTHDAY_SHEET_URL` в `.env`

---

## 🔍 Як працює пошук групи

Бот розумно шукає назву групи в тексті розкладу. Наприклад, для `SCHEDULE_GROUP=T-32`:

| Написання в таблиці | Знайде? | Пояснення |
|---------------------|---------|-----------|
| `Т-32` | ✅ | Стандартне написання |
| `T-32` | ✅ | Латинська "T" замість кириличної |
| `т - 32` | ✅ | Пробіли навколо тире |
| `Т—32` | ✅ | Довге тире |
| `T – 32` | ✅ | Коротке тире з пробілами |
| `Т32` | ✅ | Без тире |
| `T32` | ✅ | Латиниця, без тире |
| `ПТ-32` | ❌ | Інша група (з префіксом "П") |

---

## ☁️ Деплой (запуск 24/7)

Щоб бот працював постійно, його потрібно запустити на сервері. Нижче — безкоштовні варіанти.

### Варіант 1: Oracle Cloud Free Tier (рекомендовано) ⭐

Oracle надає **безкоштовний сервер назавжди** (Always Free). Це найкращий варіант.

1. Зареєструйтесь на [cloud.oracle.com](https://cloud.oracle.com/) (потрібна банківська картка для верифікації, але гроші НЕ знімають)
2. Створіть **VM Instance**:
   - Shape: `VM.Standard.E2.1.Micro` (Always Free)
   - Image: `Ubuntu 22.04`
3. Підключіться до сервера через SSH:
   ```bash
   ssh -i ваш_ключ.key ubuntu@IP_АДРЕСА_СЕРВЕРА
   ```
4. Встановіть все необхідне:
   ```bash
   # Оновлення системи
   sudo apt update && sudo apt upgrade -y
   
   # Python та pip
   sudo apt install python3 python3-pip python3-venv -y
   
   # Google Chrome
   wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
   sudo apt install ./google-chrome-stable_current_amd64.deb -y
   
   # Завантаження бота
   git clone https://github.com/your-username/schedule-checker.git
   cd schedule-checker
   
   # Встановлення залежностей
   pip3 install -r requirements.txt
   
   # Налаштування
   cp .env.example .env
   nano .env  # Заповніть свої дані
   ```
5. Запустіть бота через **systemd** (автозапуск):
   ```bash
   sudo nano /etc/systemd/system/schedule-bot.service
   ```
   Вставте:
   ```ini
   [Unit]
   Description=Schedule Checker Telegram Bot
   After=network.target
   
   [Service]
   Type=simple
   User=ubuntu
   WorkingDirectory=/home/ubuntu/schedule-checker
   ExecStart=/usr/bin/python3 /home/ubuntu/schedule-checker/bot.py
   Restart=always
   RestartSec=10
   
   [Install]
   WantedBy=multi-user.target
   ```
   Збережіть (Ctrl+O, Enter, Ctrl+X) та запустіть:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable schedule-bot
   sudo systemctl start schedule-bot
   ```
6. Перевірте статус:
   ```bash
   sudo systemctl status schedule-bot
   ```
7. Перегляд логів:
   ```bash
   journalctl -u schedule-bot -f
   ```

### Варіант 2: Render.com (простіше, але з обмеженнями)

Render має безкоштовний тариф для Background Workers, але **вимикає** сервіс після 15 хвилин бездіяльності на безкоштовному тарифі. Підходить, якщо у вас є платний план.

1. Зареєструйтесь на [render.com](https://render.com/)
2. Підключіть GitHub-репозиторій
3. Створіть **Background Worker**
4. Додайте змінні оточення (з `.env`) у налаштуваннях сервісу
5. Створіть файл `Dockerfile` у корені проєкту:
   ```dockerfile
   FROM python:3.11-slim
   
   # Встановлення Chrome
   RUN apt-get update && apt-get install -y \
       wget gnupg2 \
       && wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add - \
       && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
       && apt-get update && apt-get install -y google-chrome-stable \
       && rm -rf /var/lib/apt/lists/*
   
   WORKDIR /app
   COPY . .
   RUN pip install --no-cache-dir -r requirements.txt
   
   CMD ["python", "bot.py"]
   ```

### Варіант 3: Власний комп'ютер (найпростіше)

Просто запустіть бота на комп'ютері, який працює цілодобово.

#### Windows — запуск при старті системи:
1. Натисніть `Win+R`, введіть `shell:startup`, натисніть Enter
2. Створіть у відкритій папці файл `start_bot.bat` з вмістом:
   ```bat
   @echo off
   cd /d D:\schedule-checker
   python bot.py
   ```
   (Замініть `D:\schedule-checker` на шлях до папки з ботом)

#### Linux — запуск через systemd:
Використовуйте інструкцію з Варіанту 1, крок 5.

---

## 🛠️ Корисні команди

| Дія | Команда |
|-----|---------|
| Запустити бота | `python bot.py` |
| Зупинити бота | `Ctrl+C` |
| Переглянути логи (systemd) | `journalctl -u schedule-bot -f` |
| Перезапустити (systemd) | `sudo systemctl restart schedule-bot` |
| Зупинити (systemd) | `sudo systemctl stop schedule-bot` |

---

## 📁 Структура проєкту

```
schedule-checker/
├── bot.py              # Основний код бота
├── .env                # Ваші налаштування (НЕ пушити в git!)
├── .env.example        # Шаблон налаштувань
├── .gitignore          # Файли, які ігноруються git
├── requirements.txt    # Python-залежності
├── bot_state.json      # Стан бота (створюється автоматично)
└── README.md           # Цей файл
```

---

## ❓ Часті проблеми

### Бот пише "Помилка Selenium"
- Переконайтесь, що Google Chrome встановлений
- На Linux: перевірте `google-chrome --version`
- Драйвер Chrome завантажується автоматично (потрібен інтернет)

### Бот не надсилає повідомлення в групу
- Перевірте, що бот доданий у групу та є **адміністратором**
- Перевірте правильність `CHANNEL_ID` у `.env`
- Переконайтесь, що токен правильний

### Бот не знаходить групу
- Перевірте, що `SCHEDULE_GROUP` правильно вказаний у `.env`
- Перевірте, що BASE_SCHEDULE_CSV_URL, SUBJECTS_CSV_URL, SEMESTER_CSV_URL і
  REPLACEMENTS_CSV_URL ведуть на опубліковані CSV правильних аркушів
- Перевірте, що дата в SEMESTER_CSV_URL покриває потрібний день

### "pip not found" при встановленні залежностей
- Спробуйте `python -m pip install -r requirements.txt`
- Або `pip3 install -r requirements.txt`
- Переконайтесь, що Python встановлений з галочкою "Add to PATH"

---

## 📄 Ліцензія

MIT — використовуйте вільно.

---

## Актуальна реалізація для групи Т-32

Нова логіка більше не шукає групу скріншотом і не зашиває предмети в Python. Вона
читає чотири опубліковані CSV-джерела:

- базовий розклад на аркуші розкладу;
- аркуш предметів (повна назва, скорочення, посилання, викладач);
- аркуш семестрових тижнів;
- окрему таблицю замін.

При переході на новий семестр достатньо оновити Google Sheets. Код не містить
переліку пар, викладачів або предметів; адреси джерел задаються у .env через
BASE_SCHEDULE_CSV_URL, SUBJECTS_CSV_URL, SEMESTER_CSV_URL і REPLACEMENTS_CSV_URL.

### Як формується повідомлення

У базовому розкладі кожен час має два рядки: верхній (НАД РИСКОЮ) і нижній
(ПІД РИСКОЮ). Якщо заповнений лише один рядок, використовується його значення
щотижня. Якщо заповнені обидва, вибір робиться за діапазонами дат у таблиці
семестру. Позначки ---, ВІЛЬНА, ВІКНО та подібні виводяться як «🪟 Вікно».

Заміна прив'язується до дати, групи та номера пари, а не до повної назви
предмета. Це важливо, бо в офіційній таблиці можуть бути скорочення, друкарські
помилки або назва на кшталт ТОГГ. Скорочення з аркуша предметів зіставляються
з повною назвою; невідомі позначки не губляться, а додаються у попередження
повідомлення. Після переходу на іншу групу рядки попередньої групи більше не
підтягуються. Дубльовані номери пар також показуються як попередження.

### Час і захист від дублювання

Час планувальника — київський: о 17:00 анонсується наступний навчальний день
(у п'ятницю — понеділок), привітання з днем
народження о 08:00. Це два окремі повідомлення. Після успішної відправки
розклад позначається у bot_state.json; повторний запуск того самого дня його
не надсилає. Одночасно запускається лише один екземпляр бота — другий завершується
з помилкою блокування.

### Локальна перевірка перед будь-яким deploy

Перегляд повідомлення без Telegram:

~~~bash
python bot.py --preview-schedule
python bot.py --preview-schedule 2026-09-07
~~~

Приватний тест не використовує CHANNEL_ID:

~~~bash
python bot.py --test-schedule
~~~

Задайте PRIVATE_TEST_CHAT_ID числовим приватним chat_id. Якщо його немає,
бот спробує знайти PRIVATE_TEST_USERNAME (за замовчуванням @pelia0) серед
getUpdates; користувач має спочатку написати боту /start. Telegram Bot API
не приймає @username як chat_id для приватного чату, тому fallback у групу
заборонений.

Offline-тести парсера:

~~~bash
python -m unittest -v test_schedule_announcements.py
~~~

Поточна робоча копія тестується лише локально. Ця документація не виконує
deploy і не змінює стабільну версію на сервері.
