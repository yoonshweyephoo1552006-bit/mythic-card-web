import json
import sqlite3
import os
import hmac
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qsl

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "database" / "mythic.db"
WEB_DIR = BASE_DIR / "app" / "web"

try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except Exception:
    pass

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OWNER_ID = int(os.getenv("OWNER_ID", "0") or "0")
CARD_SYNC_SECRET = os.getenv("CARD_SYNC_SECRET", "").strip()



def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(DB_PATH) as db:
        db.execute("PRAGMA foreign_keys = ON")

        schema_path = BASE_DIR / "database" / "schema.sql"
        if schema_path.exists():
            db.executescript(
                schema_path.read_text(encoding="utf-8")
            )

        # Seed the built-in card catalog.
        # INSERT OR IGNORE keeps existing production card data safe.
        seed_cards = [
            ("CARD-0001", "Card #0001", "legendary",
             "assets/cards/legendary/CARD-0001.jpg"),
            ("CARD-0002", "Card #0002", "common",
             "assets/cards/common/CARD-0002.jpg"),
            ("CARD-0004", "Card #0004", "mythic",
             "assets/cards/mythic/CARD-0004.jpg"),
            ("CARD-0005", "Card #0005", "mythic",
             "assets/cards/mythic/CARD-0005.jpg"),
            ("CARD-0006", "Card #0006", "mythic",
             "assets/cards/mythic/CARD-0006.jpg"),
            ("CARD-0007", "Card #0007", "mythic",
             "assets/cards/mythic/CARD-0007.jpg"),
            ("CARD-0008", "Card #0008", "mythic",
             "assets/cards/mythic/CARD-0008.jpg"),
            ("CARD-0009", "Card #0009", "mythic",
             "assets/cards/mythic/CARD-0009.jpg"),
            ("CARD-0010", "Card #0010", "mythic",
             "assets/cards/mythic/CARD-0010.jpg"),
            ("CARD-0011", "Card #0011", "mythic",
             "assets/cards/mythic/CARD-0011.jpg"),
            ("CARD-0012", "Card #0012", "mythic",
             "assets/cards/mythic/CARD-0012.jpg"),
            ("CARD-0013", "Card #0013", "mythic",
             "assets/cards/mythic/CARD-0013.jpg"),
        ]

        for card_code, name, rarity, image_path in seed_cards:
            card_image = BASE_DIR / image_path
            if card_image.exists():
                db.execute("""
                    INSERT OR IGNORE INTO cards
                    (card_code, name, rarity, image_path, is_active)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    card_code,
                    name,
                    rarity,
                    image_path,
                    1
                ))

        db.commit()


def get_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    schema_path = BASE_DIR / "database" / "schema.sql"
    if schema_path.exists():
        db.executescript(schema_path.read_text(encoding="utf-8"))
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db



# ============================================================
# DROP SYSTEM
# ============================================================

DROP_DEFAULT_INTERVAL_MINUTES = 10
DROP_DEFAULT_DURATION_MINUTES = 2
EPIC_DEFAULT_MONTHLY_LIMIT = 4


def get_setting(db, key, default):
    row = db.execute(
        "SELECT value FROM app_settings WHERE key = ?",
        (key,)
    ).fetchone()

    if not row:
        return default

    value = str(row["value"]).strip().strip("'\"")

    try:
        return int(value)
    except ValueError:
        return default


def set_default_setting(db, key, value):
    db.execute(
        """
        INSERT OR IGNORE INTO app_settings(key, value)
        VALUES (?, ?)
        """,
        (key, str(value))
    )


def init_drop_settings():
    with get_db() as db:
        set_default_setting(
            db,
            "drop_interval_minutes",
            DROP_DEFAULT_INTERVAL_MINUTES
        )

        set_default_setting(
            db,
            "drop_duration_minutes",
            DROP_DEFAULT_DURATION_MINUTES
        )

        set_default_setting(
            db,
            "epic_monthly_limit",
            EPIC_DEFAULT_MONTHLY_LIMIT
        )

        db.commit()


def create_automatic_normal_drop():
    """
    Create one automatic Normal drop.

    Eligible rarities:
        common / uncommon / rare

    Epic cards are handled by the separate
    monthly Epic system.

    Duplicate ownership is allowed by the collections table.
    Legendary and Mythic are excluded because they are owner-drop only.
    """

    now = datetime.now(timezone.utc)

    with get_db() as db:
        # Expire old drops first.
        db.execute(
            """
            UPDATE drops
            SET status = 'expired'
            WHERE status = 'active'
              AND expires_at <= ?
            """,
            (now.isoformat(),)
        )

        # Never create a second active drop.
        active = db.execute(
            """
            SELECT id
            FROM drops
            WHERE status = 'active'
            LIMIT 1
            """
        ).fetchone()

        if active:
            return None

        duration_minutes = get_setting(
            db,
            "drop_duration_minutes",
            DROP_DEFAULT_DURATION_MINUTES
        )

        card = db.execute(
            """
            SELECT id, card_code, name, rarity, image_path
            FROM cards
            WHERE is_active = 1
              AND rarity IN (
                  'common',
                  'uncommon',
                  'rare'
              )
            ORDER BY RANDOM()
            LIMIT 1
            """
        ).fetchone()

        if not card:
            return None

        expires = now + timedelta(
            minutes=max(1, duration_minutes)
        )

        cursor = db.execute(
            """
            INSERT INTO drops(
                card_id,
                started_at,
                expires_at,
                status
            )
            VALUES (?, ?, ?, 'active')
            """,
            (
                card["id"],
                now.isoformat(),
                expires.isoformat()
            )
        )

        db.commit()

        return {
            "id": cursor.lastrowid,
            "card_id": card["id"],
            "card_code": card["card_code"],
            "name": card["name"],
            "rarity": card["rarity"],
            "image_path": card["image_path"],
            "started_at": now.isoformat(),
            "expires_at": expires.isoformat(),
        }



def get_text_setting(db, key, default=""):
    row = db.execute(
        "SELECT value FROM app_settings WHERE key = ?",
        (key,)
    ).fetchone()

    if not row:
        return default

    return str(row["value"]).strip().strip("'\"")


def set_setting_value(db, key, value):
    db.execute(
        """
        INSERT INTO app_settings(key, value)
        VALUES (?, ?)
        ON CONFLICT(key)
        DO UPDATE SET value = excluded.value
        """,
        (key, str(value))
    )


def prepare_epic_month(db, now):
    """
    Reset Epic monthly state when a new calendar month starts.
    """

    month_key = now.strftime("%Y-%m")
    saved_month = get_text_setting(
        db,
        "epic_month",
        ""
    )

    if saved_month != month_key:
        set_setting_value(
            db,
            "epic_month",
            month_key
        )

        set_setting_value(
            db,
            "monthly_epic_claimed",
            0
        )

        set_setting_value(
            db,
            "epic_current_card_id",
            0
        )

    return month_key


def create_automatic_epic_drop():
    """
    Create an automatic Epic drop when the current month's
    successful Epic catches are below the configured limit.

    If an Epic drop expires without being caught, the same
    Epic card is retained and can be dropped again.
    """

    now = datetime.now(timezone.utc)

    with get_db() as db:
        prepare_epic_month(db, now)

        monthly_limit = get_setting(
            db,
            "epic_monthly_limit",
            EPIC_DEFAULT_MONTHLY_LIMIT
        )

        claimed = get_setting(
            db,
            "monthly_epic_claimed",
            0
        )

        if claimed >= monthly_limit:
            return None

        # Never allow two active drops at once.
        active = db.execute(
            """
            SELECT id
            FROM drops
            WHERE status = 'active'
            LIMIT 1
            """
        ).fetchone()

        if active:
            return None

        # Expired drops are no longer active.
        db.execute(
            """
            UPDATE drops
            SET status = 'expired'
            WHERE status = 'active'
              AND expires_at <= ?
            """,
            (now.isoformat(),)
        )

        current_card_id = get_setting(
            db,
            "epic_current_card_id",
            0
        )

        card = None

        # Retry the same Epic card if the previous Epic
        # drop was not caught.
        if current_card_id > 0:
            card = db.execute(
                """
                SELECT id, card_code, name, rarity, image_path
                FROM cards
                WHERE id = ?
                  AND is_active = 1
                  AND rarity = 'epic'
                LIMIT 1
                """,
                (current_card_id,)
            ).fetchone()

        # No current Epic card means this is a new Epic slot.
        if not card:
            card = db.execute(
                """
                SELECT id, card_code, name, rarity, image_path
                FROM cards
                WHERE is_active = 1
                  AND rarity = 'epic'
                ORDER BY RANDOM()
                LIMIT 1
                """
            ).fetchone()

            if not card:
                return None

            set_setting_value(
                db,
                "epic_current_card_id",
                card["id"]
            )

        duration_minutes = get_setting(
            db,
            "drop_duration_minutes",
            DROP_DEFAULT_DURATION_MINUTES
        )

        expires = now + timedelta(
            minutes=max(1, duration_minutes)
        )

        cursor = db.execute(
            """
            INSERT INTO drops(
                card_id,
                started_at,
                expires_at,
                status
            )
            VALUES (?, ?, ?, 'active')
            """,
            (
                card["id"],
                now.isoformat(),
                expires.isoformat()
            )
        )

        db.commit()

        return {
            "id": cursor.lastrowid,
            "card_id": card["id"],
            "card_code": card["card_code"],
            "name": card["name"],
            "rarity": card["rarity"],
            "image_path": card["image_path"],
            "started_at": now.isoformat(),
            "expires_at": expires.isoformat(),
        }



def run_drop_scheduler():
    """
    Background drop scheduler.

    Priority:
        1. Epic monthly system
        2. Normal common/uncommon/rare system

    Only one active drop is allowed at a time.
    The scheduler checks once per configured Normal interval.
    """

    import threading
    import time

    def worker():
        print("[DROP] Automatic drop scheduler started")

        while True:
            try:
                with get_db() as db:
                    interval_minutes = get_setting(
                        db,
                        "drop_interval_minutes",
                        DROP_DEFAULT_INTERVAL_MINUTES
                    )

                interval_seconds = max(
                    60,
                    interval_minutes * 60
                )

                time.sleep(interval_seconds)

                # Epic gets priority so the monthly Epic system
                # cannot be starved by Normal drops.
                epic_drop = create_automatic_epic_drop()

                if epic_drop:
                    print(
                        "[DROP] Epic drop created: "
                        f'{epic_drop["card_code"]}'
                    )
                    continue

                # If no Epic drop is needed/possible, create
                # the regular Normal drop.
                normal_drop = create_automatic_normal_drop()

                if normal_drop:
                    print(
                        "[DROP] Normal drop created: "
                        f'{normal_drop["card_code"]} '
                        f'({normal_drop["rarity"]})'
                    )
                else:
                    print(
                        "[DROP] Normal drop skipped "
                        "(active drop or no eligible card)"
                    )

            except Exception as exc:
                print(
                    f"[DROP] Scheduler error: {exc}"
                )

                # Prevent a broken scheduler from spinning
                # continuously and consuming CPU.
                time.sleep(60)

    thread = threading.Thread(
        target=worker,
        name="mythic-drop-scheduler",
        daemon=True
    )
    thread.start()


def json_response(handler, data, status=200):
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")

    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)


class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        print("[WEB]", fmt % args)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Telegram-Init-Data, X-Card-Sync-Secret")
        self.end_headers()

    def seed_test_card(self):
        with get_db() as db:
            db.execute("""
                INSERT OR IGNORE INTO cards
                (card_code, name, rarity, image_path, is_active)
                VALUES (?, ?, ?, ?, ?)
            """, (
                "CARD-0001",
                "Card #0001",
                "legendary",
                "assets/cards/legendary/CARD-0001.jpg",
                1
            ))
            db.commit()

        return json_response(self, {
            "ok": True,
            "message": "Test card seeded"
        })

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/api/health":
            return json_response(self, {
                "ok": True,
                "service": "MYTHIC CARD WEB API"
            })

        if path == "/api/seed-test-card":
            return self.seed_test_card()

        if path == "/api/cards":
            return self.cards()

        if path == "/api/drop":
            return self.active_drop()

        if path == "/api/stats":
            return self.stats()

        if path == "/api/me":
            return self.me()

        if path == "/api/collection":
            return self.collection()

        if path == "/api/events":
            return self.events()

        if path == "/api/battles":
            return self.battles()

        if path == "/api/trades":
            return self.trades()

        if path == "/api/premium":
            return self.premium()

        if path == "/api/admin/premium":
            return self.admin_premium()

        if path == "/api/admin/premium/receipt":
            return self.admin_premium_receipt()

        if path == "/" or path == "/index.html":
            return self.static_file("index.html")

        if path == "/app.js":
            return self.static_file("app.js")

        if path == "/style.css":
            return self.static_file("style.css")

        if path.startswith("/assets/"):
            return self.asset_file(path)

        json_response(self, {
            "ok": False,
            "error": "Not found"
        }, 404)

    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/api/catch":
            return self.catch_card()

        if path == "/api/admin/drop":
            return self.admin_drop()

        if path == "/api/admin/card/upload":
            return self.admin_card_upload()

        if path == "/api/admin/card/replace":
            return self.admin_card_replace()

        if path == "/api/premium/request":
            return self.premium_request()

        if path == "/api/admin/premium/approve":
            return self.admin_premium_approve()

        if path == "/api/admin/premium/reject":
            return self.admin_premium_reject()

        if path == "/api/trade/create":
            return self.trade_create()

        if path == "/api/trade/accept":
            return self.trade_accept()

        if path == "/api/trade/reject":
            return self.trade_reject()

        if path == "/api/trade/cancel":
            return self.trade_cancel()

        return json_response(self, {
            "ok": False,
            "error": "Not found"
        }, 404)



    def _card_sync_authorized(self):
        """
        Authenticate Bot -> Railway card synchronization.
        Uses a private CARD_SYNC_SECRET instead of Telegram WebApp initData.
        """
        if not CARD_SYNC_SECRET:
            return False

        received = self.headers.get("X-Card-Sync-Secret", "").strip()

        return bool(
            received
            and hmac.compare_digest(received, CARD_SYNC_SECRET)
        )


    def _read_request_body(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except (TypeError, ValueError):
            length = 0

        if length <= 0:
            return b""

        # Safety limit: 15 MB per card image.
        if length > 15 * 1024 * 1024:
            return None

        return self.rfile.read(length)


    def _valid_card_rarity(self, rarity):
        return rarity in {
            "common",
            "uncommon",
            "rare",
            "epic",
            "legendary",
            "mythic",
        }


    def _safe_card_code(self, card_code):
        if not card_code:
            return False

        allowed = set(
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            "abcdefghijklmnopqrstuvwxyz"
            "0123456789-_"
        )

        return (
            len(card_code) <= 64
            and all(ch in allowed for ch in card_code)
        )


    def admin_card_upload(self):
        if not self._card_sync_authorized():
            return json_response(self, {
                "ok": False,
                "error": "Card sync authorization failed"
            }, 403)

        try:
            query = dict(parse_qsl(
                urlparse(self.path).query,
                keep_blank_values=True
            ))

            card_code = query.get("card_code", "").strip()
            name = query.get("name", "").strip()
            rarity = query.get("rarity", "").strip().lower()

            if not self._safe_card_code(card_code):
                return json_response(self, {
                    "ok": False,
                    "error": "Invalid card_code"
                }, 400)

            if not self._valid_card_rarity(rarity):
                return json_response(self, {
                    "ok": False,
                    "error": "Invalid rarity"
                }, 400)

            if not name:
                name = card_code

            body = self._read_request_body()

            if body is None:
                return json_response(self, {
                    "ok": False,
                    "error": "Image too large"
                }, 413)

            if not body:
                return json_response(self, {
                    "ok": False,
                    "error": "Image body is empty"
                }, 400)

            cards_dir = BASE_DIR / "assets" / "cards" / rarity
            cards_dir.mkdir(parents=True, exist_ok=True)

            image_path = cards_dir / f"{card_code}.jpg"
            relative_path = str(
                image_path.relative_to(BASE_DIR)
            )

            image_path.write_bytes(body)

            with get_db() as db:
                existing = db.execute(
                    """
                    SELECT id
                    FROM cards
                    WHERE card_code = ?
                    LIMIT 1
                    """,
                    (card_code,)
                ).fetchone()

                if existing:
                    db.execute(
                        """
                        UPDATE cards
                        SET name = ?,
                            rarity = ?,
                            image_path = ?,
                            is_active = 1
                        WHERE id = ?
                        """,
                        (
                            name,
                            rarity,
                            relative_path,
                            existing["id"],
                        )
                    )
                    card_id = existing["id"]
                else:
                    cur = db.execute(
                        """
                        INSERT INTO cards
                        (card_code, name, rarity, image_path, is_active)
                        VALUES (?, ?, ?, ?, 1)
                        """,
                        (
                            card_code,
                            name,
                            rarity,
                            relative_path,
                        )
                    )
                    card_id = cur.lastrowid

                db.commit()

            return json_response(self, {
                "ok": True,
                "action": "upload",
                "card": {
                    "id": card_id,
                    "card_code": card_code,
                    "name": name,
                    "rarity": rarity,
                    "image_path": relative_path,
                }
            }, 201)

        except Exception as exc:
            print("[CARD SYNC UPLOAD ERROR]", repr(exc), flush=True)

            return json_response(self, {
                "ok": False,
                "error": str(exc)
            }, 500)


    def admin_card_replace(self):
        if not self._card_sync_authorized():
            return json_response(self, {
                "ok": False,
                "error": "Card sync authorization failed"
            }, 403)

        try:
            query = dict(parse_qsl(
                urlparse(self.path).query,
                keep_blank_values=True
            ))

            card_id = int(query.get("card_id", "0"))

            if card_id <= 0:
                return json_response(self, {
                    "ok": False,
                    "error": "Invalid card_id"
                }, 400)

            body = self._read_request_body()

            if body is None:
                return json_response(self, {
                    "ok": False,
                    "error": "Image too large"
                }, 413)

            if not body:
                return json_response(self, {
                    "ok": False,
                    "error": "Image body is empty"
                }, 400)

            with get_db() as db:
                card = db.execute(
                    """
                    SELECT id, card_code, name, rarity, image_path
                    FROM cards
                    WHERE id = ? AND is_active = 1
                    LIMIT 1
                    """,
                    (card_id,)
                ).fetchone()

                if not card:
                    return json_response(self, {
                        "ok": False,
                        "error": "Card not found"
                    }, 404)

                image_path = (
                    BASE_DIR / card["image_path"]
                ).resolve()

                assets_root = (
                    BASE_DIR / "assets"
                ).resolve()

                if not str(image_path).startswith(
                    str(assets_root) + "/"
                ):
                    return json_response(self, {
                        "ok": False,
                        "error": "Invalid image path"
                    }, 400)

                image_path.parent.mkdir(
                    parents=True,
                    exist_ok=True
                )

                image_path.write_bytes(body)

            return json_response(self, {
                "ok": True,
                "action": "replace",
                "card": {
                    "id": card["id"],
                    "card_code": card["card_code"],
                    "name": card["name"],
                    "rarity": card["rarity"],
                    "image_path": card["image_path"],
                }
            })

        except Exception as exc:
            print("[CARD SYNC REPLACE ERROR]", repr(exc), flush=True)

            return json_response(self, {
                "ok": False,
                "error": str(exc)
            }, 500)


    def _admin_authorized(self):
        """
        Require a valid Telegram Web App session and the configured owner.
        """
        user, error = self._get_authenticated_user()

        if error:
            return None, error

        telegram_id = int(user["telegram_id"])

        if telegram_id != OWNER_ID:
            return None, "Owner authorization required"

        return user, None


    def admin_premium(self):
        try:
            user, error = self._admin_authorized()

            if error:
                return json_response(self, {
                    "ok": False,
                    "error": error
                }, 403)

            with get_db() as db:
                rows = db.execute("""
                    SELECT
                        pr.id,
                        pr.user_id,
                        u.telegram_id,
                        u.username,
                        u.first_name,
                        pr.amount_mmk,
                        pr.requested_days,
                        pr.payment_method,
                        pr.receipt_path,
                        pr.receipt_note,
                        pr.admin_note,
                        pr.status,
                        pr.created_at,
                        pr.processed_at
                    FROM premium_requests pr
                    JOIN users u ON u.id = pr.user_id
                    ORDER BY
                        CASE WHEN pr.status = 'pending'
                             THEN 0 ELSE 1 END,
                        pr.id DESC
                    LIMIT 100
                """).fetchall()

            return json_response(self, {
                "ok": True,
                "requests": [dict(row) for row in rows]
            })

        except Exception as e:
            return json_response(self, {
                "ok": False,
                "error": str(e)
            }, 500)


    def admin_premium_receipt(self):
        try:
            user, error = self._admin_authorized()

            if error:
                return json_response(self, {
                    "ok": False,
                    "error": error
                }, 403)

            query = parse_qsl(
                urlparse(self.path).query,
                keep_blank_values=True
            )
            params = dict(query)

            request_id = int(params.get("request_id", 0))

            if request_id <= 0:
                return json_response(self, {
                    "ok": False,
                    "error": "Invalid request_id"
                }, 400)

            with get_db() as db:
                row = db.execute("""
                    SELECT receipt_path
                    FROM premium_requests
                    WHERE id = ?
                """, (request_id,)).fetchone()

            if not row or not row["receipt_path"]:
                return json_response(self, {
                    "ok": False,
                    "error": "Receipt not found"
                }, 404)

            receipt_path = Path(row["receipt_path"]).resolve()
            upload_root = (BASE_DIR / "uploads" / "premium").resolve()

            try:
                receipt_path.relative_to(upload_root)
            except ValueError:
                return json_response(self, {
                    "ok": False,
                    "error": "Invalid receipt path"
                }, 400)

            if not receipt_path.is_file():
                return json_response(self, {
                    "ok": False,
                    "error": "Receipt file not found"
                }, 404)

            data = receipt_path.read_bytes()

            suffix = receipt_path.suffix.lower()

            content_types = {
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".webp": "image/webp"
            }

            content_type = content_types.get(
                suffix,
                "application/octet-stream"
            )

            self.send_response(200)
            self.send_header(
                "Content-Type",
                content_type
            )
            self.send_header(
                "Content-Length",
                str(len(data))
            )
            self.send_header(
                "Access-Control-Allow-Origin",
                "*"
            )
            self.send_header(
                "Cache-Control",
                "no-store"
            )
            self.end_headers()

            self.wfile.write(data)

        except (ValueError, TypeError):
            return json_response(self, {
                "ok": False,
                "error": "Invalid request_id"
            }, 400)

        except Exception as e:
            return json_response(self, {
                "ok": False,
                "error": str(e)
            }, 500)


    def admin_premium_approve(self):
        try:
            user, error = self._admin_authorized()

            if error:
                return json_response(self, {
                    "ok": False,
                    "error": error
                }, 403)

            length = int(
                self.headers.get("Content-Length", "0")
            )

            if length <= 0 or length > 20_000:
                return json_response(self, {
                    "ok": False,
                    "error": "Invalid request body"
                }, 400)

            payload = json.loads(
                self.rfile.read(length).decode("utf-8")
            )

            request_id = int(
                payload.get("request_id", 0)
            )

            days = int(
                payload.get("days", 0)
            )

            admin_note = str(
                payload.get("admin_note", "")
            ).strip()[:1000]

            if request_id <= 0:
                return json_response(self, {
                    "ok": False,
                    "error": "Invalid request_id"
                }, 400)

            if days <= 0 or days > 3650:
                return json_response(self, {
                    "ok": False,
                    "error": "Premium days must be between 1 and 3650"
                }, 400)

            now = datetime.now(timezone.utc)
            now_text = now.isoformat()

            with get_db() as db:
                request = db.execute("""
                    SELECT
                        pr.id,
                        pr.user_id,
                        pr.status,
                        u.premium_until
                    FROM premium_requests pr
                    JOIN users u ON u.id = pr.user_id
                    WHERE pr.id = ?
                """, (request_id,)).fetchone()

                if not request:
                    return json_response(self, {
                        "ok": False,
                        "error": "Premium request not found"
                    }, 404)

                if request["status"] != "pending":
                    return json_response(self, {
                        "ok": False,
                        "error": "Premium request is already processed"
                    }, 409)

                base_time = now

                existing_until = request["premium_until"]

                if existing_until:
                    try:
                        parsed_until = datetime.fromisoformat(
                            existing_until.replace("Z", "+00:00")
                        )

                        if parsed_until.tzinfo is None:
                            parsed_until = parsed_until.replace(
                                tzinfo=timezone.utc
                            )

                        if parsed_until > now:
                            base_time = parsed_until

                    except (ValueError, TypeError):
                        pass

                premium_until = (
                    base_time + timedelta(days=days)
                ).isoformat()

                db.execute("""
                    UPDATE users
                    SET
                        is_premium = 1,
                        premium_until = ?
                    WHERE id = ?
                """, (
                    premium_until,
                    request["user_id"]
                ))

                db.execute("""
                    UPDATE premium_requests
                    SET
                        requested_days = ?,
                        status = 'approved',
                        admin_note = ?,
                        processed_at = ?
                    WHERE id = ?
                """, (
                    days,
                    admin_note,
                    now_text,
                    request_id
                ))

            return json_response(self, {
                "ok": True,
                "message": "Premium approved",
                "request_id": request_id,
                "days": days,
                "premium_until": premium_until
            })

        except (ValueError, TypeError):
            return json_response(self, {
                "ok": False,
                "error": "Invalid approval data"
            }, 400)

        except json.JSONDecodeError:
            return json_response(self, {
                "ok": False,
                "error": "Invalid JSON"
            }, 400)

        except Exception as e:
            return json_response(self, {
                "ok": False,
                "error": str(e)
            }, 500)


    def admin_premium_reject(self):
        try:
            user, error = self._admin_authorized()

            if error:
                return json_response(self, {
                    "ok": False,
                    "error": error
                }, 403)

            length = int(
                self.headers.get("Content-Length", "0")
            )

            if length <= 0 or length > 20_000:
                return json_response(self, {
                    "ok": False,
                    "error": "Invalid request body"
                }, 400)

            payload = json.loads(
                self.rfile.read(length).decode("utf-8")
            )

            request_id = int(
                payload.get("request_id", 0)
            )

            admin_note = str(
                payload.get("admin_note", "")
            ).strip()[:1000]

            if request_id <= 0:
                return json_response(self, {
                    "ok": False,
                    "error": "Invalid request_id"
                }, 400)

            if not admin_note:
                return json_response(self, {
                    "ok": False,
                    "error": "Reject reason is required"
                }, 400)

            now_text = datetime.now(timezone.utc).isoformat()

            with get_db() as db:
                request = db.execute("""
                    SELECT id, status
                    FROM premium_requests
                    WHERE id = ?
                """, (request_id,)).fetchone()

                if not request:
                    return json_response(self, {
                        "ok": False,
                        "error": "Premium request not found"
                    }, 404)

                if request["status"] != "pending":
                    return json_response(self, {
                        "ok": False,
                        "error": "Premium request is already processed"
                    }, 409)

                db.execute("""
                    UPDATE premium_requests
                    SET
                        status = 'rejected',
                        admin_note = ?,
                        processed_at = ?
                    WHERE id = ?
                """, (
                    admin_note,
                    now_text,
                    request_id
                ))

            return json_response(self, {
                "ok": True,
                "message": "Premium request rejected",
                "request_id": request_id
            })

        except (ValueError, TypeError):
            return json_response(self, {
                "ok": False,
                "error": "Invalid rejection data"
            }, 400)

        except json.JSONDecodeError:
            return json_response(self, {
                "ok": False,
                "error": "Invalid JSON"
            }, 400)

        except Exception as e:
            return json_response(self, {
                "ok": False,
                "error": str(e)
            }, 500)


    def admin_drop(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))

            if length <= 0 or length > 10_000:
                return json_response(self, {
                    "ok": False,
                    "error": "Invalid request body"
                }, 400)

            payload = json.loads(
                self.rfile.read(length).decode("utf-8")
            )

            telegram_id = int(payload.get("telegram_id", 0))
            rarity = str(payload.get("rarity", "")).lower().strip()

            if telegram_id != OWNER_ID:
                return json_response(self, {
                    "ok": False,
                    "error": "Owner authorization required"
                }, 403)

            if rarity not in ("legendary", "mythic"):
                return json_response(self, {
                    "ok": False,
                    "error": "Invalid rarity"
                }, 400)

            now = datetime.now(timezone.utc)
            expires = now + timedelta(seconds=30)

            with get_db() as db:
                db.execute(
                    """
                    UPDATE drops
                    SET status = 'expired'
                    WHERE status = 'active'
                      AND expires_at <= ?
                    """,
                    (now.isoformat(),)
                )

                card = db.execute(
                    """
                    SELECT id, card_code, name, rarity, image_path
                    FROM cards
                    WHERE is_active = 1
                      AND rarity = ?
                    ORDER BY RANDOM()
                    LIMIT 1
                    """,
                    (rarity,)
                ).fetchone()

                if not card:
                    return json_response(self, {
                        "ok": False,
                        "error": f"No active {rarity} cards available"
                    }, 404)

                active = db.execute(
                    """
                    SELECT id
                    FROM drops
                    WHERE card_id = ?
                      AND status = 'active'
                    LIMIT 1
                    """,
                    (card["id"],)
                ).fetchone()

                if active:
                    return json_response(self, {
                        "ok": False,
                        "error": "This card already has an active drop"
                    }, 409)

                cur = db.execute(
                    """
                    INSERT INTO drops
                        (card_id, started_at, expires_at, status)
                    VALUES (?, ?, ?, 'active')
                    """,
                    (
                        card["id"],
                        now.isoformat(),
                        expires.isoformat(),
                    )
                )

                drop_id = cur.lastrowid

            return json_response(self, {
                "ok": True,
                "drop": {
                    "id": drop_id,
                    "card_id": card["id"],
                    "card_code": card["card_code"],
                    "name": card["name"],
                    "rarity": card["rarity"],
                    "image_path": card["image_path"],
                    "expires_at": expires.isoformat()
                }
            }, 201)

        except Exception as exc:
            print("[ADMIN DROP ERROR]", repr(exc))
            return json_response(self, {
                "ok": False,
                "error": str(exc)
            }, 500)


    def verify_telegram_init_data(self, init_data):
        if not BOT_TOKEN:
            return None, "BOT_TOKEN is not configured"

        if not init_data:
            return None, "Telegram initData is required"

        try:
            pairs = dict(parse_qsl(init_data, keep_blank_values=True))
            received_hash = pairs.pop("hash", None)

            if not received_hash:
                return None, "Invalid Telegram initData"

            data_check_string = "\n".join(
                f"{key}={pairs[key]}"
                for key in sorted(pairs)
            )

            secret_key = hmac.new(
                b"WebAppData",
                BOT_TOKEN.encode("utf-8"),
                hashlib.sha256
            ).digest()

            calculated_hash = hmac.new(
                secret_key,
                data_check_string.encode("utf-8"),
                hashlib.sha256
            ).hexdigest()

            if not hmac.compare_digest(calculated_hash, received_hash):
                return None, "Telegram initData verification failed"

            user_raw = pairs.get("user")
            if not user_raw:
                return None, "Telegram user data missing"

            user = json.loads(user_raw)

            if not user.get("id"):
                return None, "Telegram user ID missing"

            return user, None

        except Exception:
            return None, "Invalid Telegram initData"


    def catch_card(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))

            if length <= 0 or length > 100_000:
                return json_response(self, {
                    "ok": False,
                    "error": "Invalid request body"
                }, 400)

            raw = self.rfile.read(length)

            payload = json.loads(raw.decode("utf-8"))
            init_data = payload.get("initData", "")
            catch_name = payload.get("catch_name", "")

            telegram_user, error = self.verify_telegram_init_data(init_data)

            if error:
                return json_response(self, {
                    "ok": False,
                    "error": error
                }, 401)

            telegram_id = int(telegram_user["id"])
            username = telegram_user.get("username")
            first_name = telegram_user.get("first_name") or "Player"

            now = datetime.now(timezone.utc).isoformat()

            with get_db() as db:
                # Make sure this Telegram user exists.
                db.execute(
                    """
                    INSERT INTO users
                        (telegram_id, username, first_name)
                    VALUES (?, ?, ?)
                    ON CONFLICT(telegram_id) DO UPDATE SET
                        username = excluded.username,
                        first_name = excluded.first_name
                    """,
                    (telegram_id, username, first_name)
                )

                user_row = db.execute(
                    """
                    SELECT id
                    FROM users
                    WHERE telegram_id = ?
                    """,
                    (telegram_id,)
                ).fetchone()

                # Expire old drops first.
                db.execute(
                    """
                    UPDATE drops
                    SET status = 'expired'
                    WHERE status = 'active'
                      AND expires_at <= ?
                    """,
                    (now,)
                )

                drop = db.execute(
                    """
                    SELECT
                        d.id,
                        d.card_id,
                        d.expires_at,
                        c.card_code,
                        c.name,
                        c.rarity,
                        c.image_path
                    FROM drops d
                    JOIN cards c ON c.id = d.card_id
                    WHERE d.status = 'active'
                    ORDER BY d.id DESC
                    LIMIT 1
                    """
                ).fetchone()

                if not drop:
                    return json_response(self, {
                        "ok": False,
                        "error": "No active drop"
                    }, 409)

                # Validate the card name typed by the player.
                def normalize_card_name(value):
                    return " ".join(
                        str(value or "").strip().split()
                    ).casefold()

                entered_name = normalize_card_name(catch_name)
                actual_name = normalize_card_name(drop["name"])

                if not entered_name:
                    return json_response(self, {
                        "ok": False,
                        "error": "Please type the card name"
                    }, 400)

                if entered_name != actual_name:
                    return json_response(self, {
                        "ok": False,
                        "error": "Wrong card name"
                    }, 400)

                # Atomic winner selection.
                cursor = db.execute(
                    """
                    UPDATE drops
                    SET status = 'caught',
                        winner_user_id = ?
                    WHERE id = ?
                      AND status = 'active'
                      AND expires_at > ?
                    """,
                    (
                        user_row["id"],
                        drop["id"],
                        now
                    )
                )

                if cursor.rowcount != 1:
                    return json_response(self, {
                        "ok": False,
                        "error": "Someone caught this drop first"
                    }, 409)

                db.execute(
                    """
                    INSERT INTO collections(user_id, card_id, quantity)
                    VALUES (?, ?, 1)
                    ON CONFLICT(user_id, card_id)
                    DO UPDATE SET quantity = quantity + 1
                    """,
                    (
                        user_row["id"],
                        drop["card_id"]
                    )
                )

                # Epic monthly claim tracking.
                #
                # Only the atomic winner reaches this point.
                # Therefore each successful Epic catch counts
                # exactly once.
                if drop["rarity"] == "epic":
                    current_month = datetime.now(
                        timezone.utc
                    ).strftime("%Y-%m")

                    saved_month = get_text_setting(
                        db,
                        "epic_month",
                        ""
                    )

                    if saved_month != current_month:
                        set_setting_value(
                            db,
                            "epic_month",
                            current_month
                        )

                        set_setting_value(
                            db,
                            "monthly_epic_claimed",
                            0
                        )

                    claimed = get_setting(
                        db,
                        "monthly_epic_claimed",
                        0
                    )

                    monthly_limit = get_setting(
                        db,
                        "epic_monthly_limit",
                        EPIC_DEFAULT_MONTHLY_LIMIT
                    )

                    if claimed < monthly_limit:
                        set_setting_value(
                            db,
                            "monthly_epic_claimed",
                            claimed + 1
                        )

                    # This Epic slot has been successfully caught.
                    # The next Epic slot may select a new card.
                    set_setting_value(
                        db,
                        "epic_current_card_id",
                        0
                    )

            return json_response(self, {
                "ok": True,
                "message": "Card caught successfully",
                "drop": {
                    "id": drop["id"],
                    "card_id": drop["card_id"],
                    "card_code": drop["card_code"],
                    "name": drop["name"],
                    "rarity": drop["rarity"],
                    "image_path": drop["image_path"]
                }
            })

        except json.JSONDecodeError:
            return json_response(self, {
                "ok": False,
                "error": "Invalid JSON"
            }, 400)

        except Exception as e:
            return json_response(self, {
                "ok": False,
                "error": str(e)
            }, 500)


    def _get_authenticated_user(self):
        """
        Authenticate the Telegram Web App user.

        Prefer X-Telegram-Init-Data header.
        Keep ?initData=... as fallback.
        """
        init_data = self.headers.get(
            "X-Telegram-Init-Data",
            ""
        ).strip()

        if not init_data:
            query = parse_qsl(
                urlparse(self.path).query,
                keep_blank_values=True
            )
            params = dict(query)
            init_data = params.get("initData", "").strip()

        telegram_user, error = self.verify_telegram_init_data(
            init_data
        )

        if error:
            return None, error

        telegram_id = int(telegram_user["id"])
        username = telegram_user.get("username")
        first_name = telegram_user.get("first_name") or "Player"

        with get_db() as db:
            # Auto-register verified Telegram users.
            db.execute(
                """
                INSERT INTO users
                    (telegram_id, username, first_name)
                VALUES (?, ?, ?)
                ON CONFLICT(telegram_id) DO UPDATE SET
                    username = excluded.username,
                    first_name = excluded.first_name
                """,
                (telegram_id, username, first_name)
            )

            row = db.execute("""
                SELECT *
                FROM users
                WHERE telegram_id = ?
            """, (telegram_id,)).fetchone()

        if not row:
            return None, "Unable to create Telegram user"

        return row, None


    def me(self):
        try:
            user, error = self._get_authenticated_user()

            if error:
                return json_response(self, {
                    "ok": False,
                    "error": error
                }, 401)

            return json_response(self, {
                "ok": True,
                "user": {
                    "id": user["id"],
                    "telegram_id": user["telegram_id"],
                    "username": user["username"],
                    "first_name": user["first_name"],
                    "is_owner": bool(user["is_owner"]),
                    "is_premium": bool(user["is_premium"]),
                    "premium_until": user["premium_until"]
                }
            })

        except Exception as e:
            return json_response(self, {
                "ok": False,
                "error": str(e)
            }, 500)


    def collection(self):
        try:
            user, error = self._get_authenticated_user()

            if error:
                return json_response(self, {
                    "ok": False,
                    "error": error
                }, 401)

            with get_db() as db:
                rows = db.execute("""
                    SELECT
                        c.id,
                        c.card_code,
                        c.name,
                        c.rarity,
                        c.image_path,
                        co.quantity,
                        co.first_obtained_at
                    FROM collections co
                    JOIN cards c ON c.id = co.card_id
                    WHERE co.user_id = ?
                    ORDER BY
                        CASE c.rarity
                            WHEN 'mythic' THEN 1
                            WHEN 'legendary' THEN 2
                            WHEN 'epic' THEN 3
                            WHEN 'rare' THEN 4
                            WHEN 'uncommon' THEN 5
                            WHEN 'common' THEN 6
                        END,
                        c.id DESC
                """, (user["id"],)).fetchall()

            return json_response(self, {
                "ok": True,
                "cards": [dict(row) for row in rows]
            })

        except Exception as e:
            return json_response(self, {
                "ok": False,
                "error": str(e)
            }, 500)


    def events(self):
        try:
            rows = []

            with get_db() as db:
                events = db.execute("""
                    SELECT
                        e.id,
                        e.name,
                        e.max_players,
                        e.status,
                        e.created_at,
                        COUNT(ep.user_id) AS players
                    FROM events e
                    LEFT JOIN event_players ep
                        ON ep.event_id = e.id
                    GROUP BY e.id
                    ORDER BY e.id DESC
                """).fetchall()

                rows = [dict(row) for row in events]

            return json_response(self, {
                "ok": True,
                "events": rows
            })

        except Exception as e:
            return json_response(self, {
                "ok": False,
                "error": str(e)
            }, 500)


    def battles(self):
        try:
            user, error = self._get_authenticated_user()

            if error:
                return json_response(self, {
                    "ok": False,
                    "error": error
                }, 401)

            with get_db() as db:
                rows = db.execute("""
                    SELECT
                        b.id,
                        b.challenger_id,
                        b.opponent_id,
                        b.challenger_card_id,
                        b.opponent_card_id,
                        b.status,
                        b.winner_user_id,
                        b.created_at
                    FROM battles b
                    WHERE b.challenger_id = ?
                       OR b.opponent_id = ?
                    ORDER BY b.id DESC
                """, (
                    user["id"],
                    user["id"]
                )).fetchall()

            return json_response(self, {
                "ok": True,
                "battles": [dict(row) for row in rows]
            })

        except Exception as e:
            return json_response(self, {
                "ok": False,
                "error": str(e)
            }, 500)


    def trades(self):
        try:
            user, error = self._get_authenticated_user()

            if error:
                return json_response(self, {
                    "ok": False,
                    "error": error
                }, 401)

            with get_db() as db:
                rows = db.execute("""
                    SELECT
                        t.id,
                        t.from_user_id,
                        t.to_user_id,
                        t.offered_card_id,
                        t.requested_card_id,
                        t.status,
                        t.created_at,

                        fu.username AS from_username,
                        fu.first_name AS from_first_name,
                        tu.username AS to_username,
                        tu.first_name AS to_first_name,

                        oc.card_code AS offered_card_code,
                        oc.name AS offered_card_name,
                        oc.rarity AS offered_rarity,

                        rc.card_code AS requested_card_code,
                        rc.name AS requested_card_name,
                        rc.rarity AS requested_rarity

                    FROM trades t

                    JOIN users fu
                      ON fu.id = t.from_user_id

                    JOIN users tu
                      ON tu.id = t.to_user_id

                    JOIN cards oc
                      ON oc.id = t.offered_card_id

                    LEFT JOIN cards rc
                      ON rc.id = t.requested_card_id

                    WHERE t.from_user_id = ?
                       OR t.to_user_id = ?

                    ORDER BY t.id DESC
                """, (
                    user["id"],
                    user["id"]
                )).fetchall()

            return json_response(self, {
                "ok": True,
                "trades": [dict(row) for row in rows]
            })

        except Exception as e:
            return json_response(self, {
                "ok": False,
                "error": str(e)
            }, 500)


    def _trade_json(self):
        length = int(
            self.headers.get("Content-Length", "0")
        )

        if length <= 0 or length > 100_000:
            return None, json_response(self, {
                "ok": False,
                "error": "Invalid request body"
            }, 400)

        try:
            raw = self.rfile.read(length)
            payload = json.loads(
                raw.decode("utf-8")
            )
        except Exception:
            return None, json_response(self, {
                "ok": False,
                "error": "Invalid JSON"
            }, 400)

        if not isinstance(payload, dict):
            return None, json_response(self, {
                "ok": False,
                "error": "Invalid request payload"
            }, 400)

        return payload, None


    def trade_create(self):
        payload, error_response = self._trade_json()

        if error_response:
            return error_response

        user, error = self._get_authenticated_user()

        if error:
            return json_response(self, {
                "ok": False,
                "error": error
            }, 401)

        try:
            target_telegram_id = int(
                payload.get("to_user_id")
            )

            offered_card_id = int(
                payload.get("offered_card_id")
            )

            requested_card_id = int(
                payload.get("requested_card_id")
            )

        except (TypeError, ValueError):
            return json_response(self, {
                "ok": False,
                "error": "Invalid trade data"
            }, 400)

        if target_telegram_id == int(
            user["telegram_id"]
        ):
            return json_response(self, {
                "ok": False,
                "error": "You cannot trade with yourself"
            }, 400)

        if offered_card_id == requested_card_id:
            return json_response(self, {
                "ok": False,
                "error": "You cannot trade the same card"
            }, 400)

        try:
            with get_db() as db:
                sender = db.execute("""
                    SELECT id
                    FROM users
                    WHERE id = ?
                    LIMIT 1
                """, (
                    user["id"],
                )).fetchone()

                receiver = db.execute("""
                    SELECT id, telegram_id
                    FROM users
                    WHERE telegram_id = ?
                    LIMIT 1
                """, (
                    target_telegram_id,
                )).fetchone()

                if not sender:
                    return json_response(self, {
                        "ok": False,
                        "error": "Sender not found"
                    }, 404)

                if not receiver:
                    return json_response(self, {
                        "ok": False,
                        "error": "Target Telegram user not found"
                    }, 404)

                to_user_id = int(
                    receiver["id"]
                )

                if to_user_id == user["id"]:
                    return json_response(self, {
                        "ok": False,
                        "error": "You cannot trade with yourself"
                    }, 400)

                offered = db.execute("""
                    SELECT
                        id,
                        card_code,
                        name,
                        rarity,
                        is_active
                    FROM cards
                    WHERE id = ?
                    LIMIT 1
                """, (
                    offered_card_id,
                )).fetchone()

                requested = db.execute("""
                    SELECT
                        id,
                        card_code,
                        name,
                        rarity,
                        is_active
                    FROM cards
                    WHERE id = ?
                    LIMIT 1
                """, (
                    requested_card_id,
                )).fetchone()

                if not offered or not offered["is_active"]:
                    return json_response(self, {
                        "ok": False,
                        "error": "Offered card not found"
                    }, 404)

                if not requested or not requested["is_active"]:
                    return json_response(self, {
                        "ok": False,
                        "error": "Requested card not found"
                    }, 404)

                if offered["rarity"] != requested["rarity"]:
                    return json_response(self, {
                        "ok": False,
                        "error": (
                            "Trade requires cards of the same rarity"
                        )
                    }, 400)

                ownership = db.execute("""
                    SELECT quantity
                    FROM collections
                    WHERE user_id = ?
                      AND card_id = ?
                    LIMIT 1
                """, (
                    user["id"],
                    offered_card_id
                )).fetchone()

                if not ownership or int(
                    ownership["quantity"] or 0
                ) < 1:
                    return json_response(self, {
                        "ok": False,
                        "error": "You do not own the offered card"
                    }, 400)

                target_ownership = db.execute("""
                    SELECT quantity
                    FROM collections
                    WHERE user_id = ?
                      AND card_id = ?
                    LIMIT 1
                """, (
                    to_user_id,
                    requested_card_id
                )).fetchone()

                if not target_ownership or int(
                    target_ownership["quantity"] or 0
                ) < 1:
                    return json_response(self, {
                        "ok": False,
                        "error": (
                            "Target user does not own "
                            "the requested card"
                        )
                    }, 400)

                cursor = db.execute("""
                    INSERT INTO trades(
                        from_user_id,
                        to_user_id,
                        offered_card_id,
                        requested_card_id,
                        status
                    )
                    VALUES (?, ?, ?, ?, 'pending')
                """, (
                    user["id"],
                    to_user_id,
                    offered_card_id,
                    requested_card_id
                ))

                db.commit()

                return json_response(self, {
                    "ok": True,
                    "trade": {
                        "id": cursor.lastrowid,
                        "status": "pending",
                        "from_user_id": user["id"],
                        "to_user_id": to_user_id,
                        "offered_card_id": offered_card_id,
                        "requested_card_id": requested_card_id,
                        "rarity": offered["rarity"]
                    }
                }, 201)

        except Exception as e:
            return json_response(self, {
                "ok": False,
                "error": str(e)
            }, 500)


    def _trade_change_quantity(
        self,
        db,
        user_id,
        card_id,
        delta
    ):
        row = db.execute("""
            SELECT quantity
            FROM collections
            WHERE user_id = ?
              AND card_id = ?
            LIMIT 1
        """, (
            user_id,
            card_id
        )).fetchone()

        current = int(
            row["quantity"] if row else 0
        )

        new_quantity = current + delta

        if new_quantity < 0:
            return False

        if new_quantity == 0:
            db.execute("""
                DELETE FROM collections
                WHERE user_id = ?
                  AND card_id = ?
            """, (
                user_id,
                card_id
            ))
            return True

        if row:
            cursor = db.execute("""
                UPDATE collections
                SET quantity = ?
                WHERE user_id = ?
                  AND card_id = ?
            """, (
                new_quantity,
                user_id,
                card_id
            ))

            return cursor.rowcount == 1

        db.execute("""
            INSERT INTO collections(
                user_id,
                card_id,
                quantity
            )
            VALUES (?, ?, ?)
        """, (
            user_id,
            card_id,
            new_quantity
        ))

        return True


    def trade_accept(self):
        payload, error_response = self._trade_json()

        if error_response:
            return error_response

        user, error = self._get_authenticated_user()

        if error:
            return json_response(self, {
                "ok": False,
                "error": error
            }, 401)

        try:
            trade_id = int(
                payload.get("trade_id")
            )
        except (TypeError, ValueError):
            return json_response(self, {
                "ok": False,
                "error": "Invalid trade ID"
            }, 400)

        try:
            with get_db() as db:
                db.execute("BEGIN IMMEDIATE")

                trade = db.execute("""
                    SELECT
                        id,
                        from_user_id,
                        to_user_id,
                        offered_card_id,
                        requested_card_id,
                        status
                    FROM trades
                    WHERE id = ?
                    LIMIT 1
                """, (
                    trade_id,
                )).fetchone()

                if not trade:
                    db.rollback()
                    return json_response(self, {
                        "ok": False,
                        "error": "Trade not found"
                    }, 404)

                if trade["to_user_id"] != user["id"]:
                    db.rollback()
                    return json_response(self, {
                        "ok": False,
                        "error": (
                            "Only the target user can "
                            "accept this trade"
                        )
                    }, 403)

                if trade["status"] != "pending":
                    db.rollback()
                    return json_response(self, {
                        "ok": False,
                        "error": "Trade is no longer pending"
                    }, 409)

                from_user_id = int(
                    trade["from_user_id"]
                )

                to_user_id = int(
                    trade["to_user_id"]
                )

                offered_card_id = int(
                    trade["offered_card_id"]
                )

                requested_card_id = int(
                    trade["requested_card_id"]
                )

                if from_user_id == to_user_id:
                    db.rollback()
                    return json_response(self, {
                        "ok": False,
                        "error": "Invalid self-trade"
                    }, 400)

                if offered_card_id == requested_card_id:
                    db.rollback()
                    return json_response(self, {
                        "ok": False,
                        "error": "Invalid same-card trade"
                    }, 400)

                cards = db.execute("""
                    SELECT id, rarity, is_active
                    FROM cards
                    WHERE id IN (?, ?)
                """, (
                    offered_card_id,
                    requested_card_id
                )).fetchall()

                if len(cards) != 2:
                    db.rollback()
                    return json_response(self, {
                        "ok": False,
                        "error": "Trade card not found"
                    }, 404)

                card_map = {
                    int(row["id"]): row
                    for row in cards
                }

                offered = card_map.get(
                    offered_card_id
                )

                requested = card_map.get(
                    requested_card_id
                )

                if not offered["is_active"] or not requested["is_active"]:
                    db.rollback()
                    return json_response(self, {
                        "ok": False,
                        "error": "One of the cards is inactive"
                    }, 400)

                if offered["rarity"] != requested["rarity"]:
                    db.rollback()
                    return json_response(self, {
                        "ok": False,
                        "error": (
                            "Trade requires cards of "
                            "the same rarity"
                        )
                    }, 400)

                from_collection = db.execute("""
                    SELECT quantity
                    FROM collections
                    WHERE user_id = ?
                      AND card_id = ?
                    LIMIT 1
                """, (
                    from_user_id,
                    offered_card_id
                )).fetchone()

                to_collection = db.execute("""
                    SELECT quantity
                    FROM collections
                    WHERE user_id = ?
                      AND card_id = ?
                    LIMIT 1
                """, (
                    to_user_id,
                    requested_card_id
                )).fetchone()

                from_quantity = int(
                    from_collection["quantity"]
                    if from_collection else 0
                )

                to_quantity = int(
                    to_collection["quantity"]
                    if to_collection else 0
                )

                if from_quantity < 1:
                    db.rollback()
                    return json_response(self, {
                        "ok": False,
                        "error": (
                            "Sender no longer owns "
                            "the offered card"
                        )
                    }, 409)

                if to_quantity < 1:
                    db.rollback()
                    return json_response(self, {
                        "ok": False,
                        "error": (
                            "You no longer own "
                            "the requested card"
                        )
                    }, 409)

                # Remove one offered card from sender.
                if not self._trade_change_quantity(
                    db,
                    from_user_id,
                    offered_card_id,
                    -1
                ):
                    db.rollback()
                    return json_response(self, {
                        "ok": False,
                        "error": "Failed to remove offered card"
                    }, 409)

                # Remove one requested card from receiver.
                if not self._trade_change_quantity(
                    db,
                    to_user_id,
                    requested_card_id,
                    -1
                ):
                    db.rollback()
                    return json_response(self, {
                        "ok": False,
                        "error": "Failed to remove requested card"
                    }, 409)

                # Give offered card to receiver.
                if not self._trade_change_quantity(
                    db,
                    to_user_id,
                    offered_card_id,
                    1
                ):
                    db.rollback()
                    return json_response(self, {
                        "ok": False,
                        "error": "Failed to give offered card"
                    }, 409)

                # Give requested card to sender.
                if not self._trade_change_quantity(
                    db,
                    from_user_id,
                    requested_card_id,
                    1
                ):
                    db.rollback()
                    return json_response(self, {
                        "ok": False,
                        "error": "Failed to give requested card"
                    }, 409)

                cursor = db.execute("""
                    UPDATE trades
                    SET status = 'accepted'
                    WHERE id = ?
                      AND status = 'pending'
                      AND to_user_id = ?
                """, (
                    trade_id,
                    user["id"]
                ))

                if cursor.rowcount != 1:
                    db.rollback()
                    return json_response(self, {
                        "ok": False,
                        "error": "Trade was already processed"
                    }, 409)

                db.commit()

                return json_response(self, {
                    "ok": True,
                    "trade": {
                        "id": trade_id,
                        "status": "accepted"
                    }
                })

        except Exception as e:
            try:
                db.rollback()
            except Exception:
                pass

            return json_response(self, {
                "ok": False,
                "error": str(e)
            }, 500)


    def trade_reject(self):
        payload, error_response = self._trade_json()

        if error_response:
            return error_response

        user, error = self._get_authenticated_user()

        if error:
            return json_response(self, {
                "ok": False,
                "error": error
            }, 401)

        try:
            trade_id = int(
                payload.get("trade_id")
            )
        except (TypeError, ValueError):
            return json_response(self, {
                "ok": False,
                "error": "Invalid trade ID"
            }, 400)

        try:
            with get_db() as db:
                cursor = db.execute("""
                    UPDATE trades
                    SET status = 'rejected'
                    WHERE id = ?
                      AND to_user_id = ?
                      AND status = 'pending'
                """, (
                    trade_id,
                    user["id"]
                ))

                if cursor.rowcount != 1:
                    return json_response(self, {
                        "ok": False,
                        "error": (
                            "Trade not found or "
                            "already processed"
                        )
                    }, 409)

                db.commit()

            return json_response(self, {
                "ok": True,
                "trade": {
                    "id": trade_id,
                    "status": "rejected"
                }
            })

        except Exception as e:
            return json_response(self, {
                "ok": False,
                "error": str(e)
            }, 500)


    def trade_cancel(self):
        payload, error_response = self._trade_json()

        if error_response:
            return error_response

        user, error = self._get_authenticated_user()

        if error:
            return json_response(self, {
                "ok": False,
                "error": error
            }, 401)

        try:
            trade_id = int(
                payload.get("trade_id")
            )
        except (TypeError, ValueError):
            return json_response(self, {
                "ok": False,
                "error": "Invalid trade ID"
            }, 400)

        try:
            with get_db() as db:
                cursor = db.execute("""
                    UPDATE trades
                    SET status = 'cancelled'
                    WHERE id = ?
                      AND from_user_id = ?
                      AND status = 'pending'
                """, (
                    trade_id,
                    user["id"]
                ))

                if cursor.rowcount != 1:
                    return json_response(self, {
                        "ok": False,
                        "error": (
                            "Trade not found or "
                            "already processed"
                        )
                    }, 409)

                db.commit()

            return json_response(self, {
                "ok": True,
                "trade": {
                    "id": trade_id,
                    "status": "cancelled"
                }
            })

        except Exception as e:
            return json_response(self, {
                "ok": False,
                "error": str(e)
            }, 500)


    def premium(self):
        try:
            user, error = self._get_authenticated_user()

            if error:
                return json_response(self, {
                    "ok": False,
                    "error": error
                }, 401)

            with get_db() as db:
                requests = db.execute("""
                    SELECT
                        id,
                        amount_mmk,
                        requested_days,
                        status,
                        created_at,
                        processed_at
                    FROM premium_requests
                    WHERE user_id = ?
                    ORDER BY id DESC
                    LIMIT 20
                """, (user["id"],)).fetchall()

            return json_response(self, {
                "ok": True,
                "premium": {
                    "is_premium": bool(user["is_premium"]),
                    "premium_until": user["premium_until"]
                },
                "requests": [dict(row) for row in requests]
            })

        except Exception as e:
            return json_response(self, {
                "ok": False,
                "error": str(e)
            }, 500)


    def premium_request(self):
        try:
            length = int(
                self.headers.get("Content-Length", "0")
            )

            # JSON requests may contain a receipt encoded as base64.
            # Keep the total request reasonably small.
            if length <= 0 or length > 4_500_000:
                return json_response(self, {
                    "ok": False,
                    "error": "Request or receipt is too large"
                }, 400)

            raw = self.rfile.read(length)
            payload = json.loads(
                raw.decode("utf-8")
            )

            # Authenticate Telegram Web App user before
            # validating any payment fields.
            telegram_user, error = self.verify_telegram_init_data(
                self.headers.get(
                    "X-Telegram-Init-Data",
                    ""
                ).strip()
            )

            if error:
                return json_response(self, {
                    "ok": False,
                    "error": error
                }, 401)

            telegram_id = int(
                telegram_user["id"]
            )

            amount_mmk = int(
                payload.get("amount_mmk", 0)
            )

            payment_method = str(
                payload.get("payment_method", "")
            ).strip()[:100]

            receipt_note = str(
                payload.get("receipt_note", "")
            ).strip()[:1000]

            receipt_data = str(
                payload.get("receipt_data", "")
            ).strip()

            receipt_name = str(
                payload.get("receipt_name", "")
            ).strip().lower()

            if amount_mmk <= 0:
                return json_response(self, {
                    "ok": False,
                    "error": "Invalid premium amount"
                }, 400)

            if not payment_method:
                return json_response(self, {
                    "ok": False,
                    "error": "Payment method is required"
                }, 400)

            if not receipt_data:
                return json_response(self, {
                    "ok": False,
                    "error": "Payment receipt is required"
                }, 400)

            # Accept only image receipts.
            allowed_extensions = {
                ".jpg",
                ".jpeg",
                ".png",
                ".webp"
            }

            suffix = Path(receipt_name).suffix.lower()

            if suffix not in allowed_extensions:
                return json_response(self, {
                    "ok": False,
                    "error": "Receipt must be JPG, JPEG, PNG or WEBP"
                }, 400)

            # Remove optional data URL prefix.
            if "," in receipt_data:
                prefix, encoded = receipt_data.split(",", 1)

                if "image/" not in prefix:
                    return json_response(self, {
                        "ok": False,
                        "error": "Invalid receipt image"
                    }, 400)

                receipt_data = encoded

            # Decode receipt safely.
            import base64
            import binascii

            try:
                receipt_bytes = base64.b64decode(
                    receipt_data,
                    validate=True
                )
            except (ValueError, binascii.Error):
                return json_response(self, {
                    "ok": False,
                    "error": "Invalid receipt encoding"
                }, 400)

            # Limit decoded image size to 3 MB.
            if len(receipt_bytes) <= 0 or len(receipt_bytes) > 3_000_000:
                return json_response(self, {
                    "ok": False,
                    "error": "Receipt must be smaller than 3 MB"
                }, 400)

            # Basic image signatures.
            signatures = {
                ".jpg": (b"\xff\xd8\xff",),
                ".jpeg": (b"\xff\xd8\xff",),
                ".png": (b"\x89PNG\r\n\x1a\n",),
                ".webp": (b"RIFF",)
            }

            valid_signature = any(
                receipt_bytes.startswith(sig)
                for sig in signatures[suffix]
            )

            if suffix == ".webp":
                valid_signature = (
                    valid_signature and
                    len(receipt_bytes) >= 12 and
                    receipt_bytes[8:12] == b"WEBP"
                )

            if not valid_signature:
                return json_response(self, {
                    "ok": False,
                    "error": "Invalid receipt image format"
                }, 400)

            upload_root = (
                BASE_DIR /
                "uploads" /
                "premium"
            )

            upload_root.mkdir(
                parents=True,
                exist_ok=True
            )

            with get_db() as db:
                # Make sure the verified Telegram user exists.
                db.execute(
                    """
                    INSERT INTO users
                        (telegram_id, username, first_name)
                    VALUES (?, ?, ?)
                    ON CONFLICT(telegram_id) DO UPDATE SET
                        username = excluded.username,
                        first_name = excluded.first_name
                    """,
                    (
                        telegram_id,
                        telegram_user.get("username"),
                        telegram_user.get("first_name") or "Player"
                    )
                )

                user = db.execute("""
                    SELECT
                        id,
                        is_premium,
                        premium_until
                    FROM users
                    WHERE telegram_id = ?
                """, (telegram_id,)).fetchone()

                if not user:
                    return json_response(self, {
                        "ok": False,
                        "error": "Unable to create user"
                    }, 500)

                # Do not create multiple active pending requests.
                existing = db.execute("""
                    SELECT id
                    FROM premium_requests
                    WHERE user_id = ?
                      AND status = 'pending'
                    ORDER BY id DESC
                    LIMIT 1
                """, (user["id"],)).fetchone()

                if existing:
                    return json_response(self, {
                        "ok": False,
                        "error": (
                            "You already have a pending "
                            "Premium request"
                        ),
                        "request_id": existing["id"]
                    }, 409)

                cursor = db.execute("""
                    INSERT INTO premium_requests(
                        user_id,
                        amount_mmk,
                        requested_days,
                        payment_method,
                        receipt_note,
                        status
                    )
                    VALUES (?, ?, NULL, ?, ?, 'pending')
                """, (
                    user["id"],
                    amount_mmk,
                    payment_method,
                    receipt_note
                ))

                request_id = cursor.lastrowid

                filename = (
                    f"request_{request_id}{suffix}"
                )

                receipt_path = upload_root / filename

                receipt_path.write_bytes(
                    receipt_bytes
                )

                db.execute("""
                    UPDATE premium_requests
                    SET receipt_path = ?
                    WHERE id = ?
                """, (
                    str(receipt_path),
                    request_id
                ))

            return json_response(self, {
                "ok": True,
                "message": (
                    "Premium request submitted. "
                    "Waiting for owner approval."
                ),
                "request_id": request_id
            })

        except (ValueError, TypeError):
            return json_response(self, {
                "ok": False,
                "error": "Invalid premium request"
            }, 400)

        except json.JSONDecodeError:
            return json_response(self, {
                "ok": False,
                "error": "Invalid JSON"
            }, 400)

        except Exception as e:
            return json_response(self, {
                "ok": False,
                "error": str(e)
            }, 500)


    def cards(self):
        try:
            with get_db() as db:
                rows = db.execute("""
                    SELECT
                        id,
                        card_code,
                        name,
                        rarity,
                        image_path,
                        is_active
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
                        id DESC
                """).fetchall()

            return json_response(self, {
                "ok": True,
                "cards": [dict(row) for row in rows]
            })

        except Exception as e:
            return json_response(self, {
                "ok": False,
                "error": str(e)
            }, 500)

    def active_drop(self):
        try:
            now = datetime.now(timezone.utc).isoformat()

            with get_db() as db:
                db.execute("""
                    UPDATE drops
                    SET status = 'expired'
                    WHERE status = 'active'
                      AND expires_at <= ?
                """, (now,))

                row = db.execute("""
                    SELECT
                        d.id,
                        d.card_id,
                        d.started_at,
                        d.expires_at,
                        d.status,
                        c.card_code,
                        c.name,
                        c.rarity,
                        c.image_path
                    FROM drops d
                    JOIN cards c ON c.id = d.card_id
                    WHERE d.status = 'active'
                    ORDER BY d.id DESC
                    LIMIT 1
                """).fetchone()

            return json_response(self, {
                "ok": True,
                "drop": dict(row) if row else None
            })

        except Exception as e:
            return json_response(self, {
                "ok": False,
                "error": str(e)
            }, 500)

    def stats(self):
        try:
            with get_db() as db:
                cards = db.execute(
                    "SELECT COUNT(*) AS n FROM cards WHERE is_active = 1"
                ).fetchone()["n"]

                users = db.execute(
                    "SELECT COUNT(*) AS n FROM users"
                ).fetchone()["n"]

                drops = db.execute(
                    "SELECT COUNT(*) AS n FROM drops"
                ).fetchone()["n"]

                caught = db.execute(
                    "SELECT COUNT(*) AS n FROM drops WHERE status = 'caught'"
                ).fetchone()["n"]

            return json_response(self, {
                "ok": True,
                "stats": {
                    "cards": cards,
                    "users": users,
                    "drops": drops,
                    "caught": caught
                }
            })

        except Exception as e:
            return json_response(self, {
                "ok": False,
                "error": str(e)
            }, 500)

    def asset_file(self, url_path):
        relative = url_path.removeprefix("/assets/")

        # Prevent path traversal.
        requested = (BASE_DIR / "assets" / relative).resolve()
        assets_root = (BASE_DIR / "assets").resolve()

        if not str(requested).startswith(str(assets_root) + "/"):
            return json_response(self, {
                "ok": False,
                "error": "Invalid asset path"
            }, 403)

        if not requested.is_file():
            return json_response(self, {
                "ok": False,
                "error": "Asset not found"
            }, 404)

        content = requested.read_bytes()

        content_types = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".gif": "image/gif",
            ".svg": "image/svg+xml",
        }

        content_type = content_types.get(
            requested.suffix.lower(),
            "application/octet-stream"
        )

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def static_file(self, filename):
        file = WEB_DIR / filename

        if not file.exists():
            return json_response(self, {
                "ok": False,
                "error": f"{filename} not found"
            }, 404)

        content = file.read_bytes()

        content_type = {
            ".html": "text/html; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
        }.get(file.suffix, "application/octet-stream")

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


def main():
    init_db()
    init_drop_settings()
    run_drop_scheduler()

    host = "0.0.0.0"
    port = int(os.getenv("PORT", "8080"))

    print("=" * 45)
    print("       MYTHIC CARD WEB SERVER")
    print("=" * 45)
    print(f"DB  : {DB_PATH}")
    print(f"WEB : {WEB_DIR}")
    print(f"URL : http://{host}:{port}")
    print("=" * 45)

    server = ThreadingHTTPServer((host, port), Handler)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 WEB SERVER STOPPED")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
