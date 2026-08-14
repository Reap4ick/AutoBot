import asyncio
import logging
import os
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque

from dotenv import load_dotenv
from groq import Groq
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
GROQ_API_KEY = required_env("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
SYSTEM_PROMPT = os.getenv(
    "SYSTEM_PROMPT",
    """Ти відповідаєш у Telegram від імені власника акаунта. Відповідай лише на останнє повідомлення співрозмовника. Пиши природно, коротко і по суті мовою співрозмовника. Не додавай службових пояснень, внутрішніх міркувань, лапок або markdown. Не вигадуй фактів. Не обіцяй зустрічей, оплат, юридичних чи фінансових дій від імені власника. Якщо запит потребує рішення власника, скажи, що він відповість пізніше.""",
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
    text = (event.raw_text or "").strip()
    logger.info(
        "INCOMING chat_id=%s private=%s sender_id=%s text=%r",
        event.chat_id,
        event.is_private,
        event.sender_id,
        text[:200],
    )
    if event.sender_id is None or not text:
        logger.info("SKIP reason=empty_or_missing_sender chat_id=%s", event.chat_id)
        return False
    if text.startswith("/"):
        logger.info("SKIP reason=command chat_id=%s", event.chat_id)
        return False
    if ALLOWED_CHAT_IDS and event.chat_id not in ALLOWED_CHAT_IDS:
        logger.info("SKIP reason=chat_not_allowed chat_id=%s allowed=%s", event.chat_id, sorted(ALLOWED_CHAT_IDS))
        return False
    if not ALLOWED_CHAT_IDS and not event.is_private and not ALLOW_GROUPS:
        logger.info("SKIP reason=groups_disabled chat_id=%s", event.chat_id)
        return False
    logger.info("ACCEPT chat_id=%s", event.chat_id)
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
    logger.info("GROQ_REQUEST chat_id=%s model=%s input_chars=%s", chat_id, GROQ_MODEL, len(incoming_text))
    client = Groq(api_key=GROQ_API_KEY)

    def call_groq() -> str:
        completion = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=500,
        )
        return (completion.choices[0].message.content or "").strip()

    reply = await asyncio.to_thread(call_groq)
    result = reply[:MAX_OUTPUT_CHARS].strip()
    logger.info("GROQ_RESPONSE chat_id=%s output_chars=%s empty=%s", chat_id, len(result), not bool(result))
    return result


client = TelegramClient(SESSION_NAME, API_ID, API_HASH)


@client.on(events.NewMessage(incoming=True))
async def handle_message(event: events.NewMessage.Event) -> None:
    if not is_allowed(event):
        return

    chat_id = event.chat_id
    logger.info("HANDLER_START chat_id=%s", chat_id)
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
                logger.warning("Groq returned an empty response for chat %s", chat_id)
                return

            await asyncio.sleep(REPLY_DELAY_SECONDS)
            logger.info("TELEGRAM_SEND chat_id=%s text=%r", chat_id, reply[:200])
            await event.reply(reply)
            logger.info("TELEGRAM_SENT chat_id=%s", chat_id)
            state.history.append(f"Співрозмовник: {incoming_text}")
            state.history.append(f"Власник: {reply}")
            state.last_reply_at = time.monotonic()
        except FloodWaitError as exc:
            logger.warning("Telegram rate limit: wait %s seconds", exc.seconds)
            await asyncio.sleep(exc.seconds)
        except Exception:
            logger.exception("Failed to process message in chat %s", chat_id)


async def main() -> None:
    logger.info("Starting Telegram userbot with Groq model %s", GROQ_MODEL)
    logger.info(
        "CONFIG allowed_chat_ids=%s allow_groups=%s cooldown=%s delay=%s",
        sorted(ALLOWED_CHAT_IDS),
        ALLOW_GROUPS,
        COOLDOWN_SECONDS,
        REPLY_DELAY_SECONDS,
    )
    await client.start()
    me = await client.get_me()
    logger.info("Logged in as %s (id=%s)", me.username or me.first_name, me.id)
    await client.run_until_disconnected()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopped by user")
