"""
Джерело вакансій з jobs.dou.ua — конектор «світ → LLM».

Реалізує порт VacancySource (core/ports.py): fetch(limit) -> list[str].
Кожен елемент — сирий текст оголошення з URL на початку (далі LLM витягне
його в apply_url у Task 6).

Пагінація DOU:
- Сторінка 1 — звичайний GET сторінки списку (перші ~20 карток у статичному HTML).
- Наступні сторінки — AJAX: POST на .../xhr-load/ з csrf-токеном і count (offset
  уже показаних карток). GET туди повертає 405, тому саме POST.
За замовчуванням беремо лише сторінку 1 (start_page=stop_page=1) — як було раніше.
Діапазон start_page..stop_page дозволяє пройти більше сторінок; порції xhr-load
перекриваються, тому лінки дедуплікуємо.

Надійність на демо: кожен успішний живий запит ми кешуємо у fixtures/, і за
потреби (збій мережі / DOU блокує) читаємо знімок звідти — прапорець use_cache.
"""

import json
import pathlib

import httpx
from bs4 import BeautifulSoup

from core.ports import VacancySource  # реалізуємо цей контракт

# DOU віддає інший контент клієнту без браузерного User-Agent — підставляємо реалістичний.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

# Кеш-знімок поруч із рештою фікстур (fixtures/ у .gitignore — це локальний фолбек).
_CACHE = pathlib.Path(__file__).resolve().parent.parent / "fixtures" / "dou_vacancies.json"


class DouSource:
    """VacancySource на базі jobs.dou.ua: список вакансій → текст кожної."""

    LIST_URL = "https://jobs.dou.ua/vacancies/?category=Python"
    XHR_URL = "https://jobs.dou.ua/vacancies/xhr-load/?category=Python"
    PAGE_SIZE = 20  # скільки карток DOU показує на «сторінку» (offset для xhr-load)

    def __init__(
        self,
        use_cache: bool = False,
        start_page: int = 1,
        stop_page: int = 1,
    ) -> None:
        # use_cache=True — читаємо збережений знімок замість мережі (фолбек на демо).
        # start_page..stop_page — діапазон сторінок списку (1-based, включно).
        if start_page < 1 or stop_page < start_page:
            raise ValueError("очікується 1 <= start_page <= stop_page")
        self.use_cache = use_cache
        self.start_page = start_page
        self.stop_page = stop_page

    def fetch(self, limit: int = 15) -> list[str]:
        """Повертає список сирих текстів оголошень (URL на початку кожного)."""
        if self.use_cache and _CACHE.exists():
            return json.loads(_CACHE.read_text(encoding="utf-8"))[:limit]

        texts = self._fetch_live(limit)
        self._save_cache(texts)  # зберігаємо знімок для майбутнього фолбеку
        return texts

    def _fetch_live(self, limit: int) -> list[str]:
        """Збираємо лінки зі сторінок діапазону, потім текст кожної вакансії."""
        # Один Client на всю сесію: тримає cookies (csrftoken потрібен для xhr-load).
        with httpx.Client(headers=_HEADERS, timeout=30, follow_redirects=True) as client:
            links = self._collect_links(client)[:limit]

            texts: list[str] = []
            for link in links:
                v_resp = client.get(link)
                body = BeautifulSoup(v_resp.text, "html.parser").select_one(
                    ".b-typo.vacancy-section"
                )
                # body може бути None (нестандартна сторінка) — тоді лишаємо порожній
                # текст, але URL зберігаємо завжди: він потрібен «рукам» агента (ч.2).
                text = body.get_text(separator=" ", strip=True) if body else ""
                texts.append(f"URL: {link}\n\n{text}")

        return texts

    def _collect_links(self, client: httpx.Client) -> list[str]:
        """Лінки на вакансії зі сторінок start_page..stop_page (дедупльовані)."""
        # Завжди робимо GET сторінки 1: він дає cookies (csrftoken) для xhr-load
        # і заразом є контентом першої сторінки.
        first_html = client.get(self.LIST_URL).text
        csrf = client.cookies.get("csrftoken", "")

        links: list[str] = []
        seen: set[str] = set()
        for page in range(self.start_page, self.stop_page + 1):
            if page == 1:
                html = first_html
            else:
                # ЧОМУ POST: пагінація DOU — AJAX (GET сюди повертає 405).
                # count = offset уже показаних карток = (page - 1) * PAGE_SIZE.
                resp = client.post(
                    self.XHR_URL,
                    data={
                        "csrfmiddlewaretoken": csrf,
                        "count": str((page - 1) * self.PAGE_SIZE),
                    },
                    headers={"X-Requested-With": "XMLHttpRequest", "Referer": self.LIST_URL},
                )
                html = resp.json().get("html", "")

            for a in BeautifulSoup(html, "html.parser").select("a.vt"):
                href = a["href"]
                if href not in seen:  # дедуплікація: сусідні xhr-порції перекриваються
                    seen.add(href)
                    links.append(href)

        return links

    def _save_cache(self, texts: list[str]) -> None:
        _CACHE.parent.mkdir(exist_ok=True)
        _CACHE.write_text(json.dumps(texts, ensure_ascii=False, indent=2), encoding="utf-8")


_check: VacancySource = DouSource()  # статична перевірка: клас задовольняє порт
