"""
Парсер матчей и новостей с championat.com
Матчи — через Playwright (эмуляция браузера, JS рендеринг)
Новости — через RSS championat.com + полный текст статьи через Playwright
"""
import re
import time
import logging
from typing import List, Dict

import requests
import feedparser
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}

RSS_FEEDS = {
    "football":   "https://www.championat.com/rss/news/football/",
    "hockey":     "https://www.championat.com/rss/news/hockey/",
    "basketball": "https://www.championat.com/rss/news/basketball/",
    "tennis":     "https://www.championat.com/rss/news/tennis/",
}

MATCHES_URL = "https://www.championat.com/stat/"

_cache = {
    "news": {"data": None, "ts": 0},
    "matches": {"data": None, "ts": 0},
    "articles": {},  # url -> {"data": ..., "ts": ...}
}
NEWS_TTL = 300
MATCHES_TTL = 180
ARTICLE_TTL = 3600  # 1 час


def _is_fresh(key, ttl):
    return _cache[key]["data"] is not None and (time.time() - _cache[key]["ts"]) < ttl


# ============================================================
#                        НОВОСТИ
# ============================================================
def fetch_news(category="all", limit=25):
    if _is_fresh("news", NEWS_TTL):
        all_news = _cache["news"]["data"]
    else:
        all_news = []
        for cat, url in RSS_FEEDS.items():
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:15]:
                    all_news.append({
                        "category": cat,
                        "title": entry.get("title", "").strip(),
                        "link": entry.get("link", ""),
                        "summary": _clean_summary(entry.get("summary", "")),
                        "published_ts": _parse_published(entry),
                    })
            except Exception as e:
                log.warning(f"RSS {cat} failed: {e}")

        seen, unique = set(), []
        for item in all_news:
            if item["link"] in seen:
                continue
            seen.add(item["link"])
            unique.append(item)
        unique.sort(key=lambda x: x["published_ts"], reverse=True)
        _cache["news"]["data"] = unique
        _cache["news"]["ts"] = time.time()
        all_news = unique

    if category == "all":
        return all_news[:limit]
    return [n for n in all_news if n["category"] == category][:limit]


def _clean_summary(html):
    if not html:
        return ""
    text = re.sub(r"<[^>]+>", "", html)
    text = text.replace("&nbsp;", " ").replace("&quot;", '"').replace("&amp;", "&")
    return text.strip()[:280]


def _parse_published(entry):
    try:
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            return time.mktime(entry.published_parsed)
    except Exception:
        pass
    return time.time()


# ============================================================
#                        МАТЧИ (Playwright)
# ============================================================
def fetch_matches():
    if _is_fresh("matches", MATCHES_TTL):
        return _cache["matches"]["data"]

    matches = []
    try:
        html = _fetch_matches_html_playwright()
        matches = _parse_matches_html(html)
    except Exception as e:
        log.warning(f"Match parse failed: {e}")

    if not matches:
        matches = _cache["matches"]["data"] or []

    _cache["matches"]["data"] = matches
    _cache["matches"]["ts"] = time.time()
    log.info(f"Parsed {len(matches)} matches")
    return matches


def _fetch_matches_html_playwright():
    """Открывает championat.com/stat/ в headless Chromium и ждёт, пока
    отрисуются блоки с матчами, потом возвращает HTML."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = browser.new_context(
            user_agent=HEADERS["User-Agent"],
            locale="ru-RU",
            viewport={"width": 1366, "height": 900},
        )
        page = context.new_page()
        try:
            page.goto(MATCHES_URL, timeout=45000, wait_until="domcontentloaded")
            try:
                page.wait_for_selector(
                    ".livetable-event, .seo-results__item, .mc-tab-content",
                    timeout=20000,
                )
            except Exception:
                pass
            page.wait_for_timeout(3000)
            html = page.content()
        finally:
            browser.close()

    return html


def _parse_matches_html(html):
    soup = BeautifulSoup(html, "html.parser")
    matches = []

    matches.extend(_parse_livetable(soup))

    for noscript in soup.find_all("noscript"):
        inner = noscript.decode_contents()
        if not inner:
            continue
        if "livetable" in inner or "seo-results" in inner:
            inner_soup = BeautifulSoup(inner, "html.parser")
            matches.extend(_parse_livetable(inner_soup))
            matches.extend(_parse_seo_results(inner_soup))

    matches.extend(_parse_seo_results(soup))

    seen, unique = set(), []
    for m in matches:
        if not m.get("home") and not m.get("away"):
            continue
        key = (m.get("home"), m.get("away"), m.get("time"), m.get("tournament"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(m)

    return unique


def _parse_livetable(soup):
    results = []
    for sport_block in soup.select(".livetable-sport"):
        sport_tag = sport_block.select_one(".livetable-sport__head a")
        sport_name = sport_tag.get_text(strip=True) if sport_tag else ""
        sport_class = " ".join(sport_tag.get("class", [])) if sport_tag else ""
        sport_key = _sport_key_from_class(sport_class)

        for tour_block in sport_block.select(".livetable-tournament"):
            tour_el = tour_block.select_one(".livetable-tournament__title")
            tournament = tour_el.get_text(strip=True) if tour_el else ""

            for li in tour_block.select(".livetable-event"):
                m = _extract_livetable_event(li, sport_key, sport_name, tournament)
                if m:
                    results.append(m)
    return results


def _extract_livetable_event(li, sport, sport_title, tournament):
    try:
        time_el = li.select_one(".livetable-event__time")
        time_str = time_el.get_text(strip=True) if time_el else ""

        name_el = li.select_one(".livetable-event__name")
        teams = []
        if name_el:
            for team_el in name_el.select(".team-name"):
                teams.append(team_el.get_text(strip=True))

        home = teams[0] if len(teams) > 0 else ""
        away = teams[1] if len(teams) > 1 else ""

        result_el = li.select_one(".livetable-event__result")
        score = ""
        if result_el:
            sets = result_el.select(".score-set")
            if sets:
                score = " ".join(s.get_text(strip=True) for s in sets)
            else:
                ext = result_el.select_one(".result-ext")
                ext_text = ""
                if ext:
                    ext_text = ext.get_text(strip=True)
                    ext.extract()
                base = result_el.get_text(" ", strip=True)
                score = (base + (" " + ext_text if ext_text else "")).strip()

        status_el = li.select_one(".livetable-event__status")
        status = status_el.get_text(strip=True) if status_el else ""

        is_live = bool(re.search(r"период|сет|четверт|тайм|Идёт|\d+'", status))

        return {
            "sport": sport,
            "sport_title": sport_title,
            "tournament": tournament,
            "home": home,
            "away": away,
            "score": score or "-",
            "time": time_str,
            "status": status,
            "is_live": is_live,
        }
    except Exception as e:
        log.debug(f"event parse error: {e}")
        return None


def _parse_seo_results(soup):
    results = []
    container = soup.select_one(".seo-results")
    if not container:
        return results

    current_sport = ""
    current_tournament = ""

    for el in container.find_all(recursive=False):
        cls = " ".join(el.get("class", []))
        if "seo-results__sport" in cls:
            current_sport = el.get_text(strip=True)
        elif "seo-results__tournament" in cls:
            current_tournament = el.get_text(strip=True)
        elif el.name == "ul":
            for li in el.select(".seo-results__item"):
                time_el = li.select_one(".seo-results__item-date")
                time_str = time_el.get_text(strip=True) if time_el else ""
                link = li.find("a")
                if not link:
                    continue
                link_text = link.get_text(strip=True)
                status_el = li.select_one(".seo-results__item-status")
                status = status_el.get_text(strip=True) if status_el else ""

                score = ""
                m = re.search(r"(.+?)\s*[–—]\s*(.+?)(?:\s+(\d+\s*:\s*\d+.*))?$", link_text)
                if m:
                    home = m.group(1).strip()
                    away = m.group(2).strip()
                    if m.group(3):
                        score = m.group(3).strip()
                else:
                    parts = re.split(r"\s*[–—]\s*", link_text, maxsplit=1)
                    home = parts[0].strip() if parts else link_text
                    away = parts[1].strip() if len(parts) > 1 else ""

                results.append({
                    "sport": _sport_key_from_title(current_sport),
                    "sport_title": current_sport,
                    "tournament": current_tournament,
                    "home": home,
                    "away": away,
                    "score": score or "-",
                    "time": time_str,
                    "status": status,
                    "is_live": ("Идёт" in status) or ("период" in status) or ("сет" in status),
                })
    return results


def _sport_key_from_class(class_str):
    for key in ("football", "hockey", "tennis", "basketball", "volleyball",
                "auto", "mma", "biathlon", "skiing", "figureskating",
                "futsal", "rugby", "handball", "cybersport", "chess"):
        if key in class_str:
            return key
    return ""


def _sport_key_from_title(title):
    mapping = {
        "футбол": "football",
        "хоккей": "hockey",
        "теннис": "tennis",
        "баскетбол": "basketball",
        "волейбол": "volleyball",
    }
    lower = (title or "").lower()
    for rus, key in mapping.items():
        if rus in lower:
            return key
    return ""


# ============================================================
#                        СТАТЬЯ (полный текст)
# ============================================================
def fetch_article(url):
    """Скачивает статью через Playwright (отрабатывает JS-редиректы)
    и возвращает заголовок, картинку, абзацы."""
    if not url or "championat.com" not in url:
        return None

    # Кэш
    cached = _cache["articles"].get(url)
    if cached and (time.time() - cached["ts"]) < ARTICLE_TTL:
        return cached["data"]

    html, final_url = _fetch_article_html_playwright(url)
    if not html:
        return None

    soup = BeautifulSoup(html, "html.parser")

    # Заголовок
    title = ""
    h1 = soup.find("h1")
    if h1:
        title = h1.get_text(strip=True)
    if not title:
        og = soup.find("meta", property="og:title")
        if og:
            title = og.get("content", "")

    # Картинка
    image = ""
    og_img = soup.find("meta", property="og:image")
    if og_img:
        image = og_img.get("content", "")
    if not image:
        img = soup.select_one(".article__head img, .article img, picture img")
        if img:
            image = img.get("src") or img.get("data-src", "")

    # Описание
    description = ""
    og_desc = soup.find("meta", property="og:description")
    if og_desc:
        description = og_desc.get("content", "")

    # Основной текст
    body = (
        soup.select_one(".article__body")
        or soup.select_one(".article-body")
        or soup.select_one("[itemprop='articleBody']")
        or soup.select_one("article")
    )

    paragraphs = []
    if body:
        for el in body.find_all(["p", "h2", "h3"], recursive=True):
            cls = " ".join(el.get("class", []))
            if any(x in cls for x in ("adv", "banner", "promo", "related")):
                continue
            text = el.get_text(" ", strip=True)
            if not text or len(text) < 20:
                continue
            if text.startswith(("Читайте также", "Реклама", "18+")):
                continue
            paragraphs.append({
                "type": "h" if el.name in ("h2", "h3") else "p",
                "text": text,
            })

    if not paragraphs:
        if description:
            paragraphs.append({"type": "p", "text": description})
        for p in soup.find_all("p")[:20]:
            text = p.get_text(" ", strip=True)
            if len(text) >= 40:
                paragraphs.append({"type": "p", "text": text})

    data = {
        "title": title,
        "image": image,
        "description": description,
        "paragraphs": paragraphs[:40],
        "url": final_url or url,
    }

    _cache["articles"][url] = {"data": data, "ts": time.time()}
    return data


def _fetch_article_html_playwright(url):
    """Открывает URL статьи в headless Chromium, ждёт JS-редиректы
    и возвращает (html, final_url)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None, None

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = browser.new_context(
            user_agent=HEADERS["User-Agent"],
            locale="ru-RU",
            viewport={"width": 1366, "height": 900},
        )
        page = context.new_page()
        try:
            page.goto(url, timeout=45000, wait_until="domcontentloaded")

            # Ждём либо типичные блоки статьи, либо окончания редиректа
            try:
                page.wait_for_selector(
                    "h1, .article__body, [itemprop='articleBody']",
                    timeout=15000,
                )
            except Exception:
                pass

            # Дополнительная пауза, чтобы все редиректы и AJAX отработали
            page.wait_for_timeout(2500)

            html = page.content()
            final_url = page.url
        except Exception as e:
            log.warning(f"playwright article fetch failed: {e}")
            return None, None
        finally:
            browser.close()

    return html, final_url