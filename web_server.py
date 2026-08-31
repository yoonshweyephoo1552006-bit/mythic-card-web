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



def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(DB_PATH) as db:
        db.execute("PRAGMA foreign_keys = ON")

        schema_path = BASE_DIR / "database" / "schema.sql"
        if schema_path.exists():
            db.executescript(
                schema_path.read_text(encoding="utf-8")
            )

        card_image = BASE_DIR / "assets" / "cards" / "legendary" / "CARD-0001.jpg"

        if card_image.exists():
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


def get_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    schema_path = BASE_DIR / "database" / "schema.sql"
    if schema_path.exists():
        db.executescript(schema_path.read_text(encoding="utf-8"))
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


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
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
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

        if path == "/api/premium/request":
            return self.premium_request()

        return json_response(self, {
            "ok": False,
            "error": "Not found"
        }, 404)


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
            expires = now + timedelta(minutes=10)

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
        Read Telegram initData from ?initData=...
        and return the local DB user.
        """
        query = parse_qsl(
            urlparse(self.path).query,
            keep_blank_values=True
        )

        params = dict(query)
        init_data = params.get("initData", "")

        telegram_user, error = self.verify_telegram_init_data(init_data)

        if error:
            return None, error

        telegram_id = int(telegram_user["id"])

        with get_db() as db:
            row = db.execute("""
                SELECT *
                FROM users
                WHERE telegram_id = ?
            """, (telegram_id,)).fetchone()

        if not row:
            return None, "Telegram user is not registered"

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
                        t.created_at
                    FROM trades t
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

            if length <= 0 or length > 100_000:
                return json_response(self, {
                    "ok": False,
                    "error": "Invalid request body"
                }, 400)

            raw = self.rfile.read(length)
            payload = json.loads(raw.decode("utf-8"))

            init_data = payload.get("initData", "")
            amount_mmk = int(payload.get("amount_mmk", 0))

            if amount_mmk <= 0:
                return json_response(self, {
                    "ok": False,
                    "error": "Invalid premium amount"
                }, 400)

            telegram_user, error = self.verify_telegram_init_data(
                init_data
            )

            if error:
                return json_response(self, {
                    "ok": False,
                    "error": error
                }, 401)

            telegram_id = int(telegram_user["id"])

            with get_db() as db:
                user = db.execute("""
                    SELECT id
                    FROM users
                    WHERE telegram_id = ?
                """, (telegram_id,)).fetchone()

                if not user:
                    return json_response(self, {
                        "ok": False,
                        "error": "User is not registered"
                    }, 401)

                cursor = db.execute("""
                    INSERT INTO premium_requests(
                        user_id,
                        amount_mmk,
                        requested_days,
                        status
                    )
                    VALUES (?, ?, NULL, 'pending')
                """, (
                    user["id"],
                    amount_mmk
                ))

                request_id = cursor.lastrowid

            return json_response(self, {
                "ok": True,
                "message": "Premium request submitted",
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
