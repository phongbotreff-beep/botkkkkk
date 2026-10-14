import asyncio
import base64
import html
import logging
import os
import random
import re
import time

from openai import AsyncOpenAI, NotFoundError
from telegram import Update
from telegram.constants import ChatAction, ChatType, ParseMode
from telegram.error import BadRequest
from telegram.ext import Application, ContextTypes, MessageHandler, filters

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("hotro-bot")

# ====== CẤU HÌNH (đặt trong tab Variables của Railway) ======
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
AI_API_KEY = os.getenv("AI_API_KEY", "").strip()
if not TELEGRAM_TOKEN:
    raise SystemExit("Thiếu biến TELEGRAM_TOKEN (Railway > Variables)")
if not AI_API_KEY:
    raise SystemExit("Thiếu biến AI_API_KEY (Railway > Variables)")

AI_BASE_URL = os.getenv("AI_BASE_URL", "https://api.groq.com/openai/v1").strip()
MODEL = os.getenv("AI_MODEL", "llama-3.3-70b-versatile").strip()
# Model đọc được ảnh (chỉ dùng khi người dùng gửi ảnh)
VISION_MODEL = os.getenv("VISION_MODEL", "qwen/qwen3.8-27b").strip()
# Nếu model trên không dùng được (404), bot tự thử lần lượt các model này
VISION_FALLBACKS = [
    "qwen/qwen3.8-27b",
    "qwen/qwen3.6-27b",
    "meta-llama/llama-4-scout-17b-16e-instruct",
]
TRIGGER = os.getenv("TRIGGER", "@hotrohit88bot")
SHOW_ERROR = os.getenv("SHOW_ERROR", "1") == "1"  # tạm bật để xem lỗi ngay trong chat

PHOTO_TTL = 600  # giây: ảnh chờ người dùng mô tả vấn đề tối đa 10 phút
MAX_IMG_BYTES = 3_000_000  # giới hạn dung lượng ảnh gửi cho AI

# ====== KIẾN THỨC HIT88 ======
HIT88_INFO = """
THÔNG TIN HIT88 (dùng để trả lời khi người dùng hỏi):

THÔNG TIN CHUNG
- Min nạp tiền: 10k. Min rút tiền: 50k.
- Từ 9h30 rút tiền siêu tốc chỉ 30 giây.
- Người tạo bot và quản trị viên: @dgfrutil. Cần hỗ trợ nhắn @dgfrutil.
- Bot chơi game: @gamehit88_bot (gõ /game để mở danh sách game, /start để đăng ký lại).
- Nhận code miễn phí: Bot phát code: https://t.me/hit88phatcode_bot (bấm nút trong bot). Kênh phát code: https://t.me/sancodehit88

QUY ĐỊNH NHẬP CODE HIT88
1. Giới hạn nhập code:
- Mỗi tài khoản được nhập tối đa 5 mã code từ bot NPH/ngày.
- Không giới hạn việc nhập code từ các sự kiện khác, theo điều kiện riêng của từng chương trình.

2. Quy định rút tiền:
- Tài khoản chưa có lịch sử nạp trên 50K: cần nạp tối thiểu 50.000đ và hoàn thành 2 vòng cược (x2) trước khi tạo lệnh rút.
- Tài khoản đã có lịch sử nạp trên 50K: có thể tạo lệnh rút ngay mà không cần nạp thêm tiền, theo điều kiện rút tiền của hệ thống.

3. Lưu ý quan trọng:
- Cấm dồn code (dồn từ 2 code trở lên): sẽ bị khấu trừ toàn bộ số dư.
- Nhập vượt quá giới hạn 5 mã code từ bot NPH/ngày: tài khoản có thể bị khấu trừ toàn bộ số dư theo quy định.
- Nghiêm cấm tạo tài khoản phụ (clone) nhằm trục lợi hoặc lạm dụng chương trình code. Phát hiện vi phạm sẽ bị khóa tài khoản vĩnh viễn.
- Đề nghị toàn thể anh em đọc kỹ và tuân thủ quy định để tránh ảnh hưởng đến quyền lợi tài khoản.

ĐẶT CƯỢC (mỗi phiên có mã phiên, VD: phiên XX #96160)
- Min cược: 1.000 | Max cược: 1.000.000.
- Cách chơi: [Cửa cược] [số tiền]. Tài: T | Xỉu: X | Chẵn: C | Lẻ: L.
- Ẩn danh thường: TT/XX/CC/LL, VD: TT 50000, XX 50000.
- T/X/C/L trả x2.3 (thua tổng khi 3 XX 9/10/11/12 điểm).
- Tất tay: VD T MAX hoặc T ALL.
- D1 [mặt] x5: đoán viên đầu, VD: D1 4 20k.
- D2 [2 mặt] x10: đoán viên 1 và 2 đúng thứ tự, VD: D2 46 20k.
- D3 [tổng]: 9/10/11/12 x7; 8/13 x9; 7/14 x12; 6/15 x15; 5/16 x18; 4/17 x25; 3/18 x30. VD: D3 13 20000 hoặc D3 13 max.
- Xiên TC/TL/XC/XL trả x3, VD: TC 50000, XC 50000.
- Ví dụ đặt cược: T 50000, X 50000, XX MAX, TT MAX, TC max, T 5000, XXT 10000, BR 10000, BD 10000, D6 20000, SB11 5000, TL 10000, XL 10000.
- Mẹo: nhập theo mẫu [NỘI_DUNG] [SỐ_TIỀN]. Nếu lệnh sai, bot sẽ trả lời gợi ý đúng mẫu.

CÁC LỆNH CỦA BOT
- Tài khoản: /start [ref], /game, /ref, /slot, /lschoi (lịch sử chơi), /lsnap (lịch sử nạp), /lsrut (lịch sử rút), /nap [số tiền], /rutbank [số tiền], /caidatbank [STK] [MãBank] [Tên chủ TK], /code [CODE], /chuyen [idnhan] [sotien].
- Bot tương tác: /help, /checktt, /top.

NẠP TIỀN
- Nạp tối thiểu: 10.000đ. Nạp tối đa: 100.000.000đ.
- Nạp qua chuyển khoản ngân hàng. Gõ /nap số_tiền (VD: /nap 100000 hoặc /nap 100k) hoặc bấm nút mệnh giá trong bot để lấy thông tin nạp nhanh.
- Lưu ý: chuyển đúng SỐ TIỀN và NỘI DUNG được cung cấp. Mỗi lần nạp cần lấy thông tin MỚI, không dùng thông tin cũ cho giao dịch sau.

RÚT TIỀN
- Cài đặt ngân hàng trước: /caidatbank [STK] [MãBank] [Tên chủ TK]. VD: /caidatbank 0271722 MB Nguyen Van A (tên chủ tài khoản không viết dấu). Muốn đổi STK bấm /caidatbank hoặc liên hệ Admin.
- Rút tiền về tài khoản đã cài: /rutbank [số tiền], VD: /rutbank 50000.
- Rút tối thiểu: 50.000đ. Rút tối đa: 100.000.000đ. Phí rút 1% (theo mọi giao dịch).
- Điều kiện rút: phải đủ điều kiện cược. Bot hiển thị "Cược còn thiếu" và "Hiện đã cược"; còn thiếu cược thì cần cược thêm đủ số còn thiếu mới được rút.
- Danh sách Mã Bank: ICB - VietinBank, VCB - Vietcombank, BIDV - BIDV, VBA - Agribank, OCB - OCB, MB - MBBank, TCB - Techcombank, ACB - ACB, VPB - VPBank, TPB - TPBank, STB - Sacombank, HDB - HDBank, VIB - VIB, SCB - SCB, SHB - SHB, EIB - Eximbank, MSB - MSB, BAB - Bac A Bank, NCB - NCB, BVB - BaoVietBank, ABB - ABBank, CAKE - Cake, CBB - CBBank, DBS - DBS, GPB - GPBank, KLB - KienlongBank, NAB - Nam A Bank, PGB - PGBank, SGB - SaigonBank, VAB - VietABank, CIMB - CIMB, HSBC - HSBC, IBK - Industrial Bank of Korea, IVB - Indovina Bank, UOB - UOB, BIDC - BIDC, BNP - BNP Paribas, HLBVN - Hong Leong Bank, KBANK - KBank, WOORI - Woori Bank.

GIFTCODE
- Mua giftcode: /muagift [số lượng] [giá trị mỗi code], VD: /muagift 5 3000. Phí mua giftcode là 5%.
- Nhập giftcode: /code [mã giftcode], VD: /code CODE123.

ĐIỂM VIP
- Với mỗi 200K tiền cược, bạn được tặng thêm 1 điểm cấp VIP. Điểm dùng để xét tăng cấp VIP và đổi thưởng.
- Cấp VIP và biểu tượng: Vip 0 🥇 (Đồng), Vip 1 🥈 (Bạc), Vip 2 🥉 (Vàng), Vip 3 ⭐️ (Bạch Kim), Vip 4 💎 (Kim Cương), Vip 5 🏆 (Cao Thủ), Vip 6 👑 (Chiến Tướng).
- Điểm yêu cầu để đạt cấp: Vip 1: 10 điểm; Vip 2: 50; Vip 3: 100; Vip 4: 500; Vip 5: 1000; Vip 6: 5000.
- Tỉ lệ quy đổi điểm: Vip 1: 1 điểm = 100đ; Vip 2: 1 điểm = 200đ; Vip 3: 1 điểm = 300đ; Vip 4: 1 điểm = 400đ; Vip 5: 1 điểm = 500đ; Vip 6: 1 điểm = 600đ.
- Cách đổi điểm VIP: /doidiemvip [số điểm], VD: /doidiemvip 100.

BÁO DANH 7 NGÀY
- Điều kiện: ảnh đại diện phải đúng ảnh quy định trong bot (bấm giữ ảnh để lưu). Tên phải có HIT88. Tiểu sử dán link mời của chính bạn (dạng t.me/gamehit88_bot?start=ID_của_bạn). Không để chế độ ẩn danh @username.
- Báo danh mỗi ngày, đủ 7 ngày liên tiếp nhận 38.888. Sai tên, sai link, sai ảnh, hoặc thiếu một ngày thì số ngày về 0.

RƯƠNG ĐỆ TỬ 28–58K (mời bạn bè)
- Mỗi người có link mời riêng dạng t.me/gamehit88_bot?start=ID_của_bạn (lấy bằng /ref).
- Điều kiện mỗi ref hợp lệ: nạp thành công tối thiểu 50.000đ và cược hợp lệ tối thiểu 199.000đ.
- Cứ đủ 5 ref hợp lệ nhận 1 giftcode ngẫu nhiên từ 28.000đ đến 58.000đ.
"""

VISION_RULES = """

KHI NGƯỜI DÙNG GỬI ẢNH:
- Người dùng gửi ảnh chụp màn hình hoặc ảnh giao dịch kèm mô tả vấn đề. Hãy đọc kỹ ảnh (số tiền, nội dung chuyển khoản, trạng thái, thông báo lỗi, số dư, cược còn thiếu...) và nói ngắn gọn ảnh cho thấy gì.
- Đối chiếu với THÔNG TIN HIT88 để tìm nguyên nhân và hướng dẫn từng bước cách xử lý.
- Nếu ảnh mờ hoặc thiếu thông tin, nói rõ phần nào chưa thấy và nhờ gửi lại ảnh rõ hơn.
- Nếu không tự giải quyết được (nạp chưa lên, rút chưa về, tài khoản bị khóa...), hướng dẫn nhắn @dgfrutil kèm ảnh và mã giao dịch để admin xử lý. Không hứa hẹn hoàn tiền hay duyệt lệnh thay admin.
- Không bao giờ yêu cầu mật khẩu, mã OTP hay thông tin bảo mật. Nếu thấy chúng trong ảnh, nhắc bạn ấy không chia sẻ.
- Không bịa thông tin không có trong ảnh hoặc trong THÔNG TIN HIT88.
"""

SYSTEM_PROMPT = (
    "Bạn là trợ lý AI thân thiện trong nhóm Telegram HIT88, tên là Hỗ Trợ. "
    "Trả lời bằng ngôn ngữ của người hỏi (mặc định tiếng Việt), ngắn gọn, tự nhiên, dễ hiểu. "
    "Khi người dùng hỏi về HIT88 (nạp, rút, nhập code, cách cược, lệnh bot, VIP, ref, báo danh, giftcode, quy định, hỗ trợ...), "
    "hãy trả lời CHÍNH XÁC theo phần THÔNG TIN HIT88 bên dưới, không tự bịa thêm điều kiện hay con số. "
    "Ví dụ: hỏi min nạp bao nhiêu thì trả lời: 'Min nạp tiền HIT88 là 10k bạn nhé'. "
    "Nếu câu hỏi về HIT88 mà không có trong thông tin, hãy bảo bạn ấy nhắn @dgfrutil để được hỗ trợ. "
    "Với các chủ đề khác (tình cảm, cuộc sống, học tập, công việc, giải trí, kiến thức xác suất...), "
    "bạn vẫn trò chuyện bình thường, trung thực, và cảnh báo rủi ro khi thật sự cần thiết. "
    "Hãy chèn emoji phù hợp (😃 🥰 💡 💰 🎲 🎯 🍀 🌟 😏 🤩 🔥...) vào câu trả lời cho sinh động. "
    "Không dùng Markdown, chỉ dùng văn bản thuần.\n"
    + HIT88_INFO
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
log.info("Dùng AI: %s (model=%s, vision=%s)", AI_BASE_URL, MODEL, VISION_MODEL)
trigger_re = re.compile(re.escape(TRIGGER), re.IGNORECASE)

# Ảnh đang chờ người dùng mô tả vấn đề: {(chat_id, user_id): {...}}
PENDING: dict[tuple[int, int], dict] = {}


def clean_pending():
    now = time.time()
    for k in [k for k, v in PENDING.items() if now - v["ts"] > PHOTO_TTL]:
        PENDING.pop(k, None)


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


async def reply_answer(msg, user, answer: str):
    """Gửi câu trả lời kèm tên người hỏi + emoji premium, tự chia nhỏ nếu dài."""
    mention = f'<a href="tg://user?id={user.id}">{html.escape(user.full_name)}</a>'
    header = f"{cemoji('🌟')} {mention} {cemoji('🥰')}\n\n"
    first = True
    for part in split_text(answer):
        body = premiumize(html.escape(part))
        await safe_reply(msg, (header if first else "") + body)
        first = False
        await asyncio.sleep(0.3)


def error_answer(e: Exception) -> str:
    log.error("Lỗi khi gọi AI: %s: %s", type(e).__name__, e, exc_info=True)
    answer = "Xin lỗi, hiện mình đang gặp lỗi. Bạn thử lại sau nhé. 😭"
    if SHOW_ERROR:
        # Chế độ debug: hiện chi tiết lỗi ngay trong chat (tắt bằng SHOW_ERROR=0)
        answer += f"\n\n[DEBUG] {type(e).__name__}: {str(e)[:500]}"
    return answer


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


async def _vision_call(model: str, problem: str, image_b64: str, mime: str) -> str:
    text = (
        f"Vấn đề người dùng gặp phải: {problem}\n\n"
        "Hãy xem kỹ ảnh đính kèm, nói ngắn gọn ảnh cho thấy gì, "
        "rồi hướng dẫn cách giải quyết vấn đề."
    )
    resp = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT + VISION_RULES},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": text},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{image_b64}"},
                    },
                ],
            },
        ],
        max_tokens=3000,
    )
    out = resp.choices[0].message.content or ""
    # Một số model có suy luận: bỏ phần <think>...</think> nếu có
    out = re.sub(r"<think>.*?</think>", "", out, flags=re.S)
    return out.strip()


async def ask_ai_vision(problem: str, image_b64: str, mime: str) -> str:
    """Gửi ảnh + mô tả vấn đề cho model đọc ảnh; model nào 404 thì thử model kế tiếp."""
    global VISION_MODEL
    candidates = [VISION_MODEL] + [m for m in VISION_FALLBACKS if m != VISION_MODEL]
    last_err: Exception | None = None
    for model in candidates:
        try:
            out = await _vision_call(model, problem, image_b64, mime)
            if model != VISION_MODEL:
                log.warning("Model ảnh %s lỗi, chuyển sang %s", VISION_MODEL, model)
                VISION_MODEL = model
            return out
        except NotFoundError as e:
            log.warning("Model ảnh %s không dùng được: %s", model, e)
            last_err = e
    raise last_err or RuntimeError("Không có model đọc ảnh nào dùng được")


PREFERRED_MODELS = [
    "llama-3.3-70b-versatile",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "llama-3.1-8b-instant",
]
SKIP_WORDS = ("whisper", "tts", "guard", "orpheus", "embed", "safeguard")
VISION_HINTS = ("qwen3.8", "qwen3.6", "qwen3-vl", "llama-4", "scout", "maverick", "vision")


async def pick_model():
    """Lấy danh sách model key này dùng được; nếu model hiện tại không có thì tự chọn model khác."""
    global MODEL, VISION_MODEL
    try:
        page = await client.models.list()
        ids = [m.id for m in page.data]
        log.info("Model khả dụng: %s", ", ".join(ids))

        if MODEL not in ids:
            chosen = next((m for m in PREFERRED_MODELS if m in ids), None)
            if not chosen:
                chosen = next(
                    (m for m in ids if not any(w in m.lower() for w in SKIP_WORDS)),
                    None,
                )
            if chosen:
                log.warning("Model %s không dùng được, chuyển sang %s", MODEL, chosen)
                MODEL = chosen

        if VISION_MODEL not in ids:
            vchosen = next(
                (
                    m
                    for h in VISION_HINTS
                    for m in ids
                    if h in m.lower() and not any(w in m.lower() for w in SKIP_WORDS)
                ),
                None,
            )
            if vchosen:
                log.warning(
                    "Model ảnh %s không dùng được, chuyển sang %s", VISION_MODEL, vchosen
                )
                VISION_MODEL = vchosen
            else:
                log.warning(
                    "Không tìm thấy model đọc ảnh, hãy đặt biến VISION_MODEL cho đúng"
                )
    except Exception as e:
        log.error("Không lấy được danh sách model: %s: %s", type(e).__name__, e)


async def post_init(app: Application):
    """Tự kiểm tra AI ngay khi bot khởi động, in kết quả ra log."""
    await pick_model()
    try:
        out = await ask_ai("Chào một câu ngắn.")
        log.info("✅ AI OK (model=%s): %s", MODEL, out[:80])
    except Exception as e:
        log.error(
            "❌ AI LỖI (model=%s): %s: %s", MODEL, type(e).__name__, e, exc_info=True
        )


# ====== XỬ LÝ ẢNH ======
async def solve_image(msg, user, context, problem: str, image_b64: str, mime: str):
    await context.bot.send_chat_action(msg.chat_id, ChatAction.TYPING)
    try:
        answer = await ask_ai_vision(problem, image_b64, mime)
        if not answer:
            answer = "Mình chưa đọc được ảnh này, bạn gửi lại ảnh rõ hơn giúp mình nhé. 😕"
    except Exception as e:
        answer = error_answer(e)
    await reply_answer(msg, user, answer)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return

    # Chat riêng: nhận mọi ảnh. Nhóm: chỉ nhận ảnh có caption tag bot.
    is_private = update.effective_chat.type == ChatType.PRIVATE
    caption = msg.caption or ""
    if not is_private and not trigger_re.search(caption):
        return

    tg_file = None
    mime = "image/jpeg"
    if msg.photo:
        # msg.photo xếp từ nhỏ đến lớn: lấy ảnh lớn nhất không vượt giới hạn
        chosen = None
        for p in reversed(msg.photo):
            if p.file_size is None or p.file_size <= MAX_IMG_BYTES:
                chosen = p
                break
        chosen = chosen or msg.photo[0]
        tg_file = await context.bot.get_file(chosen.file_id)
    elif msg.document and (msg.document.mime_type or "").startswith("image/"):
        if msg.document.file_size and msg.document.file_size > MAX_IMG_BYTES:
            await safe_reply(msg, "Ảnh quá nặng, bạn gửi ảnh nhẹ hơn (dưới 3MB) nhé. 😕")
            return
        mime = msg.document.mime_type
        tg_file = await context.bot.get_file(msg.document.file_id)
    else:
        return

    try:
        data = bytes(await tg_file.download_as_bytearray())
    except Exception as e:
        log.error("Tải ảnh lỗi: %s: %s", type(e).__name__, e)
        await safe_reply(msg, "Mình tải ảnh không được, bạn gửi lại giúp mình nhé. 😭")
        return
    if len(data) > MAX_IMG_BYTES:
        await safe_reply(msg, "Ảnh quá nặng, bạn gửi ảnh nhẹ hơn (dưới 3MB) nhé. 😕")
        return

    image_b64 = base64.b64encode(data).decode()

    # Nếu người dùng đã ghi vấn đề ngay trong caption thì xử lý luôn
    problem = trigger_re.sub("", caption).strip()
    if problem:
        await solve_image(msg, user, context, problem, image_b64, mime)
        return

    clean_pending()
    PENDING[(msg.chat_id, user.id)] = {
        "b64": image_b64,
        "mime": mime,
        "ts": time.time(),
    }
    ask = f"{cemoji('💡')} Mình đã nhận được ảnh rồi! Bạn đang gặp vấn đề gì? Hãy nói rõ để mình xem giúp nhé."
    if not is_private:
        ask += "\n(Bạn hãy trả lời trực tiếp tin nhắn này của mình)"
    await safe_reply(msg, ask)


# ====== XỬ LÝ TIN NHẮN CHỮ ======
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user
    if not msg or not msg.text or not user:
        return

    # Chat riêng (private): trả lời mọi tin nhắn, không cần tag.
    # Nhóm/supergroup: chỉ trả lời khi có tag bot.
    is_private = update.effective_chat.type == ChatType.PRIVATE

    # Đang chờ người dùng mô tả vấn đề của ảnh vừa gửi?
    clean_pending()
    key = (msg.chat_id, user.id)
    pending = PENDING.get(key)
    if pending:
        replying_to_bot = bool(
            msg.reply_to_message
            and msg.reply_to_message.from_user
            and msg.reply_to_message.from_user.id == context.bot.id
        )
        if is_private or replying_to_bot or trigger_re.search(msg.text):
            PENDING.pop(key, None)
            problem = trigger_re.sub("", msg.text).strip() or "(người dùng không mô tả thêm)"
            await solve_image(msg, user, context, problem, pending["b64"], pending["mime"])
            return

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
        answer = error_answer(e)

    await reply_answer(msg, user, answer)


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    log.info("Bot đang chạy, từ khoá: %s", TRIGGER)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

