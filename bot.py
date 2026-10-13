import asyncio
import html
import logging
import os
import random
import re

from openai import AsyncOpenAI
from telegram import Update
from telegram.constants import ChatAction, ChatType, ParseMode
from telegram.error import BadRequest
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("hotro-bot")

# ====== CẤU HÌNH ======
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"].strip()
AI_API_KEY = os.getenv(
    "AI_API_KEY", "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"
).strip()
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://api.groq.com/openai/v1").strip()
MODEL = os.getenv("AI_MODEL", "llama-3.3-70b-versatile").strip()
TRIGGER = os.getenv("TRIGGER", "@hotrohit88bot")
SHOW_ERROR = os.getenv("SHOW_ERROR", "1") == "1"  # tạm bật để xem lỗi ngay trong chat

SYSTEM_PROMPT = (
    "Bạn là trợ lý AI thân thiện trong nhóm Telegram, tên là Hỗ Trợ. "
    "Trả lời bằng ngôn ngữ của người hỏi (mặc định tiếng Việt), ngắn gọn, tự nhiên, dễ hiểu. "
    "Bạn có thể trò chuyện về mọi chủ đề: tình cảm, cuộc sống, học tập, công việc, giải trí, "
    "kiến thức về cờ bạc/xác suất, v.v. Hãy trung thực và đưa ra thông tin hữu ích, "
    "kể cả cảnh báo rủi ro khi thật sự cần thiết. "
    "Hãy chèn emoji phù hợp (😃 🥰 💡 💰 🎲 🎯 🍀 🌟 😏 🤩 🔥...) vào câu trả lời cho sinh động. "
    "Không dùng Markdown, chỉ dùng văn bản thuần."
)

# ====== EMOJI PREMIUM ======
RAW_EMOJI = """
🗑 5445267414562389170
⌛ 5386367538735104399
🚨 5395695537687123235
✏️ 5395444784611480792
✉️ 5253742260054409879
➕ 5397916757333654639
📍 5391032818111363540
🔄 5375338737028841420
🔝 5415655814079723871
🔗 5271604874419647061
🖥 5282843764451195532
🛡 5251203410396458957
➡️ 5416117059207572332
💸 5231005931550030290
📌 5397782960512444700
🚗 6280407793631498213
😃 6111737246732262016
🇻🇳 6190651897792174993
🔋 5307905813451397794
💳 5445353829304387411
⛏ 5197371802136892976
📥 5443127283898405358
💰 5278467510604160626
🛡 5197288647275071607
🏦 5332455502917949981
↗️ 5429651785352501917
🛒 5312361253610475399
⚖️ 5400250414929041085
💻 5193177581888755275
🖼 5262517101578443800
💡 5262844652964303985
💰 5287231198098117669
🎯 5256131095094652290
📞 5285238101344544669
🎲 5280816565657300091
🔓 5291873529464122510
🥰 5197387964098813812
☺️ 5238015713314086319
🖐 5237759703198474072
💩 5235622845299565321
🚘 5240037474679398914
❌ 5238037944064811339
😳 5238083517962793068
😏 5237903859480796749
🏃‍♀️ 5237981615568723131
💳 5240066289614987080
😱 5235640209852343235
🤩 5195357093107868151
😕 5197226061011623665
🍌 5237784970491074950
🤓 5240209101572545926
⌨️ 5237843923212181104
😡 5240408207666455054
🔫 5235762367312173706
💳 5237971457971067970
😨 5242500342070909767
😭 5460630100263312018
🤪 5240076365608264313
🥰 5240076833759699366
👅 5239944638961294456
😭 5460741258311900209
💸 5240290577102152084
😧 5237721297600912488
🍔 5239948040575393823
🐶 5242395424609803673
🤫 6226686020570584326
🤘 6163685838250054493
🌟 6195233300752111114
🔝 6163696502653850661
🍀 6161347086823461532
💥 6161101981629814014
🎖 6165926565638051547
🤬 6168156972219635148
🥰 6190600074716779111
🥰 6167691994765202199
🥰 6167904514041976028
🥰 6170039056953513698
🥰 6170126953459228118
🍑 6165529117954413678
🤓 6167810935294530083
🕺 6186015776948885249
🌷 6197378228894568973
🐉 6188171511229060434
👋 6190629722876023613
😍 6192639363843626187
😇 6195191910152279859
🚊 6208671312823456804
🤨 6208304964998010180
🥰 6208631494181655806
"""

VS16 = "\ufe0f"
EMOJI_IDS: dict[str, list[str]] = {}
for line in RAW_EMOJI.strip().splitlines():
    emo, eid = line.split()
    EMOJI_IDS.setdefault(emo.replace(VS16, ""), []).append(eid)

# Regex khớp mọi emoji có ID premium (chuỗi dài khớp trước)
_keys = sorted(EMOJI_IDS, key=len, reverse=True)
EMOJI_RE = re.compile(
    "|".join("".join(re.escape(c) + VS16 + "?" for c in k) for k in _keys)
)
TG_EMOJI_RE = re.compile(r'<tg-emoji emoji-id="\d+">(.*?)</tg-emoji>', re.S)


def cemoji(emo: str, shown: str | None = None) -> str:
    """Trả về thẻ custom emoji (random 1 ID nếu emoji có nhiều ID)."""
    eid = random.choice(EMOJI_IDS[emo.replace(VS16, "")])
    return f'<tg-emoji emoji-id="{eid}">{shown or emo}</tg-emoji>'


def premiumize(text: str) -> str:
    """Thay emoji thường trong text (đã escape HTML) bằng emoji premium."""
    return EMOJI_RE.sub(lambda m: cemoji(m.group(0), m.group(0)), text)


# ====== TIỆN ÍCH ======
client = AsyncOpenAI(api_key=AI_API_KEY, base_url=AI_BASE_URL)
log.info("Dùng AI: %s (model=%s)", AI_BASE_URL, MODEL)
trigger_re = re.compile(re.escape(TRIGGER), re.IGNORECASE)


def split_text(text: str, limit: int = 3000):
    """Chia nhỏ tin nhắn dài (Telegram giới hạn 4096 ký tự)."""
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = limit
        yield text[:cut]
        text = text[cut:].lstrip("\n")
    if text:
        yield text


async def safe_reply(msg, text_html: str):
    """Gửi kèm emoji premium; nếu Telegram từ chối thì gửi lại bằng emoji thường."""
    try:
        await msg.reply_text(text_html, parse_mode=ParseMode.HTML)
    except BadRequest as e:
        log.warning("Gửi custom emoji lỗi (%s), chuyển sang emoji thường", e)
        plain = TG_EMOJI_RE.sub(r"\1", text_html)
        await msg.reply_text(plain, parse_mode=ParseMode.HTML)


async def ask_ai(prompt: str) -> str:
    resp = await client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        max_tokens=1500,
    )
    return (resp.choices[0].message.content or "").strip()


async def post_init(app: Application):
    """Tự kiểm tra AI ngay khi bot khởi động, in kết quả ra log."""
    try:
        out = await ask_ai("Chào một câu ngắn.")
        log.info("✅ AI OK (model=%s): %s", MODEL, out[:80])
    except Exception as e:
        log.error(
            "❌ AI LỖI (model=%s): %s: %s", MODEL, type(e).__name__, e, exc_info=True
        )


# ====== XỬ LÝ TIN NHẮN ======
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user
    if not msg or not msg.text or not user:
        return

    # Chat riêng (private): trả lời mọi tin nhắn, không cần tag.
    # Nhóm/supergroup: chỉ trả lời khi có tag bot.
    is_private = update.effective_chat.type == ChatType.PRIVATE
    if not is_private and not trigger_re.search(msg.text):
        return

    question = trigger_re.sub("", msg.text).strip()

    quoted = ""
    if msg.reply_to_message and msg.reply_to_message.text:
        quoted = msg.reply_to_message.text.strip()

    if not question and not quoted:
        await safe_reply(
            msg, f"{cemoji('💡')} Bạn cần hỏi gì? Gõ: {html.escape(TRIGGER)} &lt;nội dung câu hỏi&gt;"
        )
        return

    prompt = question
    if quoted:
        prompt = (
            f"[Tin nhắn được trích dẫn]\n{quoted}\n\n"
            f"[Câu hỏi]\n{question or 'Hãy phản hồi tin nhắn trên.'}"
        )

    await context.bot.send_chat_action(msg.chat_id, ChatAction.TYPING)

    try:
        answer = await ask_ai(prompt)
        if not answer:
            answer = "Mình chưa có câu trả lời cho câu này, bạn thử hỏi lại nhé. 😕"
    except Exception as e:
        log.error("Lỗi khi gọi AI: %s: %s", type(e).__name__, e, exc_info=True)
        answer = "Xin lỗi, hiện mình đang gặp lỗi. Bạn thử lại sau nhé. 😭"
        if SHOW_ERROR:
            # Chế độ debug: hiện chi tiết lỗi ngay trong chat (tắt bằng SHOW_ERROR=0)
            answer += f"\n\n[DEBUG] {type(e).__name__}: {str(e)[:500]}"

    mention = f'<a href="tg://user?id={user.id}">{html.escape(user.full_name)}</a>'
    header = f"{cemoji('🌟')} {mention} {cemoji('🥰')}\n\n"

    first = True
    for part in split_text(answer):
        body = premiumize(html.escape(part))
        await safe_reply(msg, (header if first else "") + body)
        first = False
        await asyncio.sleep(0.3)


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    log.info("Bot đang chạy, từ khoá: %s", TRIGGER)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
