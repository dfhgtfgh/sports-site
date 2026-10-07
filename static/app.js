const API = {
  matches: "/api/matches",
  news: "/api/news",
  newsFull: "/api/news/full",
};

let currentCategory = "all";
let newsCache = [];

// ---------------- Утилиты ----------------
const $ = (sel) => document.querySelector(sel);

function escapeHtml(str = "") {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function timeAgo(ts) {
  if (!ts) return "";
  const diff = Math.floor(Date.now() / 1000 - ts);
  if (diff < 60) return "только что";
  if (diff < 3600) return `${Math.floor(diff / 60)} мин назад`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} ч назад`;
  return `${Math.floor(diff / 86400)} дн назад`;
}

// ---------------- Матчи ----------------
async function loadMatches() {
  const grid = $("#matches-grid");
  try {
    const res = await fetch(`${API.matches}?category=${currentCategory}`);
    const matches = await res.json();

    $("#matches-count").textContent = matches.length;

    if (!matches.length) {
      grid.innerHTML = `<div class="empty">Сегодня матчей не найдено 😔<br><small>Попробуй категорию выше.</small></div>`;
      renderLiveBar([]);
      return;
    }

    grid.innerHTML = matches.map(renderMatchCard).join("");
    renderLiveBar(matches.filter((m) => m.is_live));
  } catch (e) {
    console.error(e);
    grid.innerHTML = `<div class="empty">Ошибка загрузки матчей</div>`;
  }
}

function renderMatchCard(m) {
  const live = m.is_live ? "is-live" : "";
  const scoreParts = (m.score || "-").split(/[:\- ]+/);
  const homeScore = scoreParts[0] ?? "";
  const awayScore = scoreParts[1] ?? "";
  const hasAway = m.away && m.away.trim();

  return `
    <article class="match-card ${live}">
      <div class="match-card__top">
        <span class="match-card__tournament">${escapeHtml(m.tournament || m.sport_title || "Матч")}</span>
        ${m.is_live ? '<span class="match-card__live">LIVE</span>' : ""}
      </div>
      <div class="match-card__teams">
        <div class="team">
          <span class="team__name">${escapeHtml(m.home)}</span>
          <span class="team__score">${escapeHtml(homeScore)}</span>
        </div>
        ${hasAway ? `
        <div class="team">
          <span class="team__name">${escapeHtml(m.away)}</span>
          <span class="team__score">${escapeHtml(awayScore)}</span>
        </div>` : ""}
      </div>
      <div class="match-card__bottom">
        <span class="match-card__status ${m.is_live ? "live" : ""}">
          ${escapeHtml(m.time ? m.time + " · " : "")}${escapeHtml(m.status || "—")}
        </span>
        <span>${escapeHtml(m.sport_title || "")}</span>
      </div>
    </article>
  `;
}

function renderLiveBar(liveMatches) {
  const track = $("#livebar-track");
  if (!liveMatches.length) {
    track.innerHTML = `<span class="livebar__empty">Сейчас нет live-матчей</span>`;
    return;
  }
  track.innerHTML = liveMatches
    .map(
      (m) => `
      <span class="live-item">
        <span>${escapeHtml(m.home)}</span>
        <span class="score">${escapeHtml(m.score || "-")}</span>
        <span>${escapeHtml(m.away || "")}</span>
      </span>`
    )
    .join("");
}

// ---------------- Новости ----------------
async function loadNews(category = "all") {
  const list = $("#news-list");
  try {
    const res = await fetch(`${API.news}?category=${category}&limit=25`);
    const news = await res.json();
    newsCache = news;

    if (!news.length) {
      list.innerHTML = `<div class="empty">Новостей пока нет</div>`;
      return;
    }

    list.innerHTML = news.map(renderNewsCard).join("");
  } catch (e) {
    console.error(e);
    list.innerHTML = `<div class="empty">Ошибка загрузки новостей</div>`;
  }
}

function renderNewsCard(n) {
  return `
    <a class="news-card" href="#" data-url="${escapeHtml(n.link)}" data-cat="${escapeHtml(n.category)}" data-title="${escapeHtml(n.title)}" data-summary="${escapeHtml(n.summary || "")}">
      <div class="news-card__meta">
        <span class="news-card__cat">${escapeHtml(n.category)}</span>
        <span>${timeAgo(n.published_ts)}</span>
      </div>
      <div class="news-card__title">${escapeHtml(n.title)}</div>
      ${n.summary ? `<div class="news-card__summary">${escapeHtml(n.summary)}</div>` : ""}
    </a>
  `;
}

// ---------------- Модалка ----------------
const modal = $("#news-modal");
const modalBody = $("#news-modal-body");

function openModal() {
  modal.hidden = false;
  document.body.style.overflow = "hidden";
}

function closeModal() {
  modal.hidden = true;
  document.body.style.overflow = "";
  modalBody.innerHTML = `<div class="modal__loader">Загрузка статьи…</div>`;
}

function renderPreview(title, cat, summary) {
  return `
    <article class="article">
      <div class="article__head">
        ${cat ? `<span class="article__cat">${escapeHtml(cat)}</span>` : ""}
        <h1 class="article__title">${escapeHtml(title || "")}</h1>
        ${summary ? `<p style="color:var(--muted);font-size:14px;line-height:1.6;margin-bottom:6px">${escapeHtml(summary)}</p>` : ""}
        <div class="article__meta">
          <span>Спортивные новости</span>
        </div>
      </div>
      <div class="article__content">
        <div class="modal__loader">Загрузка полного текста…</div>
      </div>
    </article>
  `;
}

function renderPreviewFallback(title, cat, summary, url) {
  return `
    <article class="article">
      <div class="article__head">
        ${cat ? `<span class="article__cat">${escapeHtml(cat)}</span>` : ""}
        <h1 class="article__title">${escapeHtml(title || "")}</h1>
        ${summary ? `<p style="color:var(--muted);font-size:14px;line-height:1.6;margin-bottom:6px">${escapeHtml(summary)}</p>` : ""}
        <div class="article__meta">
          <span>Спортивные новости</span>
        </div>
      </div>
      <div class="article__content">
        <p style="color:var(--muted)">Полный текст недоступен.</p>
      </div>
    </article>
  `;
}

function renderArticle(data, fallbackTitle, fallbackCat, fallbackSummary) {
  const title = data.title || fallbackTitle || "";
  const summary = fallbackSummary || data.description || "";
  const image = data.image
    ? `<img class="article__hero" src="${escapeHtml(data.image)}" alt="" loading="lazy" onerror="this.remove()">`
    : "";
  const content = (data.paragraphs || [])
    .map((p) => {
      const cls = p.type === "h" ? "h2" : "p";
      return `<${cls}>${escapeHtml(p.text)}</${cls}>`;
    })
    .join("");

  return `
    <article class="article">
      ${image}
      <div class="article__head">
        ${fallbackCat ? `<span class="article__cat">${escapeHtml(fallbackCat)}</span>` : ""}
        <h1 class="article__title">${escapeHtml(title)}</h1>
        ${summary && !image ? `<p style="color:var(--muted);font-size:14px;line-height:1.6;margin-bottom:6px">${escapeHtml(summary)}</p>` : ""}
        <div class="article__meta">
          <span>Спортивные новости</span>
        </div>
      </div>
      <div class="article__content">
        ${content || "<p>Полный текст недоступен.</p>"}
      </div>
    </article>
  `;
}

async function openNews(url, title, cat, summary) {
  openModal();
  modalBody.innerHTML = renderPreview(title, cat, summary);

  try {
    const res = await fetch(`${API.newsFull}?url=${encodeURIComponent(url)}`);
    if (!res.ok) throw new Error("bad response");
    const data = await res.json();

    const hasContent = (data.paragraphs || []).length > 0;
    if (!hasContent && !data.image) {
      throw new Error("no content");
    }

    modalBody.innerHTML = renderArticle(data, title, cat, summary);
    modalBody.scrollTop = 0;
  } catch (e) {
    console.error(e);
    modalBody.innerHTML = renderPreviewFallback(title, cat, summary, url);
  }
}

document.addEventListener("click", (e) => {
  const card = e.target.closest(".news-card");
  if (card) {
    e.preventDefault();
    openNews(
      card.dataset.url,
      card.dataset.title,
      card.dataset.cat,
      card.dataset.summary || ""
    );
    return;
  }
  if (e.target.closest("[data-close-modal]")) {
    closeModal();
  }
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !modal.hidden) closeModal();
});

// ---------------- Навигация ----------------
document.querySelectorAll(".nav__btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".nav__btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    currentCategory = btn.dataset.cat;
    loadNews(currentCategory);
    loadMatches();
  });
});

// ---------------- Мобильные табы ----------------
function setupMobileTabs() {
  const tabs = document.querySelectorAll(".mobile-tab");
  const panels = document.querySelectorAll("[data-tab-panel]");

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const target = tab.dataset.tab;
      tabs.forEach((t) => t.classList.toggle("active", t === tab));
      panels.forEach((p) => {
        p.classList.toggle("active", p.dataset.tabPanel === target);
      });
    });
  });

  if (panels.length) {
    panels.forEach((p, i) => p.classList.toggle("active", i === 0));
  }
}

$("#refresh-news").addEventListener("click", () => loadNews(currentCategory));

// ---------------- Автообновление ----------------
function tick() {
  const el = $("#last-update");
  if (el) el.textContent = new Date().toLocaleTimeString("ru-RU");
}

async function refreshAll() {
  tick();
  await Promise.all([loadMatches(), loadNews(currentCategory)]);
}

setupMobileTabs();
refreshAll();

setInterval(loadMatches, 60_000);
setInterval(() => loadNews(currentCategory), 300_000);
setInterval(tick, 1000);