import os
import sqlite3
import random
import httpx
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "database" / "mythic.db"
CARDS_DIR = BASE_DIR / "assets" / "cards"

load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
MYTHIC_WEBAPP_URL = "https://yoonshweyephoo1552006-bit.github.io/mythic-card-web/"
MYTHIC_API_URL = "https://mythic-card-web-production.up.railway.app"
CARD_SYNC_SECRET = os.getenv("CARD_SYNC_SECRET", "").strip()
OWNER_ID_RAW = os.getenv("OWNER_ID", "").strip()

try:
    OWNER_ID = int(OWNER_ID_RAW) if OWNER_ID_RAW else 0
except ValueError:
    OWNER_ID = 0


RARITIES = {
    "common": "⚪ COMMON",
    "uncommon": "🟢 UNCOMMON",
    "rare": "🔵 RARE",
    "epic": "🟣 EPIC",
    "legendary": "🟠 LEGENDARY",
    "mythic": "🔴 MYTHIC",
}


DROP_INTERVAL_HOURS = 2
DROP_DURATION_MINUTES = 120

RANDOM_DROP_RARITIES = (
    "common",
    "uncommon",
    "rare",
    "epic",
)


def get_random_drop_card():
    with get_db() as db:
        rows = db.execute(
            """
            SELECT id, card_code, name, rarity, image_path
            FROM cards
            WHERE is_active = 1
              AND rarity IN ('common', 'uncommon', 'rare', 'epic')
            """
        ).fetchall()

    if not rows:
        return None

    return random.choice(rows)


def create_drop():
    card = get_random_drop_card()

    if not card:
        return None

    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=DROP_DURATION_MINUTES)

    with get_db() as db:
        # Don't create another active drop for the same card.
        active = db.execute(
            """
            SELECT id FROM drops
            WHERE card_id = ? AND status = 'active'
            LIMIT 1
            """,
            (card["id"],),
        ).fetchone()

        if active:
            return None

        db.execute(
            """
            INSERT INTO drops
                (card_id, started_at, expires_at, status)
            VALUES (?, ?, ?, 'active')
            """,
            (
                card["id"],
                now.isoformat(),
                expires.isoformat(),
            ),
        )

        drop_id = db.execute(
            "SELECT last_insert_rowid() AS id"
        ).fetchone()["id"]

    return {
        "id": drop_id,
        "card_id": card["id"],
        "name": card["name"],
        "rarity": card["rarity"],
        "image_path": card["image_path"],
        "expires_at": expires.isoformat(),
    }



def create_owner_drop(rarity):
    """Create an owner-triggered drop for a specific rarity."""
    if rarity not in ("legendary", "mythic"):
        return None

    with get_db() as db:
        rows = db.execute(
            """
            SELECT id, card_code, name, rarity, image_path
            FROM cards
            WHERE is_active = 1
              AND rarity = ?
            """,
            (rarity,),
        ).fetchall()

    if not rows:
        return None

    card = random.choice(rows)

    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=DROP_DURATION_MINUTES)

    with get_db() as db:
        active = db.execute(
            """
            SELECT id
            FROM drops
            WHERE card_id = ?
              AND status = 'active'
            LIMIT 1
            """,
            (card["id"],),
        ).fetchone()

        if active:
            return None

        db.execute(
            """
            INSERT INTO drops
                (card_id, started_at, expires_at, status)
            VALUES (?, ?, ?, 'active')
            """,
            (
                card["id"],
                now.isoformat(),
                expires.isoformat(),
            ),
        )

        drop_id = db.execute(
            "SELECT last_insert_rowid() AS id"
        ).fetchone()["id"]

    return {
        "id": drop_id,
        "card_id": card["id"],
        "name": card["name"],
        "rarity": card["rarity"],
        "image_path": card["image_path"],
        "expires_at": expires.isoformat(),
    }


def expire_old_drops():
    now = datetime.now(timezone.utc).isoformat()

    with get_db() as db:
        db.execute(
            """
            UPDATE drops
            SET status = 'expired'
            WHERE status = 'active'
              AND expires_at <= ?
            """,
            (now,),
        )


async def send_drop(context: ContextTypes.DEFAULT_TYPE, drop):
    if not drop:
        return False

    rarity_text = RARITIES.get(
        drop["rarity"],
        drop["rarity"].upper(),
    )

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🎯 CATCH CARD",
                    callback_data=f"catch_drop_{drop['id']}",
                )
            ]
        ]
    )

    caption = (
        "🎴 NEW CARD DROP!\\n\\n"
        f"🃏 {drop['name']}\\n"
        f"🏷️ {rarity_text}\\n\\n"
        "⚡ Be quick — catch it before it expires!"
    )

    image_file = BASE_DIR / drop["image_path"]

    with get_db() as db:
        users = db.execute(
            "SELECT telegram_id FROM users ORDER BY id"
        ).fetchall()

    sent = 0

    for row in users:
        try:
            if image_file.exists():
                with image_file.open("rb") as photo:
                    await context.bot.send_photo(
                        chat_id=row["telegram_id"],
                        photo=photo,
                        caption=caption,
                        reply_markup=keyboard,
                    )
            else:
                await context.bot.send_message(
                    chat_id=row["telegram_id"],
                    text=caption,
                    reply_markup=keyboard,
                )
            sent += 1
        except Exception:
            pass

    print(f"🎴 DROP #{drop['id']} SENT | users={sent}")
    return True


async def drop_job(context: ContextTypes.DEFAULT_TYPE):
    expire_old_drops()

    drop = create_drop()

    if not drop:
        return

    await send_drop(context, drop)

    rarity_text = RARITIES.get(
        drop["rarity"],
        drop["rarity"].upper(),
    )

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🎯 CATCH CARD",
                    callback_data=f"catch_drop_{drop['id']}",
                )
            ]
        ]
    )

    caption = (
        "🎴 NEW CARD DROP!\n\n"
        f"🃏 {drop['name']}\n"
        f"🏷️ {rarity_text}\n\n"
        "⚡ Be quick — catch it before it expires!"
    )

    image_file = BASE_DIR / drop["image_path"]

    # Send the drop to all registered users.
    with get_db() as db:
        users = db.execute(
            "SELECT telegram_id FROM users ORDER BY id"
        ).fetchall()

    sent = 0
    failed = 0

    for row in users:
        chat_id = row["telegram_id"]

        try:
            if image_file.exists():
                with image_file.open("rb") as photo:
                    await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=photo,
                        caption=caption,
                        reply_markup=keyboard,
                    )
            else:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=caption,
                    reply_markup=keyboard,
                )

            sent += 1

        except Exception:
            # A blocked/deleted chat must not stop the whole drop.
            failed += 1

    print(
        f"🎴 DROP #{drop['id']} SENT | "
        f"users={sent} failed={failed}"
    )


async def catch_drop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    if not query or not query.from_user:
        return

    await query.answer()

    try:
        drop_id = int(query.data.replace("catch_drop_", "", 1))
    except (TypeError, ValueError):
        await query.answer("❌ Invalid drop.", show_alert=True)
        return

    user = query.from_user
    save_user(user)

    now = datetime.now(timezone.utc).isoformat()

    with get_db() as db:
        drop = db.execute(
            """
            SELECT id, card_id, expires_at, status
            FROM drops
            WHERE id = ?
            """,
            (drop_id,),
        ).fetchone()

        if not drop:
            await query.answer(
                "❌ Drop not found.",
                show_alert=True,
            )
            return

        if drop["status"] != "active":
            await query.answer(
                "❌ This card has already been claimed or expired.",
                show_alert=True,
            )
            return

        if drop["expires_at"] <= now:
            db.execute(
                """
                UPDATE drops
                SET status = 'expired'
                WHERE id = ?
                """,
                (drop_id,),
            )

            await query.answer(
                "⏰ This drop has expired.",
                show_alert=True,
            )
            return

        user_row = db.execute(
            "SELECT id FROM users WHERE telegram_id = ?",
            (user.id,),
        ).fetchone()

        if not user_row:
            return

        db.execute(
            """
            UPDATE drops
            SET status = 'caught',
                winner_user_id = ?
            WHERE id = ?
              AND status = 'active'
            """,
            (user_row["id"], drop_id),
        )

        if db.execute("SELECT changes()").fetchone()[0] != 1:
            await query.answer(
                "❌ Someone caught it first!",
                show_alert=True,
            )
            return

        db.execute(
            """
            INSERT INTO collections(user_id, card_id, quantity)
            VALUES (?, ?, 1)
            ON CONFLICT(user_id, card_id)
            DO UPDATE SET quantity = quantity + 1
            """,
            (user_row["id"], drop["card_id"]),
        )

    await query.edit_message_reply_markup(reply_markup=None)

    await query.message.reply_text(
        f"🎉 {user.first_name} caught the card!\n\n"
        "🃏 Card added to your collection."
    )

def get_db():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def is_owner(user_id: int) -> bool:
    return OWNER_ID != 0 and user_id == OWNER_ID


def get_bot_enabled() -> bool:
    with get_db() as db:
        row = db.execute(
            "SELECT value FROM app_settings WHERE key = 'bot_enabled'"
        ).fetchone()

    return bool(row and row["value"] == "1")


def set_bot_enabled(enabled: bool):
    with get_db() as db:
        db.execute(
            """
            INSERT INTO app_settings(key, value)
            VALUES ('bot_enabled', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            ("1" if enabled else "0",),
        )


def save_user(user):
    with get_db() as db:
        db.execute(
            """
            INSERT INTO users
                (telegram_id, username, first_name, is_owner)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                is_owner = excluded.is_owner
            """,
            (
                user.id,
                user.username,
                user.first_name,
                1 if is_owner(user.id) else 0,
            ),
        )


def owner_keyboard():
    enabled = get_bot_enabled()

    status = "🟢 BOT ON" if enabled else "🔴 BOT OFF"

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    status,
                    callback_data="owner_toggle_bot",
                )
            ],
            [
                InlineKeyboardButton(
                    "🎴 OPEN MYTHIC CARD",
                    web_app=WebAppInfo(url=MYTHIC_WEBAPP_URL),
                )
            ],
            [
                InlineKeyboardButton(
                    "📤 UPLOAD CARD",
                    callback_data="owner_upload_card",
                )
            ],
            [
                InlineKeyboardButton(
                    "🔄 REPLACE CARD",
                    callback_data="owner_replace_card",
                )
            ],
            [
                InlineKeyboardButton(
                    "👑 DROP LEGENDARY",
                    callback_data="owner_drop_legendary",
                ),
                InlineKeyboardButton(
                    "🌌 DROP MYTHIC",
                    callback_data="owner_drop_mythic",
                ),
            ],
            [
                InlineKeyboardButton(
                    "🏟️ START EVENT",
                    callback_data="owner_start_event",
                )
            ],
        ]
    )


def rarity_keyboard():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "⚪ COMMON",
                    callback_data="upload_rarity_common",
                ),
                InlineKeyboardButton(
                    "🟢 UNCOMMON",
                    callback_data="upload_rarity_uncommon",
                ),
            ],
            [
                InlineKeyboardButton(
                    "🔵 RARE",
                    callback_data="upload_rarity_rare",
                ),
                InlineKeyboardButton(
                    "🟣 EPIC",
                    callback_data="upload_rarity_epic",
                ),
            ],
            [
                InlineKeyboardButton(
                    "🟠 LEGENDARY",
                    callback_data="upload_rarity_legendary",
                ),
                InlineKeyboardButton(
                    "🔴 MYTHIC",
                    callback_data="upload_rarity_mythic",
                ),
            ],
            [
                InlineKeyboardButton(
                    "❌ CANCEL",
                    callback_data="upload_cancel",
                )
            ],
        ]
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return

    user = update.effective_user
    save_user(user)

    context.user_data.pop("upload_photo", None)

    if is_owner(user.id):
        await update.message.reply_text(
            "👑 OWNER PANEL\n\n"
            "Control your Mythic Card system here.",
            reply_markup=owner_keyboard(),
        )
        return

    if not get_bot_enabled():
        await update.message.reply_text(
            "🃏 MYTHIC CARD\n\n"
            "🔴 The bot is currently preparing.\n"
            "Please try again later."
        )
        return

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🎴 OPEN MYTHIC CARD",
                    web_app=WebAppInfo(url=MYTHIC_WEBAPP_URL),
                )
            ]
        ]
    )

    await update.message.reply_text(
        "🃏 MYTHIC CARD\n\n"
        "🟢 The bot is online.\n"
        "👇 Tap below to open the game.",
        reply_markup=keyboard,
    )




async def collection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return

    user = update.effective_user

    if not get_bot_enabled() and not is_owner(user.id):
        await update.message.reply_text(
            "🃏 MY COLLECTION\n\n"
            "🔴 Bot is currently offline."
        )
        return

    save_user(user)

    with get_db() as db:
        user_row = db.execute(
            "SELECT id FROM users WHERE telegram_id = ?",
            (user.id,),
        ).fetchone()

        if not user_row:
            await update.message.reply_text(
                "❌ User account was not found."
            )
            return

        rows = db.execute(
            """
            SELECT
                c.card_code,
                c.name,
                c.rarity,
                c.image_path,
                col.quantity
            FROM collections col
            JOIN cards c ON c.id = col.card_id
            WHERE col.user_id = ?
            ORDER BY
                CASE c.rarity
                    WHEN 'mythic' THEN 1
                    WHEN 'legendary' THEN 2
                    WHEN 'epic' THEN 3
                    WHEN 'rare' THEN 4
                    WHEN 'uncommon' THEN 5
                    WHEN 'common' THEN 6
                END,
                c.id
            """,
            (user_row["id"],),
        ).fetchall()

        counts = {}
        for rarity in RARITIES:
            count_row = db.execute(
                """
                SELECT COALESCE(SUM(col.quantity), 0) AS total
                FROM collections col
                JOIN cards c ON c.id = col.card_id
                WHERE col.user_id = ?
                  AND c.rarity = ?
                """,
                (user_row["id"], rarity),
            ).fetchone()

            counts[rarity] = int(count_row["total"])

    total_cards = sum(counts.values())

    summary = (
        "🃏 MY COLLECTION\n\n"
        f"👤 {user.first_name}\n"
        f"📦 Total Cards: {total_cards}\n\n"
        f"⚪ Common: {counts['common']}\n"
        f"🟢 Uncommon: {counts['uncommon']}\n"
        f"🔵 Rare: {counts['rare']}\n"
        f"🟣 Epic: {counts['epic']}\n"
        f"🟠 Legendary: {counts['legendary']}\n"
        f"🔴 Mythic: {counts['mythic']}"
    )

    await update.message.reply_text(summary)

    if not rows:
        await update.message.reply_text(
            "📭 Your collection is empty.\n\n"
            "Catch cards to start your collection!"
        )
        return

    for row in rows:
        image_file = BASE_DIR / row["image_path"]

        if not image_file.exists():
            continue

        rarity_text = RARITIES.get(
            row["rarity"],
            row["rarity"].upper(),
        )

        with image_file.open("rb") as photo:
            await update.message.reply_photo(
                photo=photo,
                caption=(
                    f"🃏 {row['name']}\n"
                    f"🏷️ {rarity_text}\n"
                    f"🔢 Owned: {row['quantity']}"
                ),
            )


async def gallery(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return

    if not get_bot_enabled() and not is_owner(update.effective_user.id):
        await update.message.reply_text(
            "🃏 CARD GALLERY\n\n"
            "🔴 Bot is currently offline."
        )
        return

    with get_db() as db:
        rows = db.execute(
            """
            SELECT card_code, name, rarity, image_path
            FROM cards
            WHERE is_active = 1
            ORDER BY
                CASE rarity
                    WHEN 'mythic' THEN 1
                    WHEN 'legendary' THEN 2
                    WHEN 'epic' THEN 3
                    WHEN 'rare' THEN 4
                    WHEN 'uncommon' THEN 5
                    WHEN 'common' THEN 6
                END,
                id
            """
        ).fetchall()

    if not rows:
        await update.message.reply_text(
            "🃏 CARD GALLERY\n\n"
            "No cards have been added yet."
        )
        return

    await update.message.reply_text(
        f"🃏 CARD GALLERY\n\n"
        f"Total cards: {len(rows)}\n\n"
        "Cards are shown below."
    )

    for row in rows:
        image_file = BASE_DIR / row["image_path"]

        if not image_file.exists():
            await update.message.reply_text(
                f"⚠️ {row['name']}\n"
                f"Image file is missing."
            )
            continue

        rarity_text = RARITIES.get(
            row["rarity"],
            row["rarity"].upper(),
        )

        with image_file.open("rb") as photo:
            await update.message.reply_photo(
                photo=photo,
                caption=f"🃏 {row['name']}",
            )


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user and update.message:
        await update.message.reply_text(
            f"🆔 Your Telegram ID:\n{update.effective_user.id}"
        )


async def owner_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return

    if not is_owner(update.effective_user.id):
        await update.message.reply_text("⛔ Unauthorized.")
        return

    await update.message.reply_text(
        "👑 OWNER PANEL",
        reply_markup=owner_keyboard(),
    )




def replace_card_keyboard():
    with get_db() as db:
        rows = db.execute(
            """
            SELECT id, card_code, name, rarity
            FROM cards
            WHERE is_active = 1
            ORDER BY id
            """
        ).fetchall()

    buttons = []

    for row in rows:
        rarity_text = RARITIES.get(
            row["rarity"],
            row["rarity"].upper(),
        )

        buttons.append(
            [
                InlineKeyboardButton(
                    f"🔄 {row['card_code']} • {rarity_text}",
                    callback_data=f"replace_select_{row['id']}",
                )
            ]
        )

    buttons.append(
        [
            InlineKeyboardButton(
                "❌ CANCEL",
                callback_data="replace_cancel",
            )
        ]
    )

    return InlineKeyboardMarkup(buttons)


async def replace_card_photo_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.effective_user or not update.message:
        return

    user = update.effective_user

    if not is_owner(user.id):
        return

    card_id = context.user_data.get("replace_card_id")

    if not card_id:
        return

    if not update.message.photo:
        return

    photo = update.message.photo[-1]

    try:
        with get_db() as db:
            card = db.execute(
                """
                SELECT
                    id,
                    card_code,
                    name,
                    rarity,
                    image_path
                FROM cards
                WHERE id = ? AND is_active = 1
                LIMIT 1
                """,
                (card_id,),
            ).fetchone()

        if not card:
            context.user_data.pop(
                "replace_card_id",
                None,
            )

            await update.message.reply_text(
                "❌ Card မတွေ့ပါ။",
                reply_markup=owner_keyboard(),
            )
            return

        image_file = BASE_DIR / card["image_path"]

        image_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        # Download Telegram replacement to a temporary file first.
        temp_file = image_file.with_suffix(
            ".replace.tmp.jpg"
        )

        tg_file = await context.bot.get_file(
            photo.file_id
        )

        await tg_file.download_to_drive(
            custom_path=str(temp_file)
        )

        if not temp_file.exists():
            raise RuntimeError(
                "Replacement image was not downloaded."
            )

        # Sync replacement to Railway first.
        await sync_replaced_card_to_web(
            image_file=temp_file,
            card_id=card["id"],
        )

        # Railway succeeded, now update local image.
        temp_file.replace(image_file)

        context.user_data.pop(
            "replace_card_id",
            None,
        )

        await update.message.reply_text(
            "✅ CARD IMAGE REPLACED + WEBAPP SYNCED!\n\n"
            f"🎴 {card['card_code']}\n"
            f"🃏 {card['name']}\n"
            f"🏷️ "
            f"{RARITIES.get(card['rarity'], card['rarity'].upper())}\n\n"
            "📸 Local image replaced.\n"
            "🌐 Railway WebApp image replaced.\n"
            "ℹ️ Card ID / Name / Rarity / Collection data "
            "မပြောင်းပါ။",
            reply_markup=owner_keyboard(),
        )

    except Exception as exc:
        print(
            f"❌ CARD IMAGE REPLACE/SYNC ERROR: "
            f"{type(exc).__name__}: {exc}",
            flush=True,
        )

        # Clean temporary file if it exists.
        try:
            if "temp_file" in locals() and temp_file.exists():
                temp_file.unlink()
        except Exception:
            pass

        await update.message.reply_text(
            "❌ Image replace / WebApp sync failed.\n\n"
            f"⚠️ {type(exc).__name__}: {exc}\n\n"
            "ℹ️ Existing local image was kept unchanged.",
            reply_markup=owner_keyboard(),
        )



async def owner_upload_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.effective_user or not update.message:
        return

    if not is_owner(update.effective_user.id):
        await update.message.reply_text("⛔ Unauthorized.")
        return

    context.user_data.pop("upload_rarity", None)
    context.user_data.pop("upload_count", None)

    await update.message.reply_text(
        "📤 CARD UPLOAD\n\n"
        "ဘယ် Rarity ထဲကို ပုံတွေထည့်မလဲ?",
        reply_markup=rarity_keyboard(),
    )


def get_setting_int(key: str, default: int = 0) -> int:
    with get_db() as db:
        row = db.execute(
            "SELECT value FROM app_settings WHERE key = ?",
            (key,),
        ).fetchone()

    try:
        return int(row["value"]) if row else default
    except (TypeError, ValueError):
        return default


def get_card_count(rarity=None) -> int:
    with get_db() as db:
        if rarity:
            row = db.execute(
                "SELECT COUNT(*) AS total FROM cards WHERE rarity = ?",
                (rarity,),
            ).fetchone()
        else:
            row = db.execute(
                "SELECT COUNT(*) AS total FROM cards"
            ).fetchone()

    return int(row["total"])


def check_card_upload_limit(rarity: str):
    total_limit = get_setting_int("total_card_limit", 1500)
    rarity_limit = get_setting_int(
        f"{rarity}_card_limit",
        0,
    )

    total = get_card_count()
    rarity_count = get_card_count(rarity)

    if total >= total_limit:
        return False, (
            f"❌ TOTAL CARD LIMIT REACHED\n\n"
            f"📦 {total}/{total_limit}\n"
            "Card အသစ်ထပ်ထည့်လို့ မရတော့ပါ။"
        )

    if rarity_limit > 0 and rarity_count >= rarity_limit:
        return False, (
            f"❌ {RARITIES[rarity]} LIMIT REACHED\n\n"
            f"📦 {rarity_count}/{rarity_limit}\n"
            "ဒီ Rarity အတွက် သတ်မှတ်ထားတဲ့အရေအတွက် ပြည့်နေပါပြီ။"
        )

    return True, ""


async def photo_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.effective_user or not update.message:
        return

    user = update.effective_user

    if not is_owner(user.id):
        return

    if context.user_data.get("replace_card_id"):
        await replace_card_photo_handler(update, context)
        return

    rarity = context.user_data.get("upload_rarity")

    if not rarity:
        return

    allowed, limit_message = check_card_upload_limit(rarity)
    if not allowed:
        await update.message.reply_text(limit_message)
        return

    if not update.message.photo:
        return

    allowed, reason = check_card_upload_limit(rarity)

    if not allowed:
        await update.message.reply_text(
            reason,
            reply_markup=owner_keyboard(),
        )
        return

    photo = update.message.photo[-1]

    pending = context.user_data.setdefault("pending_cards", [])

    total_limit = get_setting_int("total_card_limit", 1500)
    rarity_limit = get_setting_int(
        f"{rarity}_card_limit",
        0,
    )

    remaining_total = total_limit - get_card_count()
    remaining_rarity = (
        rarity_limit - get_card_count(rarity)
        if rarity_limit > 0
        else remaining_total
    )

    remaining = min(
        remaining_total,
        remaining_rarity,
    )

    if len(pending) >= remaining:
        await update.message.reply_text(
            f"❌ {RARITIES[rarity]} upload limit reached.\n\n"
            f"📦 Total remaining: {remaining_total}\n"
            f"🏷️ Rarity remaining: {remaining_rarity}",
            reply_markup=upload_done_keyboard(),
        )
        return

    pending.append(photo.file_id)

    count = len(pending)

    await update.message.reply_text(
        f"🖼️ Image received: #{count}\n\n"
        f"🏷️ Rarity: {RARITIES[rarity]}\n\n"
        "နောက်ထပ်ပုံတွေ ဆက်ပို့လို့ရပါတယ်။\n"
        "ပြီးရင် ✅ DONE UPLOAD ကိုနှိပ်ပါ။",
        reply_markup=upload_done_keyboard(),
    )


def upload_done_keyboard():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ DONE UPLOAD",
                    callback_data="upload_done",
                )
            ],
            [
                InlineKeyboardButton(
                    "❌ CANCEL",
                    callback_data="upload_cancel",
                )
            ],
        ]
    )


async def sync_card_to_web(
    *,
    image_file,
    card_code,
    name,
    rarity,
):
    """
    Upload one locally saved card image to Railway.
    """
    if not CARD_SYNC_SECRET:
        raise RuntimeError(
            "CARD_SYNC_SECRET is not configured"
        )

    image_bytes = Path(image_file).read_bytes()

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{MYTHIC_API_URL}/api/admin/card/upload",
            params={
                "card_code": card_code,
                "name": name,
                "rarity": rarity,
            },
            content=image_bytes,
            headers={
                "Content-Type": "image/jpeg",
                "X-Card-Sync-Secret": CARD_SYNC_SECRET,
            },
        )

        if response.status_code >= 400:
            raise RuntimeError(
                f"Railway sync failed "
                f"({response.status_code}): "
                f"{response.text[:500]}"
            )

        data = response.json()

        if not data.get("ok"):
            raise RuntimeError(
                data.get("error", "Railway sync failed")
            )

        return data


async def sync_replaced_card_to_web(
    *,
    image_file,
    card_id,
):
    """
    Replace an existing Railway card image.
    """
    if not CARD_SYNC_SECRET:
        raise RuntimeError(
            "CARD_SYNC_SECRET is not configured"
        )

    image_bytes = Path(image_file).read_bytes()

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{MYTHIC_API_URL}/api/admin/card/replace",
            params={
                "card_id": int(card_id),
            },
            content=image_bytes,
            headers={
                "Content-Type": "image/jpeg",
                "X-Card-Sync-Secret": CARD_SYNC_SECRET,
            },
        )

        if response.status_code >= 400:
            raise RuntimeError(
                f"Railway replace failed "
                f"({response.status_code}): "
                f"{response.text[:500]}"
            )

        data = response.json()

        if not data.get("ok"):
            raise RuntimeError(
                data.get("error", "Railway replace failed")
            )

        return data


async def save_pending_cards(
    query,
    context: ContextTypes.DEFAULT_TYPE,
):
    rarity = context.user_data.get("upload_rarity")
    pending = context.user_data.get("pending_cards", [])

    if not rarity or not pending:
        await query.edit_message_text(
            "❌ သိမ်းရန် pending card မရှိပါ။",
            reply_markup=owner_keyboard(),
        )
        return

    total_limit = get_setting_int("total_card_limit", 1500)
    rarity_limit = get_setting_int(
        f"{rarity}_card_limit",
        0,
    )

    current_total = get_card_count()
    current_rarity = get_card_count(rarity)

    remaining_total = total_limit - current_total
    remaining_rarity = (
        rarity_limit - current_rarity
        if rarity_limit > 0
        else remaining_total
    )

    allowed_count = min(
        remaining_total,
        remaining_rarity,
    )

    if allowed_count <= 0:
        await query.edit_message_text(
            f"❌ {RARITIES[rarity]} upload limit reached.\n\n"
            f"📦 Total: {current_total}/{total_limit}\n"
            f"🏷️ Rarity: "
            f"{current_rarity}/"
            f"{rarity_limit if rarity_limit > 0 else '∞'}",
            reply_markup=owner_keyboard(),
        )
        return

    if len(pending) > allowed_count:
        await query.edit_message_text(
            f"❌ Too many cards in this batch.\n\n"
            f"📦 You can save only "
            f"{allowed_count} more card(s).\n"
            f"🖼️ Pending: {len(pending)}",
            reply_markup=owner_keyboard(),
        )
        return

    CARDS_DIR.joinpath(rarity).mkdir(
        parents=True,
        exist_ok=True,
    )

    saved = 0
    failed = 0
    web_synced = 0

    for file_id in pending:
        card_id = None
        image_path = None

        try:
            with get_db() as db:
                next_row = db.execute(
                    """
                    SELECT COALESCE(MAX(id), 0) + 1 AS next_id
                    FROM cards
                    """
                ).fetchone()

                card_number = int(next_row["next_id"])
                card_code = f"CARD-{card_number:04d}"
                card_name = f"Card #{card_number:04d}"

                image_path = (
                    CARDS_DIR
                    / rarity
                    / f"{card_code}.jpg"
                )

                db.execute(
                    """
                    INSERT INTO cards
                    (card_code, name, rarity, image_path)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        card_code,
                        card_name,
                        rarity,
                        str(
                            image_path.relative_to(BASE_DIR)
                        ),
                    ),
                )

                card_id = db.execute(
                    "SELECT last_insert_rowid() AS id"
                ).fetchone()["id"]

            tg_file = await context.bot.get_file(file_id)

            await tg_file.download_to_drive(
                custom_path=str(image_path)
            )

            if not image_path.exists():
                raise RuntimeError(
                    "Telegram image was not saved locally."
                )

            # Sync the exact same image to Railway.
            await sync_card_to_web(
                image_file=image_path,
                card_code=card_code,
                name=card_name,
                rarity=rarity,
            )

            saved += 1
            web_synced += 1

        except Exception as exc:
            failed += 1

            print(
                f"❌ CARD UPLOAD/SYNC ERROR: "
                f"{type(exc).__name__}: {exc}",
                flush=True,
            )

            # Roll back the local DB row if the Railway sync failed.
            if card_id is not None:
                try:
                    with get_db() as db:
                        db.execute(
                            "DELETE FROM cards WHERE id = ?",
                            (card_id,),
                        )
                except Exception:
                    pass

            if image_path is not None:
                try:
                    if image_path.exists():
                        image_path.unlink()
                except Exception:
                    pass

    context.user_data.pop("upload_rarity", None)
    context.user_data.pop("pending_cards", None)

    await query.edit_message_text(
        "✅ BATCH UPLOAD COMPLETE\n\n"
        f"🏷️ {RARITIES[rarity]}\n"
        f"🖼️ Saved: {saved}\n"
        f"🌐 WebApp Synced: {web_synced}\n"
        f"❌ Failed: {failed}\n\n"
        "☁️ Railway WebApp sync completed.",
        reply_markup=owner_keyboard(),
    )


async def owner_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if not query or not query.from_user:
        return

    if not is_owner(query.from_user.id):
        await query.answer(
            "⛔ Unauthorized.",
            show_alert=True,
        )
        return

    await query.answer()

    if query.data == "owner_toggle_bot":
        new_state = not get_bot_enabled()
        set_bot_enabled(new_state)

        await query.edit_message_text(
            "👑 OWNER PANEL\n\n"
            f"Bot status: "
            f"{'🟢 ON' if new_state else '🔴 OFF'}",
            reply_markup=owner_keyboard(),
        )
        return

    if query.data == "owner_upload_card":
        context.user_data.pop("upload_rarity", None)
        context.user_data.pop("pending_cards", None)

        await query.edit_message_text(
            "📤 CARD UPLOAD\n\n"
            "Rarity ရွေးပါ။\n"
            "ရွေးပြီးရင် အဲ့ Rarity ရဲ့ ပုံတွေကို "
            "အများကြီး ဆက်တိုက်ပို့နိုင်ပါတယ်။",
            reply_markup=rarity_keyboard(),
        )
        return

    if query.data == "owner_replace_card":
        context.user_data.pop("upload_rarity", None)
        context.user_data.pop("pending_cards", None)
        context.user_data.pop("replace_card_id", None)

        with get_db() as db:
            total = db.execute(
                """
                SELECT COUNT(*) AS total
                FROM cards
                WHERE is_active = 1
                """
            ).fetchone()["total"]

        if not total:
            await query.edit_message_text(
                "❌ Active card မရှိသေးပါ။",
                reply_markup=owner_keyboard(),
            )
            return

        await query.edit_message_text(
            "🔄 REPLACE CARD IMAGE\n\n"
            f"🎴 Active Cards: {total}\n\n"
            "ပုံအသစ်ပြောင်းချင်တဲ့ Card ကိုရွေးပါ။\n"
            "Card ID / Name / Rarity / Collection data "
            "မပြောင်းပါဘူး။",
            reply_markup=replace_card_keyboard(),
        )
        return

    if query.data.startswith("replace_select_"):
        try:
            card_id = int(
                query.data.replace(
                    "replace_select_",
                    "",
                    1,
                )
            )
        except ValueError:
            await query.edit_message_text(
                "❌ Invalid card.",
                reply_markup=owner_keyboard(),
            )
            return

        with get_db() as db:
            card = db.execute(
                """
                SELECT id, card_code, name, rarity
                FROM cards
                WHERE id = ? AND is_active = 1
                LIMIT 1
                """,
                (card_id,),
            ).fetchone()

        if not card:
            await query.edit_message_text(
                "❌ Card မတွေ့ပါ။",
                reply_markup=replace_card_keyboard(),
            )
            return

        context.user_data.pop("upload_rarity", None)
        context.user_data.pop("pending_cards", None)
        context.user_data["replace_card_id"] = card_id

        await query.edit_message_text(
            "🔄 READY TO REPLACE\n\n"
            f"🎴 {card['card_code']}\n"
            f"🃏 {card['name']}\n"
            f"🏷️ {RARITIES.get(card['rarity'], card['rarity'].upper())}\n\n"
            "📸 အခု ပုံအသစ် ၁ ပုံပို့ပါ။\n\n"
            "⚠️ ဒီ Card ရဲ့ image ပဲ အစားထိုးမယ်။\n"
            "Card data တွေ မပြောင်းပါဘူး။"
        )
        return

    if query.data == "replace_cancel":
        context.user_data.pop("replace_card_id", None)

        await query.edit_message_text(
            "❌ Card image replacement cancelled.",
            reply_markup=owner_keyboard(),
        )
        return

    if query.data.startswith("upload_rarity_"):
        rarity = query.data.replace(
            "upload_rarity_",
            "",
            1,
        )

        if rarity not in RARITIES:
            await query.edit_message_text(
                "❌ Invalid rarity.",
                reply_markup=owner_keyboard(),
            )
            return

        context.user_data["upload_rarity"] = rarity
        context.user_data["pending_cards"] = []

        await query.edit_message_text(
            "🖼️ READY FOR BATCH UPLOAD\n\n"
            f"🏷️ Selected: {RARITIES[rarity]}\n\n"
            "အခု ဒီ Rarity အတွက် ပုံတွေကို "
            "အများကြီး ဆက်ပို့ပါ။\n\n"
            "ပြီးသွားရင် ✅ DONE UPLOAD ကိုနှိပ်ပါ။",
            reply_markup=upload_done_keyboard(),
        )
        return

    if query.data == "upload_done":
        await save_pending_cards(query, context)
        return

    if query.data == "upload_cancel":
        context.user_data.pop("upload_rarity", None)
        context.user_data.pop("pending_cards", None)

        await query.edit_message_text(
            "❌ Card upload cancelled.",
            reply_markup=owner_keyboard(),
        )
        return

    if query.data in ("owner_drop_legendary", "owner_drop_mythic"):
        rarity = (
            "legendary"
            if query.data == "owner_drop_legendary"
            else "mythic"
        )

        await query.answer("⏳ Creating Web drop...")

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(
                    f"{MYTHIC_API_URL}/api/admin/drop",
                    json={
                        "telegram_id": update.effective_user.id,
                        "rarity": rarity,
                    },
                )

            data = response.json()

            if not data.get("ok"):
                error = data.get("error", "Unknown error")

                if response.status_code == 409:
                    await query.message.reply_text(
                        f"⚠️ {rarity.upper()} DROP NOT CREATED\n\n"
                        "🎴 An active drop already exists for this card.\n"
                        "🌐 Check the Web App for the current drop."
                    )
                else:
                    await query.message.reply_text(
                        f"❌ {rarity.upper()} DROP FAILED\\n\\n"
                        f"Reason: {error}"
                    )
                return

            drop = data.get("drop") or {}

            await query.message.reply_text(
                f"✅ {rarity.upper()} DROP CREATED!\n\n"
                f"🎴 {drop.get('name', 'Unknown Card')}\n"
                f"🏷️ {rarity.upper()}\n"
                f"🌐 Card is now live in the Web App.\n"
                f"🎯 Players can catch it from the Web App."
            )

        except Exception as exc:
            print(
                f"❌ WEB DROP API ERROR: {type(exc).__name__}: {exc}",
                flush=True,
            )
            await query.message.reply_text(
                f"❌ {rarity.upper()} DROP FAILED\n\n"
                f"⚠️ {type(exc).__name__}: {exc}"
            )

        return

    if query.data == "owner_start_event":
        await query.answer(
            "Event system will be connected next.",
            show_alert=True,
        )
        return


def main():
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN is empty. Add your Telegram Bot Token to .env"
        )

    if OWNER_ID == 0:
        raise RuntimeError(
            "OWNER_ID is empty or invalid. Add your Telegram ID to .env"
        )

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .pool_timeout(30)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("myid", myid))
    application.add_handler(CommandHandler("gallery", gallery))
    application.add_handler(CommandHandler("collection", collection))
    application.add_handler(CommandHandler("owner", owner_panel))
    application.add_handler(
        CommandHandler("uploadcard", owner_upload_command)
    )

    application.add_handler(
        MessageHandler(filters.PHOTO, photo_handler)
    )

    application.add_handler(
        CallbackQueryHandler(
            owner_callback,
            pattern=r"^(owner_|upload_|replace_)",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            catch_drop,
            pattern=r"^catch_drop_",
        )
    )

    # Automatic local drops are disabled.
    # Drops are now created by the Web backend through the owner panel.

    print("🤖 MYTHIC CARD BOT STARTING...")
    print(f"👑 OWNER ID: {OWNER_ID}")
    print(f"🔘 BOT ENABLED: {get_bot_enabled()}")

    application.run_polling()


if __name__ == "__main__":
    main()
