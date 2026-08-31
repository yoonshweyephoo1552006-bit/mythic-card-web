const API_BASE = 'https://mythic-card-web-production.up.railway.app';
const tg = window.Telegram?.WebApp;
const ASSET_BASE = 'https://yoonshweyephoo1552006-bit.github.io/mythic-card-web/';

if (tg) {
    tg.ready();
    tg.expand();
}

const user = tg?.initDataUnsafe?.user || null;

let activeDrop = null;
let timerInterval = null;

function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

function showMessage(message) {
    if (tg) {
        tg.showAlert(message);
    } else {
        alert(message);
    }
}

/* -----------------------------
   Telegram user
----------------------------- */

function loadTelegramUser() {
    if (!user) return;

    const name =
        user.first_name ||
        user.username ||
        "Player";

    setText("user-name", name);
    setText("profile-name", name);
    setText("profile-id", `Telegram ID: ${user.id}`);
}


/* -----------------------------
   Timer
----------------------------- */

function formatRemaining(ms) {
    if (ms <= 0) return "00:00:00";

    const total = Math.floor(ms / 1000);

    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = total % 60;

    return [h, m, s]
        .map(v => String(v).padStart(2, "0"))
        .join(":");
}

function updateDropTimer() {
    const timer = document.getElementById("timer");

    if (!timer) return;

    if (!activeDrop) {
        timer.textContent = "--:--:--";
        return;
    }

    const expires =
        new Date(activeDrop.expires_at).getTime();

    const remaining = expires - Date.now();

    if (remaining <= 0) {
        timer.textContent = "EXPIRED";

        const button =
            document.getElementById("catch-btn");

        if (button) {
            button.disabled = true;
            button.textContent = "⏰ EXPIRED";
        }

        return;
    }

    timer.textContent = formatRemaining(remaining);
}


/* -----------------------------
   Active Drop
----------------------------- */

function renderDrop(drop) {
    activeDrop = drop;

    const rarityEl =
        document.querySelector(".hero .rarity");

    const nameEl =
        document.querySelector(".hero .card-name");

    const frameEl =
        document.querySelector(".hero .card-frame");

    const button =
        document.getElementById("catch-btn");

    if (!drop) {
        if (rarityEl) {
            rarityEl.textContent = "NO ACTIVE DROP";
        }

        if (nameEl) {
            nameEl.textContent = "Come back later";
        }

        if (frameEl) {
            frameEl.innerHTML =
                '<div class="card-placeholder">🃏</div>';
        }

        if (button) {
            button.disabled = true;
            button.textContent = "⏰ NO DROP";
        }

        updateDropTimer();
        return;
    }

    if (rarityEl) {
        rarityEl.textContent =
            String(drop.rarity || "")
                .toUpperCase();
    }

    if (nameEl) {
        nameEl.textContent =
            drop.name || drop.card_code || "Unknown Card";
    }

    if (frameEl) {
        if (drop.image_path) {
            frameEl.innerHTML =
                `<img src="${ASSET_BASE}${drop.image_path}" alt="Card">`;
        } else {
            frameEl.innerHTML =
                '<div class="card-placeholder">🃏</div>';
        }
    }

    if (button) {
        const expires =
            new Date(drop.expires_at).getTime();

        if (expires > Date.now()) {
            button.disabled = false;
            button.textContent = "⚡ CATCH";
        } else {
            button.disabled = true;
            button.textContent = "⏰ EXPIRED";
        }
    }

    updateDropTimer();
}


/* -----------------------------
   Drop API
----------------------------- */

async function loadDrop() {
    try {
        const response = await fetch(API_BASE + "/api/drop", {
            cache: "no-store"
        });

        const data = await response.json();

        if (!data.ok) {
            throw new Error(
                data.error || "Drop API error"
            );
        }

        renderDrop(data.drop);

    } catch (error) {
        console.error("Drop API:", error);
    }
}


/* -----------------------------
   Catch API
----------------------------- */

async function catchCard() {
    const button =
        document.getElementById("catch-btn");

    if (!activeDrop) {
        showMessage("❌ No active drop.");
        return;
    }

    const expires =
        new Date(activeDrop.expires_at).getTime();

    if (expires <= Date.now()) {
        showMessage("⏰ This drop has expired.");
        await loadDrop();
        return;
    }

    const initData = tg?.initData;

    if (!initData) {
        showMessage(
            "⚠️ Please open Mythic Card from Telegram."
        );
        return;
    }

    if (button) {
        button.disabled = true;
        button.textContent = "🎯 CATCHING...";
    }

    try {
        const response = await fetch(API_BASE + "/api/catch", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                initData: initData
            })
        });

        const data = await response.json();

        if (!data.ok) {
            showMessage(
                "❌ " +
                (data.error || "Catch failed.")
            );

            await loadDrop();
            return;
        }

        showMessage(
            "🎉 CARD CAUGHT!\n\n" +
            "🃏 " + data.drop.name + "\n" +
            "🏷️ " + data.drop.rarity
        );

        activeDrop = null;

        if (button) {
            button.disabled = true;
            button.textContent = "✅ CAUGHT";
        }

        await loadDrop();
        await loadStats();
        await loadCards();

    } catch (error) {
        console.error("Catch API:", error);

        showMessage(
            "❌ Connection error. Please try again."
        );

        if (button) {
            button.disabled = false;
            button.textContent = "⚡ CATCH";
        }
    }
}


/* -----------------------------
   Stats
----------------------------- */

async function loadStats() {
    try {
        const response = await fetch(API_BASE + "/api/stats", {
            cache: "no-store"
        });

        const data = await response.json();

        if (!data.ok) {
            throw new Error(
                data.error || "Stats API error"
            );
        }

        // "total-cards" is the global card catalog count.
        // User-owned total is handled separately by loadCollection().

    } catch (error) {
        console.error("Stats API:", error);
    }
}


/* -----------------------------
   Card list
----------------------------- */

async function loadCards() {
    try {
        const response = await fetch(API_BASE + "/api/cards", {
            cache: "no-store"
        });

        const data = await response.json();

        if (!data.ok) {
            throw new Error(
                data.error || "Cards API error"
            );
        }

        console.log(
            "MYTHIC CARD DATABASE:",
            data.cards
        );

    } catch (error) {
        console.error("Cards API:", error);
    }
}



/* -----------------------------
   Authenticated API
----------------------------- */

function getInitData() {
    return tg?.initData || "";
}

async function apiFetch(path, options = {}) {
    const initData = getInitData();

    const headers = {
        ...(options.headers || {})
    };

    if (initData) {
        headers["X-Telegram-Init-Data"] = initData;
    }

    const response = await fetch(path, {
        cache: "no-store",
        ...options,
        headers
    });

    const data = await response.json();

    if (!response.ok || !data.ok) {
        throw new Error(data.error || `API error ${response.status}`);
    }

    return data;
}


/* -----------------------------
   Profile API
----------------------------- */

async function loadMe() {
    try {
        const data = await apiFetch(API_BASE + "/api/me");

        const u = data.user || {};

        const name =
            u.first_name ||
            u.username ||
            "Player";

        setText("user-name", name);
        setText("profile-name", name);
        setText(
            "profile-id",
            u.telegram_id
                ? `Telegram ID: ${u.telegram_id}`
                : "Telegram ID: —"
        );

        const premiumEl =
            document.getElementById("profile-premium");

        if (premiumEl) {
            premiumEl.textContent =
                u.is_premium
                    ? `⭐ Premium until ${u.premium_until || "—"}`
                    : "Free Player";
        }

    } catch (error) {
        console.error("Me API:", error);
    }
}


/* -----------------------------
   Collection API
----------------------------- */

async function loadCollection() {
    try {
        const data = await apiFetch(API_BASE + "/api/collection");

        const cards = data.cards || [];

        const list =
            document.getElementById("collection-list");

        const empty =
            document.getElementById("collection-empty");

        if (!list) return;

        list.innerHTML = "";

        if (!cards.length) {
            if (empty) empty.style.display = "block";
            setText("total-cards", 0);
            return;
        }

        if (empty) empty.style.display = "none";

        for (const card of cards) {
            const item = document.createElement("div");
            item.className = "collection-item";

            const image = card.image_path
                ? `<img src="${ASSET_BASE}${card.image_path}" alt="">`
                : `<div class="collection-placeholder">🃏</div>`;

            item.innerHTML = `
                <div class="collection-image">
                    ${image}
                </div>
                <div class="collection-info">
                    <strong>${card.name || card.card_code || "Card"}</strong>
                    <span>${String(card.rarity || "").toUpperCase()}</span>
                    <small>×${card.quantity || 0}</small>
                </div>
            `;

            list.appendChild(item);
        }

        const totalOwned = cards.reduce(
            (sum, card) => sum + Number(card.quantity || 0),
            0
        );

        setText("total-cards", totalOwned);

    } catch (error) {
        console.error("Collection API:", error);
    }
}


/* -----------------------------
   Premium API
----------------------------- */

async function loadPremium() {
    try {
        const data = await apiFetch(API_BASE + "/api/premium");

        const premium = data.premium || {};
        const requests = data.requests || [];

        const status =
            document.getElementById("premium-status");

        if (status) {
            status.textContent =
                premium.is_premium
                    ? `⭐ PREMIUM ACTIVE`
                    : `FREE ACCOUNT`;
        }

        const until =
            document.getElementById("premium-until");

        if (until) {
            until.textContent =
                premium.is_premium
                    ? `Until: ${premium.premium_until || "—"}`
                    : "Premium not active";
        }

        const requestList =
            document.getElementById("premium-requests");

        if (requestList) {
            requestList.innerHTML = "";

            for (const request of requests) {
                const item = document.createElement("div");
                item.className = "premium-request";

                item.innerHTML = `
                    <strong>#${request.id}</strong>
                    <span>${request.amount_mmk || 0} MMK</span>
                    <small>${request.status || "pending"}</small>
                `;

                requestList.appendChild(item);
            }
        }

    } catch (error) {
        console.error("Premium API:", error);
    }
}


/* -----------------------------
   Events API
----------------------------- */

async function loadEvents() {
    try {
        const data = await fetch(API_BASE + "/api/events", {
            cache: "no-store"
        }).then(r => r.json());

        if (!data.ok) {
            throw new Error(data.error || "Events API error");
        }

        const list =
            document.getElementById("events-list");

        if (!list) return;

        list.innerHTML = "";

        const events = data.events || [];

        if (!events.length) {
            list.innerHTML =
                '<div class="empty-mini">No events yet.</div>';
            return;
        }

        for (const event of events) {
            const item = document.createElement("div");
            item.className = "event-item";

            item.innerHTML = `
                <strong>${event.name || "Event"}</strong>
                <span>${event.players || 0}/${event.max_players || 0} players</span>
                <small>${event.status || ""}</small>
            `;

            list.appendChild(item);
        }

    } catch (error) {
        console.error("Events API:", error);
    }
}


/* -----------------------------
   Battles API
----------------------------- */

async function loadBattles() {
    try {
        const data = await apiFetch(API_BASE + "/api/battles");

        const list =
            document.getElementById("battles-list");

        if (!list) return;

        list.innerHTML = "";

        const battles = data.battles || [];

        if (!battles.length) {
            list.innerHTML =
                '<div class="empty-mini">No battles yet.</div>';
            return;
        }

        for (const battle of battles) {
            const item = document.createElement("div");
            item.className = "battle-item";

            item.innerHTML = `
                <strong>Battle #${battle.id}</strong>
                <span>${battle.status || "unknown"}</span>
                <small>Winner: ${battle.winner_user_id || "—"}</small>
            `;

            list.appendChild(item);
        }

    } catch (error) {
        console.error("Battles API:", error);
    }
}


/* -----------------------------
   Trades API
----------------------------- */

async function loadTrades() {
    try {
        const data = await apiFetch(API_BASE + "/api/trades");

        const list =
            document.getElementById("trades-list");

        if (!list) return;

        list.innerHTML = "";

        const trades = data.trades || [];

        if (!trades.length) {
            list.innerHTML =
                '<div class="empty-mini">No trades yet.</div>';
            return;
        }

        for (const trade of trades) {
            const item = document.createElement("div");
            item.className = "trade-item";

            item.innerHTML = `
                <strong>Trade #${trade.id}</strong>
                <span>${trade.status || "unknown"}</span>
                <small>${trade.created_at || ""}</small>
            `;

            list.appendChild(item);
        }

    } catch (error) {
        console.error("Trades API:", error);
    }
}


/* -----------------------------
   Dashboard refresh
----------------------------- */

async function loadUserData() {
    if (!getInitData()) {
        console.warn(
            "Telegram initData unavailable. Open from Telegram."
        );
        return;
    }

    await Promise.allSettled([
        loadMe(),
        loadCollection(),
        loadPremium(),
        loadBattles(),
        loadTrades()
    ]);
}


/* -----------------------------
   Navigation
----------------------------- */

document.querySelectorAll(".nav-btn").forEach((button) => {
    button.addEventListener("click", () => {
        const target = button.dataset.screen;

        document.querySelectorAll(".screen").forEach((screen) => {
            screen.classList.toggle(
                "active",
                screen.id === target
            );
        });

        document.querySelectorAll(".nav-btn").forEach((btn) => {
            btn.classList.toggle(
                "active",
                btn === button
            );
        });
    });
});


/* -----------------------------
   Catch button
----------------------------- */

document.getElementById("catch-btn")
    ?.addEventListener("click", catchCard);


/* -----------------------------
   Start
----------------------------- */

loadTelegramUser();
loadDrop();
loadStats();
loadCards();
loadUserData();
loadEvents();

updateDropTimer();

timerInterval = setInterval(() => {
    updateDropTimer();
}, 1000);

setInterval(() => {
    loadDrop();
    loadStats();
    loadUserData();
}, 10000);
