import asyncio
import logging
import os
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque

from dotenv import load_dotenv
from google import genai
from google.genai import types
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("telegram_userbot")


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


API_ID = int(required_env("TG_API_ID"))
API_HASH = required_env("TG_API_HASH")
SESSION_NAME = os.getenv("TG_SESSION_NAME", "telegram_userbot")
GEMINI_API_KEY = required_env("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
SYSTEM_PROMPT = os.getenv(
    "SYSTEM_PROMPT",
    """Ти відповідаєш у Telegram від імені власника акаунта. Пиши природно, коротко і по суті, українською мовою, якщо співрозмовник не використовує іншу мову. Не вигадуй фактів. Не згадуй, що ти AI, якщо це не потрібно для чесної відповіді. Не обіцяй зустрічей, оплат, юридичних чи фінансових дій від імені власника. Якщо запит потребує рішення власника, скажи, що він відповість пізніше.""",
)


def parse_int_set(value: str) -> set[int]:
    result: set[int] = set()
    for item in value.split(","):
        item = item.strip()
        if item:
            result.add(int(item))
    return result


ALLOWED_CHAT_IDS = parse_int_set(os.getenv("ALLOWED_CHAT_IDS", ""))
ALLOW_GROUPS = os.getenv("ALLOW_GROUPS", "false").lower() in {"1", "true", "yes"}
REPLY_DELAY_SECONDS = float(os.getenv("REPLY_DELAY_SECONDS", "2"))
COOLDOWN_SECONDS = float(os.getenv("COOLDOWN_SECONDS", "15"))
MAX_HISTORY_MESSAGES = int(os.getenv("MAX_HISTORY_MESSAGES", "12"))
MAX_INPUT_CHARS = int(os.getenv("MAX_INPUT_CHARS", "4000"))
MAX_OUTPUT_CHARS = int(os.getenv("MAX_OUTPUT_CHARS", "2000"))


@dataclass
class ChatState:
    history: Deque[str]
    last_reply_at: float = 0.0
    lock: asyncio.Lock | None = None


states: dict[int, ChatState] = defaultdict(
    lambda: ChatState(history=deque(maxlen=MAX_HISTORY_MESSAGES), lock=asyncio.Lock())
)


def is_allowed(event: events.NewMessage.Event) -> bool:
    if event.sender_id is None or not event.raw_text.strip():
        return False
    if event.raw_text.lstrip().startswith("/"):
        return False
    if ALLOWED_CHAT_IDS and event.chat_id not in ALLOWED_CHAT_IDS:
        return False
    if not ALLOWED_CHAT_IDS and not event.is_private and not ALLOW_GROUPS:
        return False
    return True


def build_prompt(chat_id: int, incoming_text: str) -> str:
    history = "\n".join(states[chat_id].history)
    return (
        f"Попередній контекст цього діалогу:\n{history or '(немає)'}\n\n"
        f"Нове повідомлення співрозмовника:\n{incoming_text}\n\n"
        "Сформулюй лише готову відповідь для надсилання в Telegram, без пояснень і без лапок."
    )


async def generate_reply(chat_id: int, incoming_text: str) -> str:
    prompt = build_prompt(chat_id, incoming_text[:MAX_INPUT_CHARS])
    client = genai.Client(api_key=GEMINI_API_KEY)

    def call_gemini():
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.7,
                max_output_tokens=500,
            ),
        )
        return (response.text or "").strip()

    reply = await asyncio.to_thread(call_gemini)
    return reply[:MAX_OUTPUT_CHARS].strip()


client = TelegramClient(SESSION_NAME, API_ID, API_HASH)


@client.on(events.NewMessage(incoming=True))
async def handle_message(event: events.NewMessage.Event) -> None:
    if not is_allowed(event):
        return

    chat_id = event.chat_id
    state = states[chat_id]
    async with state.lock:
        now = time.monotonic()
        if now - state.last_reply_at < COOLDOWN_SECONDS:
            logger.info("Cooldown active for chat %s; message skipped", chat_id)
            return

        incoming_text = event.raw_text.strip()
        logger.info("Generating reply for chat %s", chat_id)
        try:
            reply = await generate_reply(chat_id, incoming_text)
            if not reply:
                logger.warning("Gemini returned an empty response for chat %s", chat_id)
                return

            await asyncio.sleep(REPLY_DELAY_SECONDS)
            await event.reply(reply)
            state.history.append(f"Співрозмовник: {incoming_text}")
            state.history.append(f"Власник: {reply}")
            state.last_reply_at = time.monotonic()
        except FloodWaitError as exc:
            logger.warning("Telegram rate limit: wait %s seconds", exc.seconds)
            await asyncio.sleep(exc.seconds)
        except Exception:
            logger.exception("Failed to process message in chat %s", chat_id)


async def main() -> None:
    logger.info("Starting Telegram userbot with model %s", GEMINI_MODEL)
    await client.start()
    me = await client.get_me()
    logger.info("Logged in as %s (id=%s)", me.username or me.first_name, me.id)
    await client.run_until_disconnected()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopped by user")
