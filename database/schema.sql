PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL UNIQUE,
    username TEXT,
    first_name TEXT,
    is_owner INTEGER NOT NULL DEFAULT 0,
    is_premium INTEGER NOT NULL DEFAULT 0,
    premium_until TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    rarity TEXT NOT NULL CHECK (
        rarity IN ('common','uncommon','rare','epic','legendary','mythic')
    ),
    image_path TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS collections (
    user_id INTEGER NOT NULL,
    card_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0),
    first_obtained_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, card_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (card_id) REFERENCES cards(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS drops (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    winner_user_id INTEGER,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active','caught','expired','cancelled')),
    FOREIGN KEY (card_id) REFERENCES cards(id),
    FOREIGN KEY (winner_user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS premium_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    amount_mmk INTEGER NOT NULL,
    requested_days INTEGER,
    payment_method TEXT,
    receipt_path TEXT,
    receipt_note TEXT,
    admin_note TEXT,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','approved','rejected')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processed_at TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_user_id INTEGER NOT NULL,
    to_user_id INTEGER NOT NULL,
    offered_card_id INTEGER NOT NULL,
    requested_card_id INTEGER,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','accepted','rejected','cancelled')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (from_user_id) REFERENCES users(id),
    FOREIGN KEY (to_user_id) REFERENCES users(id),
    FOREIGN KEY (offered_card_id) REFERENCES cards(id),
    FOREIGN KEY (requested_card_id) REFERENCES cards(id)
);

CREATE TABLE IF NOT EXISTS battles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    challenger_id INTEGER NOT NULL,
    opponent_id INTEGER NOT NULL,
    challenger_card_id INTEGER,
    opponent_card_id INTEGER,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','accepted','active','completed','cancelled')),
    winner_user_id INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (challenger_id) REFERENCES users(id),
    FOREIGN KEY (opponent_id) REFERENCES users(id),
    FOREIGN KEY (challenger_card_id) REFERENCES cards(id),
    FOREIGN KEY (opponent_card_id) REFERENCES cards(id),
    FOREIGN KEY (winner_user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    max_players INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'waiting'
        CHECK (status IN ('waiting','active','completed','cancelled')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS event_players (
    event_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (event_id, user_id),
    FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS rewards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    reward_type TEXT NOT NULL,
    reward_value TEXT NOT NULL,
    source TEXT NOT NULL,
    claimed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, reward_type, source),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

INSERT OR IGNORE INTO app_settings(key, value)
VALUES ('bot_enabled', '0');

INSERT OR IGNORE INTO app_settings(key, value)
VALUES ('monthly_epic_claimed', '0');
