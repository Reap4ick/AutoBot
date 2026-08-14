# Telegram userbot + Groq

Цей модуль відповідає на вхідні текстові повідомлення через **особистий Telegram-акаунт** і генерує відповіді за допомогою Groq API. За замовчуванням він обробляє лише приватні чати; для безпечної роботи рекомендується явно вказати `ALLOWED_CHAT_IDS`.

## 1. Підготувати ключі

Створи Telegram API application на [my.telegram.org](https://my.telegram.org) і отримай `api_id` та `api_hash`. Окремо створи Groq API key у [Groq Console](https://console.groq.com/keys). Не публікуй ці значення та не коміть файл `.env` або `.session` у Git.

За замовчуванням використовується production-модель `llama-3.3-70b-versatile`. Її можна змінити через `GROQ_MODEL`.

## 2. Встановити на Ubuntu/Debian

```bash
sudo apt update
sudo apt install -y python3 python3-venv
cd /opt
git clone https://github.com/Reap4ick/AutoBot.git
cd /opt/AutoBot/telegram_userbot
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
nano .env
```

У `ALLOWED_CHAT_IDS` вкажи ID чатів через кому. Порожнє значення разом із `ALLOW_GROUPS=false` означає «усі приватні чати», тому для реального акаунта краще використовувати явний список.

## 3. Встановити на Windows

У CMD або PowerShell виконай:

```bat
cd C:\Users\Hp\Desktop\AutoBot\telegram_userbot
py -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
notepad .env
```

У `.env` обов'язково вкажи `GROQ_API_KEY`, `TG_API_ID` і `TG_API_HASH`.

## 4. Перша авторизація

Перший запуск потрібно виконати вручну, щоб ввести номер телефону, код Telegram і, якщо ввімкнено, пароль двофакторної автентифікації.

На Windows:

```bat
cd C:\Users\Hp\Desktop\AutoBot\telegram_userbot
.venv\Scripts\python.exe main.py
```

На Linux:

```bash
cd /opt/AutoBot/telegram_userbot
. .venv/bin/activate
python main.py
```

Після успішної авторизації Telethon створить файл сесії `telegram_userbot.session`. Цей файл є фактично активною сесією акаунта, тому не передавай його стороннім і не додавай у Git.

## 5. Запуск як сервіс на Linux

```bash
cd /opt/AutoBot/telegram_userbot
sudo cp telegram-userbot.service /etc/systemd/system/telegram-userbot.service
sudo systemctl daemon-reload
sudo systemctl enable --now telegram-userbot
sudo systemctl status telegram-userbot
journalctl -u telegram-userbot -f
```

## Поведінка та обмеження

Userbot ігнорує власні повідомлення, команди, порожній текст, заборонені чати та групи, якщо `ALLOW_GROUPS=false`. Між відповідями діє cooldown, а кожен чат має коротку історію контексту в пам'яті процесу. У разі помилки Groq повідомлення не надсилається. У логах використовуються маркери `GROQ_REQUEST`, `GROQ_RESPONSE`, `TELEGRAM_SEND` і `TELEGRAM_SENT`.

Не використовуй цей код для масових розсилок, спаму, обходу обмежень Telegram або автоматичних дій, які можуть створити юридичні чи фінансові зобов'язання. Перевіряй перші відповіді вручну та вимкни процес, якщо поведінка моделі некоректна.

## Перевірка коду

```bash
python -m py_compile main.py
```

Офіційний Groq quickstart використовує пакет `groq`, змінну `GROQ_API_KEY` і метод `client.chat.completions.create` [1].

[1]: https://console.groq.com/docs/quickstart
