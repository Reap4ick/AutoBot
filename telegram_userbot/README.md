# Telegram userbot + Gemini

Цей модуль відповідає на вхідні текстові повідомлення через **особистий Telegram-акаунт** і генерує відповіді за допомогою Gemini. За замовчуванням він обробляє лише приватні чати; для безпечної роботи рекомендується явно вказати `ALLOWED_CHAT_IDS`.

## 1. Підготувати ключі

Створи Telegram API application на [my.telegram.org](https://my.telegram.org) і отримай `api_id` та `api_hash`. Окремо створи Gemini API key в [Google AI Studio](https://aistudio.google.com/apikey). Не публікуй ці значення та не коміть файл `.env` або `.session` у Git.

## 2. Встановити на Ubuntu/Debian

```bash
sudo apt update
sudo apt install -y python3 python3-venv
cd /opt
sudo git clone <URL_ЦЬОГО_РЕПОЗИТОРІЮ> SpotShort
sudo chown -R "$USER":"$USER" /opt/SpotShort
cd /opt/SpotShort/telegram_userbot
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
nano .env
```

У `ALLOWED_CHAT_IDS` вкажи ID чатів через кому. Порожнє значення разом із `ALLOW_GROUPS=false` означає «усі приватні чати», тому для реального акаунта краще використовувати явний список.

## 3. Перша авторизація

Перший запуск потрібно виконати вручну в SSH-сесії, щоб ввести номер телефону, код Telegram і, якщо ввімкнено, пароль двофакторної автентифікації:

```bash
cd /opt/SpotShort/telegram_userbot
. .venv/bin/activate
python main.py
```

Після успішної авторизації Telethon створить файл сесії `telegram_userbot.session`. Цей файл є фактично активною сесією акаунта, тому збережи права доступу `chmod 600 *.session` і не передавай його стороннім.

Зупини процес через `Ctrl+C` після перевірки входу.

## 4. Запуск як сервіс

Скопіюй `telegram-userbot.service` у systemd, перевір шляхи та запусти:

```bash
sudo cp telegram-userbot.service /etc/systemd/system/telegram-userbot.service
sudo systemctl daemon-reload
sudo systemctl enable --now telegram-userbot
sudo systemctl status telegram-userbot
journalctl -u telegram-userbot -f
```

## Поведінка та обмеження

Бот ігнорує власні повідомлення, команди, порожній текст, заборонені чати та групи, якщо `ALLOW_GROUPS=false`. Між відповідями діє cooldown, а кожен чат має коротку історію контексту в пам’яті процесу. У разі помилки Gemini повідомлення не надсилається.

Не використовуй цей код для масових розсилок, спаму, обходу обмежень Telegram або автоматичних дій, які можуть створити юридичні чи фінансові зобов’язання. Перевіряй перші відповіді вручну та вимкни сервіс, якщо поведінка моделі некоректна.

## Перевірка коду

```bash
python -m py_compile main.py
```
