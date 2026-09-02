const API_BASE =
    (window.location.hostname === "127.0.0.1" ||
     window.location.hostname === "localhost")
        ? ""
        : "https://mythic-card-web-production.up.railway.app";
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
    setText(
        "profile-username",
        user.username ? `@${user.username}` : "@username"
    );
    setText("profile-id", `Telegram ID: ${user.id}`);

    const avatar = document.getElementById("profile-avatar");
    const fallback = document.getElementById("profile-avatar-fallback");

    if (avatar && fallback && user.photo_url) {
        avatar.src = user.photo_url;

        avatar.onload = () => {
            avatar.style.display = "block";
            fallback.style.display = "none";
        };

        avatar.onerror = () => {
            avatar.style.display = "none";
            fallback.style.display = "grid";
        };
    }

    const profileFrame =
        document.getElementById("profile-frame");

    const ownerBadge =
        document.getElementById("profile-owner-badge");

    if (profileFrame && user.id === 5599773708) {
        profileFrame.classList.remove(
            "free-frame",
            "premium-frame"
        );
        profileFrame.classList.add("owner-frame");
    }

    if (ownerBadge && user.id === 5599773708) {
        ownerBadge.classList.add("show");
    }
}


/* -----------------------------
   Timer
----------------------------- */

function formatRemaining(ms) {
    if (ms <= 0) return "00:00";

    const total = Math.floor(ms / 1000);
    const m = Math.floor(total / 60);
    const s = total % 60;

    return [m, s]
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


    const frameEl =
        document.querySelector(".hero .card-frame");

    const button =
        document.getElementById("catch-btn");

    const input =
        document.getElementById("catch-input");

    if (!drop) {
        if (rarityEl) {
            rarityEl.textContent = "NO ACTIVE DROP";
        }

        if (frameEl) {
            frameEl.innerHTML =
                '<div class="card-placeholder">🃏</div>';
        }

        if (input) {
            input.value = "";
            input.disabled = true;
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
            if (input) {
                input.disabled = false;
            }

            button.disabled = false;
            button.textContent = "⚡ CATCH";
        } else {
            if (input) {
                input.disabled = true;
            }
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

    const input =
        document.getElementById("catch-input");

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

    const catchName =
        input?.value?.trim() || "";

    if (!catchName) {
        showMessage(
            "✍️ Type the card name first."
        );

        input?.focus();
        return;
    }

    if (button) {
        button.disabled = true;
        button.textContent = "🎯 CHECKING...";
    }

    if (input) {
        input.disabled = true;
    }

    try {
        const response = await fetch(API_BASE + "/api/catch", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                initData: initData,
                catch_name: catchName
            })
        });

        const data = await response.json();

        if (!data.ok) {
            showMessage(
                "❌ " +
                (data.error || "Wrong card name.")
            );

            if (input) {
                input.disabled = false;
                input.focus();
            }

            if (button) {
                button.disabled = false;
                button.textContent = "⚡ CATCH";
            }

            return;
        }

        showMessage(
            "🎉 CARD CAUGHT!\n\n" +
            "🃏 " + data.drop.name + "\n" +
            "🏷️ " + data.drop.rarity
        );

        activeDrop = null;

        if (input) {
            input.value = "";
            input.disabled = true;
        }

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

        if (input) {
            input.disabled = false;
        }

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

        setText(
            "total-cards",
            data.stats.cards ?? 0
        );

    } catch (error) {
        console.error("Stats API:", error);
    }
}


/* -----------------------------
   Card list
----------------------------- */

let allCards = [];

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

        allCards = Array.isArray(data.cards)
            ? data.cards
            : [];

        renderGallery();

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

    let response;

    try {
        response = await fetch(path, {
            cache: "no-store",
            ...options,
            headers
        });
    } catch (error) {
        console.error("API network error:", path, error);
        throw new Error(
            `Network error while contacting API: ${error.message || "Failed to fetch"}`
        );
    }

    const text = await response.text();

    let data;

    try {
        data = JSON.parse(text);
    } catch (error) {
        console.error(
            "API invalid JSON:",
            path,
            response.status,
            text
        );

        throw new Error(
            `Server returned invalid response (${response.status})`
        );
    }

    if (!response.ok || !data.ok) {
        console.error(
            "API error:",
            path,
            response.status,
            data
        );

        throw new Error(
            data.error || `API error ${response.status}`
        );
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

        const profileFrame =
            document.getElementById("profile-frame");

        const premiumBadge =
            document.getElementById("profile-premium-badge");

        const ownerBadge =
            document.getElementById("profile-owner-badge");

        if (profileFrame) {
            profileFrame.classList.remove(
                "free-frame",
                "premium-frame",
                "owner-frame"
            );

            if (u.is_owner) {
                profileFrame.classList.add("owner-frame");
            } else if (u.is_premium) {
                profileFrame.classList.add("premium-frame");
            } else {
                profileFrame.classList.add("free-frame");
            }
        }

        if (premiumBadge) {
            premiumBadge.classList.toggle(
                "show",
                Boolean(u.is_premium)
            );
        }

        if (ownerBadge) {
            ownerBadge.classList.toggle(
                "show",
                Boolean(u.is_owner)
            );
        }

    } catch (error) {
        console.error("Me API:", error);
    }
}


/* -----------------------------
   Collection API
----------------------------- */

let collectionCards = [];
let activeRarityFilter = "all";
let galleryMode = "all";

function getCardRarity(card) {
    return String(card?.rarity || "common").toLowerCase();
}

function getMyQuantity(card) {
    const owned = collectionCards.find(
        item => Number(item.id) === Number(card.id)
    );

    return Number(owned?.quantity || 0);
}

function getMythicEffect(rarity, index) {
    if (rarity === "mythic") {
        const effects = [
            "mythic-cosmic",
            "mythic-fire",
            "mythic-void",
            "mythic-arcane",
            "mythic-storm",
            "mythic-divine"
        ];

        return effects[index % effects.length];
    }

    if (rarity === "legendary") {
        return "legendary-effect";
    }

    return "normal-effect";
}

function updateCollectionStats(cards) {
    const total = cards.reduce(
        (sum, card) => sum + Number(card.quantity || 0),
        0
    );

    const legendary = cards
        .filter(card => getCardRarity(card) === "legendary")
        .reduce(
            (sum, card) => sum + Number(card.quantity || 0),
            0
        );

    const mythic = cards
        .filter(card => getCardRarity(card) === "mythic")
        .reduce(
            (sum, card) => sum + Number(card.quantity || 0),
            0
        );

    setText("total-cards", total);
    setText("legendary-count", legendary);
    setText("mythic-count", mythic);

    const progress =
        document.getElementById("collection-progress");

    if (progress) {
        const uniqueOwned = cards.length;

        progress.textContent =
            `${uniqueOwned} / ${allCards.length} UNIQUE`;
    }
}

function openCardGallery(card) {
    const modal =
        document.getElementById("card-modal");

    const imageBox =
        document.getElementById("card-modal-image");

    const nameBox =
        document.getElementById("card-modal-name");

    const codeBox =
        document.getElementById("card-modal-code");

    const rarityBox =
        document.getElementById("card-modal-rarity");

    if (!modal) return;

    const rarity = getCardRarity(card);
    const quantity = getMyQuantity(card);

    if (rarityBox) {
        rarityBox.textContent =
            rarity.toUpperCase();

        rarityBox.className =
            "modal-rarity " + rarity;
    }

    if (nameBox) {
        nameBox.textContent =
            card.name ||
            card.card_code ||
            "Mythic Card";
    }

    if (codeBox) {
        codeBox.textContent =
            `${card.card_code || "UNKNOWN"} • ${
                quantity > 0
                    ? `OWNED ×${quantity}`
                    : "MISSING"
            }`;
    }

    if (imageBox) {
        if (card.image_path) {
            imageBox.innerHTML = `
                <div class="modal-card-aura ${rarity}"></div>
                <img
                    src="${ASSET_BASE}${card.image_path}"
                    alt=""
                >
            `;
        } else {
            imageBox.innerHTML =
                `<div class="modal-card-placeholder">🃏</div>`;
        }
    }

    modal.classList.add("show");
    document.body.classList.add("modal-open");
}

function closeCardGallery() {
    const modal =
        document.getElementById("card-modal");

    if (!modal) return;

    modal.classList.remove("show");
    document.body.classList.remove("modal-open");
}

function renderGallery() {
    const list =
        document.getElementById("collection-list");

    const empty =
        document.getElementById("collection-empty");

    if (!list) return;

    updateCollectionStats(collectionCards);

    let cards = [...allCards];

    if (
        galleryMode === "my" ||
        galleryMode === "owned"
    ) {
        cards = cards.filter(
            card => getMyQuantity(card) > 0
        );
    }

    if (galleryMode === "missing") {
        cards = cards.filter(
            card => getMyQuantity(card) <= 0
        );
    }

    if (activeRarityFilter !== "all") {
        cards = cards.filter(
            card =>
                getCardRarity(card) ===
                activeRarityFilter
        );
    }

    list.innerHTML = "";

    if (!cards.length) {
        if (empty) {
            empty.style.display = "block";

            const title =
                empty.querySelector("h3");

            const text =
                empty.querySelector("p");

            if (title) {
                title.textContent =
                    galleryMode === "missing"
                        ? "Collection Complete"
                        : "No Cards Found";
            }

            if (text) {
                text.textContent =
                    galleryMode === "missing"
                        ? "You own every card in this filter."
                        : "No cards match this filter.";
            }
        }

        return;
    }

    if (empty) {
        empty.style.display = "none";
    }

    cards.forEach((card, index) => {
        const rarity =
            getCardRarity(card);

        const quantity =
            getMyQuantity(card);

        const owned =
            quantity > 0;

        const effect =
            getMythicEffect(
                rarity,
                index
            );

        const item =
            document.createElement("button");

        item.type = "button";

        item.className =
            `collection-item ${rarity}-card ${effect} ${
                owned
                    ? "owned"
                    : "missing"
            }`;

        item.innerHTML = `
            <div class="collection-image">
                <div class="card-energy"></div>

                ${
                    card.image_path
                        ? `<img
                             src="${ASSET_BASE}${card.image_path}"
                             alt=""
                           >`
                        : `<div class="collection-placeholder">🃏</div>`
                }

                ${
                    owned
                        ? `<div class="owned-badge">✓ OWNED</div>`
                        : `<div class="missing-badge">MISSING</div>`
                }

                <div class="card-shine"></div>
                <div class="card-corners"></div>
            </div>

            <div class="collection-info">
                <strong>
                    ${card.name || card.card_code || "Card"}
                </strong>

                <span>
                    ${rarity.toUpperCase()}
                </span>

                <small>
                    ${
                        owned
                            ? `OWNED ×${quantity}`
                            : "NOT COLLECTED"
                    }
                </small>
            </div>
        `;

        item.addEventListener(
            "click",
            () => openCardGallery(card)
        );

        list.appendChild(item);
    });
}

function setGalleryMode(mode, button) {
    galleryMode = mode;

    document
        .querySelectorAll(".gallery-mode")
        .forEach(btn => {
            btn.classList.toggle(
                "active",
                btn === button
            );
        });

    renderGallery();
}

async function loadCollection() {
    try {
        const data =
            await apiFetch(
                API_BASE + "/api/collection"
            );

        collectionCards =
            Array.isArray(data.cards)
                ? data.cards
                : [];

        renderGallery();

    } catch (error) {
        console.error(
            "Collection API:",
            error
        );
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
   Premium Purchase
----------------------------- */

function setPremiumSubmitStatus(message, isError = false) {
    const el = document.getElementById(
        "premium-submit-status"
    );

    if (!el) return;

    el.textContent = message;
    el.classList.toggle("error", Boolean(isError));
}


function fileToDataUrl(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();

        reader.onload = () => resolve(reader.result);
        reader.onerror = () => reject(
            new Error("Could not read receipt")
        );

        reader.readAsDataURL(file);
    });
}


async function submitPremiumRequest() {
    const amountEl =
        document.getElementById("premium-amount");

    const methodEl =
        document.getElementById("premium-payment-method");

    const receiptEl =
        document.getElementById("premium-receipt");

    const noteEl =
        document.getElementById("premium-note");

    const button =
        document.getElementById("premium-submit");

    const amount = Number(
        amountEl?.value || 0
    );

    const paymentMethod =
        methodEl?.value || "";

    const file =
        receiptEl?.files?.[0];

    const note =
        noteEl?.value?.trim() || "";

    if (!amount || amount <= 0) {
        setPremiumSubmitStatus(
            "❌ Please enter a valid amount.",
            true
        );
        return;
    }

    if (!paymentMethod) {
        setPremiumSubmitStatus(
            "❌ Please select a payment method.",
            true
        );
        return;
    }

    if (!file) {
        setPremiumSubmitStatus(
            "❌ Please upload your payment receipt.",
            true
        );
        return;
    }

    const allowedTypes = [
        "image/jpeg",
        "image/png",
        "image/webp"
    ];

    if (!allowedTypes.includes(file.type)) {
        setPremiumSubmitStatus(
            "❌ Receipt must be JPG, PNG or WEBP.",
            true
        );
        return;
    }

    if (file.size > 3 * 1024 * 1024) {
        setPremiumSubmitStatus(
            "❌ Receipt must be smaller than 3 MB.",
            true
        );
        return;
    }

    try {
        if (button) {
            button.disabled = true;
            button.textContent = "⏳ Submitting...";
        }

        setPremiumSubmitStatus(
            "Uploading receipt..."
        );

        const receiptData =
            await fileToDataUrl(file);

        const data = await apiFetch(
            API_BASE + "/api/premium/request",
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    amount_mmk: Math.floor(amount),
                    payment_method: paymentMethod,
                    receipt_note: note,
                    receipt_data: receiptData,
                    receipt_name: file.name
                })
            }
        );

        setPremiumSubmitStatus(
            `✅ Request #${data.request_id} submitted. Waiting for owner approval.`
        );

        if (amountEl) amountEl.value = "";
        if (methodEl) methodEl.value = "";
        if (receiptEl) receiptEl.value = "";
        if (noteEl) noteEl.value = "";

        await loadPremium();

    } catch (error) {
        console.error(
            "Premium request:",
            error
        );

        setPremiumSubmitStatus(
            `❌ ${error.message || "Submission failed"}`,
            true
        );

    } finally {
        if (button) {
            button.disabled = false;
            button.textContent =
                "📤 Submit Premium Request";
        }
    }
}


function setupPremiumPurchase() {
    const button =
        document.getElementById(
            "premium-submit"
        );

    if (!button) return;

    button.addEventListener(
        "click",
        submitPremiumRequest
    );
}


/* -----------------------------
   Premium Admin
----------------------------- */

function isCurrentOwner() {
    return Boolean(
        user &&
        Number(user.id) === 5599773708
    );
}


function setPremiumAdminStatus(message, isError = false) {
    const el = document.getElementById(
        "premium-admin-status"
    );

    if (!el) return;

    el.textContent = message;
    el.classList.toggle(
        "error",
        Boolean(isError)
    );
}


async function loadPremiumAdmin() {
    const panel =
        document.getElementById(
            "premium-admin-panel"
        );

    const list =
        document.getElementById(
            "premium-admin-requests"
        );

    if (!panel || !list) return;

    if (!isCurrentOwner()) {
        panel.style.display = "none";
        return;
    }

    panel.style.display = "block";

    try {
        const data = await apiFetch(
            API_BASE + "/api/admin/premium"
        );

        const requests =
            data.requests || [];

        list.innerHTML = "";

        if (!requests.length) {
            list.innerHTML =
                '<div class="empty-mini">No premium requests.</div>';
            return;
        }

        for (const request of requests) {
            const item =
                document.createElement("div");

            item.className =
                "premium-admin-request";

            const status =
                String(
                    request.status || "pending"
                ).toLowerCase();

            item.innerHTML = `
                <div class="premium-admin-head">
                    <strong>
                        #${request.id}
                    </strong>
                    <span class="premium-admin-status ${status}">
                        ${status.toUpperCase()}
                    </span>
                </div>

                <div class="premium-admin-user">
                    👤 ${escapeHtml(
                        request.first_name ||
                        request.username ||
                        "User"
                    )}
                </div>

                <div class="premium-admin-info">
                    <div>🆔 ${request.telegram_id}</div>
                    <div>💰 ${request.amount_mmk || 0} MMK</div>
                    <div>💳 ${escapeHtml(
                        request.payment_method || "—"
                    )}</div>
                    <div>📝 ${escapeHtml(
                        request.receipt_note || "—"
                    )}</div>
                </div>

                ${
                    request.receipt_path
                    ? `
                        <button
                            type="button"
                            class="premium-admin-btn"
                            data-receipt-id="${request.id}"
                        >
                            🧾 View Receipt
                        </button>
                    `
                    : `
                        <div class="empty-mini">
                            No receipt
                        </div>
                    `
                }

                ${
                    status === "pending"
                    ? `
                        <div class="premium-admin-actions">

                            <input
                                type="number"
                                min="1"
                                max="3650"
                                class="premium-admin-days"
                                data-days-id="${request.id}"
                                placeholder="Days"
                            >

                            <input
                                type="text"
                                maxlength="1000"
                                class="premium-admin-note"
                                data-note-id="${request.id}"
                                placeholder="Admin note / reject reason"
                            >

                            <div class="premium-admin-action-row">
                                <button
                                    type="button"
                                    class="premium-admin-btn approve"
                                    data-approve-id="${request.id}"
                                >
                                    ✅ Approve
                                </button>

                                <button
                                    type="button"
                                    class="premium-admin-btn reject"
                                    data-reject-id="${request.id}"
                                >
                                    ❌ Reject
                                </button>
                            </div>
                        </div>
                    `
                    : `
                        <div class="premium-admin-note-display">
                            ${escapeHtml(
                                request.admin_note || ""
                            )}
                        </div>
                    `
                }
            `;

            list.appendChild(item);
        }

    } catch (error) {
        console.error(
            "Premium Admin API:",
            error
        );

        setPremiumAdminStatus(
            `❌ ${error.message || "Could not load requests"}`,
            true
        );
    }
}


function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}


async function approvePremiumRequest(requestId) {
    const daysEl =
        document.querySelector(
            `[data-days-id="${requestId}"]`
        );

    const noteEl =
        document.querySelector(
            `[data-note-id="${requestId}"]`
        );

    const days =
        Number(daysEl?.value || 0);

    const adminNote =
        noteEl?.value?.trim() || "";

    if (!days || days <= 0) {
        setPremiumAdminStatus(
            "❌ Enter Premium days before approving.",
            true
        );
        return;
    }

    if (days > 3650) {
        setPremiumAdminStatus(
            "❌ Maximum is 3650 days.",
            true
        );
        return;
    }

    if (!confirm(
        `Approve request #${requestId} for ${days} day(s)?`
    )) {
        return;
    }

    try {
        setPremiumAdminStatus(
            "⏳ Approving..."
        );

        await apiFetch(
            API_BASE +
            "/api/admin/premium/approve",
            {
                method: "POST",
                headers: {
                    "Content-Type":
                        "application/json"
                },
                body: JSON.stringify({
                    request_id: requestId,
                    days: Math.floor(days),
                    admin_note: adminNote
                })
            }
        );

        setPremiumAdminStatus(
            `✅ Request #${requestId} approved.`
        );

        await loadPremiumAdmin();
        await loadPremium();

    } catch (error) {
        setPremiumAdminStatus(
            `❌ ${error.message || "Approval failed"}`,
            true
        );
    }
}


async function rejectPremiumRequest(requestId) {
    const noteEl =
        document.querySelector(
            `[data-note-id="${requestId}"]`
        );

    const adminNote =
        noteEl?.value?.trim() || "";

    if (!adminNote) {
        setPremiumAdminStatus(
            "❌ Enter a reject reason.",
            true
        );
        return;
    }

    if (!confirm(
        `Reject Premium request #${requestId}?`
    )) {
        return;
    }

    try {
        setPremiumAdminStatus(
            "⏳ Rejecting..."
        );

        await apiFetch(
            API_BASE +
            "/api/admin/premium/reject",
            {
                method: "POST",
                headers: {
                    "Content-Type":
                        "application/json"
                },
                body: JSON.stringify({
                    request_id: requestId,
                    admin_note: adminNote
                })
            }
        );

        setPremiumAdminStatus(
            `✅ Request #${requestId} rejected.`
        );

        await loadPremiumAdmin();
        await loadPremium();

    } catch (error) {
        setPremiumAdminStatus(
            `❌ ${error.message || "Rejection failed"}`,
            true
        );
    }
}


async function viewPremiumReceipt(requestId) {
    const receiptUrl =
        API_BASE +
        `/api/admin/premium/receipt?request_id=${encodeURIComponent(requestId)}`;

    try {
        console.log("Premium receipt request:", receiptUrl);
        console.log("Premium receipt initData:", {
            hasInitData: Boolean(getInitData()),
            initDataLength: getInitData().length,
            hostname: window.location.hostname,
            apiBase: API_BASE
        });

        const response = await fetch(
            receiptUrl,
            {
                cache: "no-store",
                headers: {
                    "X-Telegram-Init-Data":
                        getInitData()
                }
            }
        );

        console.log(
            "Premium receipt response:",
            response.status,
            response.type,
            response.headers.get("content-type")
        );

        if (!response.ok) {
            const data =
                await response.json()
                    .catch(() => ({}));

            throw new Error(
                data.error ||
                `Receipt error ${response.status}`
            );
        }

        const blob =
            await response.blob();

        console.log(
            "Premium receipt loaded:",
            blob.type,
            blob.size
        );

        const image =
            document.getElementById(
                "receipt-modal-image"
            );

        const modal =
            document.getElementById(
                "receipt-modal"
            );

        if (!image || !modal) {
            throw new Error(
                "Receipt preview UI is unavailable"
            );
        }

        const reader =
            new FileReader();

        const dataUrl =
            await new Promise(
                (resolve, reject) => {
                    reader.onload =
                        () => resolve(reader.result);

                    reader.onerror =
                        () => reject(
                            new Error(
                                "Could not read receipt image"
                            )
                        );

                    reader.readAsDataURL(blob);
                }
            );

        image.src = dataUrl;

        modal.classList.add("show");
        document.body.classList.add("modal-open");

    } catch (error) {
        console.error(
            "Premium receipt error:",
            error,
            "name=",
            error?.name,
            "message=",
            error?.message,
            "stack=",
            error?.stack
        );

        setPremiumAdminStatus(
            `❌ Receipt request failed: ${error.message || "Unknown error"}`,
            true
        );
    }
}

function setupPremiumReceiptModal() {
    const modal =
        document.getElementById("receipt-modal");

    const close =
        document.getElementById("receipt-modal-close");

    const backdrop =
        document.getElementById("receipt-modal-backdrop");

    if (!modal) return;

    const hide = () => {
        modal.classList.remove("show");
        document.body.classList.remove("modal-open");

        const image =
            document.getElementById(
                "receipt-modal-image"
            );

        if (image) {
            image.removeAttribute("src");
        }
    };

    if (close) {
        close.addEventListener("click", hide);
    }

    if (backdrop) {
        backdrop.addEventListener("click", hide);
    }
}

function setupPremiumAdmin() {
    if (!isCurrentOwner()) return;

    const list =
        document.getElementById(
            "premium-admin-requests"
        );

    if (!list) return;

    list.addEventListener(
        "click",
        async (event) => {
            const approve =
                event.target.closest(
                    "[data-approve-id]"
                );

            const reject =
                event.target.closest(
                    "[data-reject-id]"
                );

            const receipt =
                event.target.closest(
                    "[data-receipt-id]"
                );

            if (approve) {
                await approvePremiumRequest(
                    Number(
                        approve.dataset.approveId
                    )
                );
                return;
            }

            if (reject) {
                await rejectPremiumRequest(
                    Number(
                        reject.dataset.rejectId
                    )
                );
                return;
            }

            if (receipt) {
                await viewPremiumReceipt(
                    Number(
                        receipt.dataset.receiptId
                    )
                );
            }
        }
    );

    loadPremiumAdmin();
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

function setTradeStatus(message, isError = false) {
    const el = document.getElementById(
        "trade-action-status"
    );

    if (!el) return;

    el.textContent = message || "";

    el.classList.toggle(
        "error",
        Boolean(isError)
    );
}


function setTradeRarityStatus(
    message,
    isError = false
) {
    const el = document.getElementById(
        "trade-rarity-status"
    );

    if (!el) return;

    el.textContent = message || "";

    el.classList.toggle(
        "error",
        Boolean(isError)
    );
}


function getCardById(cardId) {
    return allCards.find(
        card =>
            Number(card.id) === Number(cardId)
    );
}


function populateTradeCards() {
    const offeredSelect =
        document.getElementById(
            "trade-offered-card"
        );

    const requestedSelect =
        document.getElementById(
            "trade-requested-card"
        );

    if (!offeredSelect || !requestedSelect) {
        return;
    }

    const ownedCards = allCards
        .filter(card => getMyQuantity(card) > 0)
        .sort((a, b) =>
            String(a.name || "")
                .localeCompare(
                    String(b.name || "")
                )
        );

    const activeCards = allCards
        .filter(
            card =>
                Number(card.is_active ?? 1) === 1
        )
        .sort((a, b) =>
            String(a.name || "")
                .localeCompare(
                    String(b.name || "")
                )
        );

    offeredSelect.innerHTML =
        '<option value="">Select a card</option>';

    for (const card of ownedCards) {
        const option =
            document.createElement("option");

        option.value = card.id;

        option.textContent =
            `${card.name || card.card_code} ` +
            `(${getCardRarity(card)}) ` +
            `×${getMyQuantity(card)}`;

        offeredSelect.appendChild(option);
    }

    requestedSelect.innerHTML =
        '<option value="">Select a card</option>';

    for (const card of activeCards) {
        const option =
            document.createElement("option");

        option.value = card.id;

        option.textContent =
            `${card.name || card.card_code} ` +
            `(${getCardRarity(card)})`;

        requestedSelect.appendChild(option);
    }

    updateTradeRarityStatus();
}


function updateTradeRarityStatus() {
    const offeredSelect =
        document.getElementById(
            "trade-offered-card"
        );

    const requestedSelect =
        document.getElementById(
            "trade-requested-card"
        );

    if (!offeredSelect || !requestedSelect) {
        return;
    }

    const offered =
        getCardById(offeredSelect.value);

    const requested =
        getCardById(requestedSelect.value);

    if (!offered || !requested) {
        setTradeRarityStatus("");
        return;
    }

    const offeredRarity =
        getCardRarity(offered);

    const requestedRarity =
        getCardRarity(requested);

    if (offeredRarity !== requestedRarity) {
        setTradeRarityStatus(
            "❌ Cards must have the same rarity.",
            true
        );
        return;
    }

    if (
        Number(offered.id) ===
        Number(requested.id)
    ) {
        setTradeRarityStatus(
            "❌ Select two different cards.",
            true
        );
        return;
    }

    setTradeRarityStatus(
        `✅ ${offeredRarity.toUpperCase()} ↔ ` +
        `${requestedRarity.toUpperCase()}`
    );
}


async function createTrade() {
    const targetInput =
        document.getElementById(
            "trade-target-user"
        );

    const offeredSelect =
        document.getElementById(
            "trade-offered-card"
        );

    const requestedSelect =
        document.getElementById(
            "trade-requested-card"
        );

    const button =
        document.getElementById(
            "trade-create-btn"
        );

    const targetUserId =
        Number(targetInput?.value || 0);

    const offeredCardId =
        Number(offeredSelect?.value || 0);

    const requestedCardId =
        Number(requestedSelect?.value || 0);

    if (targetUserId <= 0) {
        setTradeStatus(
            "❌ Enter a valid Telegram User ID.",
            true
        );
        return;
    }

    if (
        offeredCardId <= 0 ||
        requestedCardId <= 0
    ) {
        setTradeStatus(
            "❌ Select both cards.",
            true
        );
        return;
    }

    const offered =
        getCardById(offeredCardId);

    const requested =
        getCardById(requestedCardId);

    if (!offered || !requested) {
        setTradeStatus(
            "❌ Card not found.",
            true
        );
        return;
    }

    if (
        getCardRarity(offered) !==
        getCardRarity(requested)
    ) {
        setTradeStatus(
            "❌ Both cards must have the same rarity.",
            true
        );
        return;
    }

    if (offeredCardId === requestedCardId) {
        setTradeStatus(
            "❌ Select two different cards.",
            true
        );
        return;
    }

    if (button) {
        button.disabled = true;
        button.textContent =
            "⏳ SENDING...";
    }

    setTradeStatus("");

    try {
        await apiFetch(
            API_BASE + "/api/trade/create",
            {
                method: "POST",
                headers: {
                    "Content-Type":
                        "application/json"
                },
                body: JSON.stringify({
                    to_user_id: targetUserId,
                    offered_card_id:
                        offeredCardId,
                    requested_card_id:
                        requestedCardId
                })
            }
        );

        setTradeStatus(
            "✅ Trade request sent."
        );

        if (targetInput) {
            targetInput.value = "";
        }

        if (offeredSelect) {
            offeredSelect.value = "";
        }

        if (requestedSelect) {
            requestedSelect.value = "";
        }

        updateTradeRarityStatus();

        await loadTrades();

    } catch (error) {
        setTradeStatus(
            `❌ ${error.message || "Trade failed."}`,
            true
        );

    } finally {
        if (button) {
            button.disabled = false;
            button.textContent =
                "📤 SEND TRADE";
        }
    }
}


async function tradeAction(
    action,
    tradeId
) {
    try {
        const data =
            await apiFetch(
                API_BASE +
                `/api/trade/${action}`,
                {
                    method: "POST",
                    headers: {
                        "Content-Type":
                            "application/json"
                    },
                    body: JSON.stringify({
                        trade_id:
                            Number(tradeId)
                    })
                }
            );

        setTradeStatus(
            `✅ Trade ${data.trade?.status || action}.`
        );

        await Promise.allSettled([
            loadTrades(),
            loadCollection(),
            loadMe()
        ]);

        populateTradeCards();

    } catch (error) {
        setTradeStatus(
            `❌ ${error.message || "Trade action failed."}`,
            true
        );

        await loadTrades();
    }
}


async function loadTrades() {
    try {
        const data =
            await apiFetch(
                API_BASE + "/api/trades"
            );

        const list =
            document.getElementById(
                "trades-list"
            );

        if (!list) return;

        list.innerHTML = "";

        const trades =
            data.trades || [];

        if (!trades.length) {
            list.innerHTML =
                '<div class="empty-mini">No trades yet.</div>';
            return;
        }

        const currentUserId =
            Number(
                window.currentUserId || 0
            );

        for (const trade of trades) {
            const item =
                document.createElement("div");

            item.className =
                "trade-item";

            const isIncoming =
                currentUserId > 0 &&
                Number(trade.to_user_id) ===
                    currentUserId;

            const isOutgoing =
                currentUserId > 0 &&
                Number(trade.from_user_id) ===
                    currentUserId;

            const offeredLabel =
                trade.offered_card_name ||
                trade.offered_card_code ||
                `Card #${trade.offered_card_id}`;

            const requestedLabel =
                trade.requested_card_name ||
                trade.requested_card_code ||
                `Card #${trade.requested_card_id}`;

            const rarity =
                trade.offered_rarity ||
                trade.requested_rarity ||
                "";

            let actions = "";

            if (
                trade.status === "pending" &&
                isIncoming
            ) {
                actions = `
                    <div class="trade-actions">
                        <button
                            type="button"
                            data-trade-action="accept"
                            data-trade-id="${trade.id}"
                        >
                            ✅ Accept
                        </button>

                        <button
                            type="button"
                            data-trade-action="reject"
                            data-trade-id="${trade.id}"
                        >
                            ❌ Reject
                        </button>
                    </div>
                `;
            }

            if (
                trade.status === "pending" &&
                isOutgoing
            ) {
                actions = `
                    <div class="trade-actions">
                        <button
                            type="button"
                            data-trade-action="cancel"
                            data-trade-id="${trade.id}"
                        >
                            🚫 Cancel
                        </button>
                    </div>
                `;
            }

            item.innerHTML = `
                <strong>
                    Trade #${trade.id}
                </strong>

                <span>
                    ${
                        isIncoming
                            ? "📥 Incoming"
                            : isOutgoing
                                ? "📤 Outgoing"
                                : ""
                    }
                    · ${trade.status || "unknown"}
                </span>

                <small>
                    ${offeredLabel}
                    ↔
                    ${requestedLabel}
                    ${rarity ? ` · ${rarity}` : ""}
                </small>

                <small>
                    ${trade.created_at || ""}
                </small>

                ${actions}
            `;

            list.appendChild(item);
        }

        list
            .querySelectorAll(
                "[data-trade-action]"
            )
            .forEach(button => {
                button.addEventListener(
                    "click",
                    async () => {
                        const action =
                            button.dataset
                                .tradeAction;

                        const tradeId =
                            button.dataset
                                .tradeId;

                        button.disabled = true;

                        await tradeAction(
                            action,
                            tradeId
                        );
                    }
                );
            });

    } catch (error) {
        console.error(
            "Trades API:",
            error
        );
    }
}


function setupTradeUI() {
    const offeredSelect =
        document.getElementById(
            "trade-offered-card"
        );

    const requestedSelect =
        document.getElementById(
            "trade-requested-card"
        );

    const createButton =
        document.getElementById(
            "trade-create-btn"
        );

    if (offeredSelect) {
        offeredSelect.addEventListener(
            "change",
            updateTradeRarityStatus
        );
    }

    if (requestedSelect) {
        requestedSelect.addEventListener(
            "change",
            updateTradeRarityStatus
        );
    }

    if (createButton) {
        createButton.addEventListener(
            "click",
            createTrade
        );
    }

    populateTradeCards();
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
   Collection UI
----------------------------- */

document.querySelectorAll(".gallery-mode").forEach((button) => {
    button.addEventListener("click", () => {
        setGalleryMode(
            button.dataset.mode || "all",
            button
        );
    });
});

document.querySelectorAll(".rarity-filter").forEach((button) => {
    button.addEventListener("click", () => {
        activeRarityFilter =
            button.dataset.rarity || "all";

        document
            .querySelectorAll(".rarity-filter")
            .forEach((btn) => {
                btn.classList.toggle(
                    "active",
                    btn === button
                );
            });

        renderGallery();
    });
});

document.getElementById("card-modal-close")
    ?.addEventListener("click", closeCardGallery);

document.querySelector(".card-modal-backdrop")
    ?.addEventListener("click", closeCardGallery);


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

document.getElementById("catch-input")
    ?.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
            event.preventDefault();
            catchCard();
        }
    });


/* -----------------------------
   Start
----------------------------- */

loadTelegramUser();
setupPremiumPurchase();
setupPremiumAdmin();
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


document.addEventListener("DOMContentLoaded", setupPremiumReceiptModal);
