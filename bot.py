import asyncio
import html
import logging
import os
import re

from anthropic import AsyncAnthropic
from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import Application, ContextTypes, MessageHandler, filters

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("hotro-bot")

TELEGRAM_TOKEN = os.environ["8287419825:AAFsjCvqeYZgjXYRT_b48wID81R7AVvu_OU"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")
TRIGGER = os.getenv("TRIGGER", "@hotro")  # từ khoá kích hoạt bot

SYSTEM_PROMPT = (
    "Bạn là trợ lý AI thân thiện trong nhóm Telegram, tên là Hỗ Trợ. "
    "Trả lời bằng ngôn ngữ của người hỏi (mặc định tiếng Việt), ngắn gọn, tự nhiên, dễ hiểu. "
    "Bạn có thể trò chuyện về mọi chủ đề: tình cảm, cuộc sống, học tập, công việc, giải trí, "
    "kiến thức về cờ bạc/xác suất, v.v. Hãy trung thực và đưa ra thông tin hữu ích, "
    "kể cả cảnh báo rủi ro khi thật sự cần thiết."
)

client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
trigger_re = re.compile(re.escape(TRIGGER), re.IGNORECASE)


def split_text(text: str, limit: int = 3800):
    """Chia nhỏ tin nhắn dài (Telegram giới hạn 4096 ký tự)."""
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = limit
        yield text[:cut]
        text = text[cut:].lstrip("\n")
    if text:
        yield text


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user
    if not msg or not msg.text or not user:
        return

    if not trigger_re.search(msg.text):
        return

    question = trigger_re.sub("", msg.text).strip()

    # Nếu người dùng reply vào tin nhắn khác thì đưa thêm làm ngữ cảnh
    quoted = ""
    if msg.reply_to_message and msg.reply_to_message.text:
        quoted = msg.reply_to_message.text.strip()

    if not question and not quoted:
        await msg.reply_text("Bạn cần hỏi gì? Gõ: @hotro <nội dung câu hỏi>")
        return

    prompt = question
    if quoted:
        prompt = f"[Tin nhắn được trích dẫn]\n{quoted}\n\n[Câu hỏi]\n{question or 'Hãy phản hồi tin nhắn trên.'}"

    await context.bot.send_chat_action(msg.chat_id, ChatAction.TYPING)

    try:
        resp = await client.messages.create(
            model=MODEL,
            max_tokens=1500,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        answer = "".join(b.text for b in resp.content if b.type == "text").strip()
        if not answer:
            answer = "Mình chưa có câu trả lời cho câu này, bạn thử hỏi lại nhé."
    except Exception:
        log.exception("Lỗi khi gọi AI")
        answer = "Xin lỗi, hiện mình đang gặp lỗi. Bạn thử lại sau nhé."

    # Tag lại người hỏi
    mention = f'<a href="tg://user?id={user.id}">{html.escape(user.full_name)}</a>'
    first = True
    for part in split_text(answer):
        text = (f"{mention}\n" if first else "") + html.escape(part)
        await msg.reply_text(text, parse_mode=ParseMode.HTML)
        first = False
        await asyncio.sleep(0.3)


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    log.info("Bot đang chạy...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
