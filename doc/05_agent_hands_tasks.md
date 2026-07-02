# Вебінар: специфікація «Отримання даних» (таски)

Це деталізація **лівої половини** пайплайна агента — від резюме до відсортованого шортліста.
«Руки» агента (відправка листів) — окремий документ.

## Принципи

- Пайплайн: **parse → reason** (без `remember` — БД не потрібна, стан живе як список об'єктів у пам'яті ноутбука).
- Одне джерело, один запит. Без дедуплікації, без поєднання джерел, без ORM.
- Чиста структура навіть у Jupyter: `core/` нічого не знає про світ; `connectors/` торкаються світу; ноутбук — диригент.
- **Розширюваність через порти.** Джерело вакансій, відправка й отримання повідомлень — це *інтерфейси* (`typing.Protocol`) у `core/ports.py`; конкретні конектори — адаптери, що їх реалізують. Заміна джерела (HN → український борд) чи каналу (email → веб-форма) = новий адаптер, без змін у ядрі та циклі агента.
- Що можна без LLM — робимо без LLM.
- Провайдер: Google Gemini через `google-genai` + `instructor` (крос-провайдерність зберігається).

## Структура

```
core/                    # домен, без I/O
  models.py              # CandidateProfile, SearchPreferences, Vacancy, MatchResult
  ports.py               # інтерфейси (Protocol): VacancySource,
                         # MessageSender, MessageReceiver
  logic.py               # без LLM: rejection_reason() (фільтр) +
                         # missing_fields()/has_enough_info() (повнота даних)
connectors/              # адаптери, що реалізують порти
  resume_loader.py       # pypdf: PDF → текст
  vacancy_source.py      # DouSource(VacancySource): httpx + bs4 → jobs.dou.ua (з пагінацією)
  llm.py                 # instructor + genai/mistral: текст → моделі ядра (з фолбеком)
notebooks/
  part1_agent_sees.ipynb # диригент
data/
  resume.pdf
```

## Залежності

```
uv add pydantic pypdf httpx google-genai instructor "mistralai<2" beautifulsoup4 python-dotenv
```
`.env`: `GOOGLE_API_KEY=...`, `MISTRAL_API_KEY=...` (Mistral — крос-провайдерний фолбек; `mistralai` має бути `<2`, бо instructor 1.15.x чекає API SDK 1.x).

## Моделі LLM

| Крок | Модель | Призначення |
|---|---|---|
| Екстракція (резюме, вакансії) | `gemini-3.1-flash-lite` | дешево, механічно |
| Матчинг | `gemini-3.5-flash` | судження з поясненням |

> **Достатність даних рахуємо алгоритмічно** (`core/logic.py`, без LLM): після
> структурування у Task 6 «чи є вилка/формат/стек» — це детермінована перевірка
> полів `Vacancy`, а не судження. LLM лишаємо лише там, де потрібен reasoning
> (матчинг). Кожен LLM-крок має крос-провайдерний фолбек (Gemini → Mistral).

---

# Task P — Підготовка (зробити ДО роботи з кодом)

**Мета:** а зараз — нічого не кодимо; збираємо все, без чого перша ж клітинка не запуститься.

**Пояснення:** усі зовнішні доступи й артефакти готуємо заздалегідь, бо частину з них видають не миттєво (ключі, App-пароль, баланс). Жоден секрет не потрапляє в код чи репозиторій — лише у `.env` через змінні оточення.

**Чеклист:**

1. **Окремий Gmail для агента** — персональний (не Workspace), напр. `job.agent.demo@gmail.com`. Свіжа порожня скринька → чисте демо.
2. **App Password Gmail** — увімкнути 2-Step Verification → згенерувати 16-значний App Password (Mail). Без 2FA екран паролів не з'явиться.
   - Перевірити, що мережа майданчика не блокує порт 587 (SMTP) і 993 (IMAP).
3. **Ключ Gemini з балансом** — отримати API-ключ Google AI Studio; переконатися, що на проєкті ввімкнено білінг / є кредит під виклики демо (екстракція + матчинг + генерація листів).
4. **Джерело вакансій** — jobs.dou.ua. Зібрати кеш HTML сторінок вакансій у `fixtures/` (фолбек). Зберегти з браузера `sessionid` та `csrftoken` для можливості відправки відгуків через форму.
5. **Резюме** — покласти `data/resume.pdf` (реальне або демо-резюме «поручителя»).
6. **Mailtrap (опційно, фолбек)** — sandbox-скринька на випадок проблем із живим Gmail на ефірі.
6. **Оточення** — Python 3.14 + uv; `uv add pydantic pypdf httpx google-genai instructor "mistralai<2" beautifulsoup4 python-dotenv`.
8. **Каркас репозиторію** — пакети `core/` і `connectors/`, тека `data/`, `notebooks/`, `fixtures/`.
9. **`.env` + `.gitignore`** — секрети у `.env`, `.env` у `.gitignore` (у публічний репозиторій не потрапляє).

**Результат — `.env` (шаблон):**

```dotenv
# .env  (НЕ комітити)
GOOGLE_API_KEY=...
MISTRAL_API_KEY=...              # крос-провайдерний фолбек
AGENT_EMAIL=job.agent.demo@gmail.com
GMAIL_APP_PASSWORD=...           # 16 символів, без пробілів
DOU_SESSIONID=...                # з Cookies браузера
DOU_CSRFTOKEN=...                # з Cookies браузера
```

```gitignore
# .gitignore
.env
data/*.pdf
__pycache__/
```

---

# Task 0 — Каркас: середовище і структура

**Мета:** а зараз ми підготуємо чистий каркас — пакети `core/` та `connectors/`, щоб код одразу був структурованим, а не «купою клітинок».

**Пояснення:** ми розкладаємо код на ядро (моделі + чиста логіка, без мережі й LLM) і конектори (усе, що торкається світу). Так ядро можна тестувати без жодного виклику, а конектори — міняти незалежно. Це той самий принцип «двох типів конекторів», тільки оформлений як пакети.

**Результат:**

```python
# клітинка ноутбука: робимо пакети імпортованими
import sys, pathlib
sys.path.append(str(pathlib.Path.cwd()))

from dotenv import load_dotenv
load_dotenv()  # підтягує GOOGLE_API_KEY з .env
```

---

# Task 1 — Резюме: PDF → текст

**Мета:** а зараз ми завантажимо резюме з PDF і перетворимо його на звичайний текст.

**Пояснення:** беремо `pypdf` — чистий Python, нуль системних залежностей, найпростіший для старту. Текст вийде трохи «брудний» (втрачене форматування, склеєні колонки) — і це нормально: далі його чистить LLM. Тобто ідеальна екстракція нам не потрібна, нам потрібен *хоч якийсь* текст.

**Результат:**

```python
# connectors/resume_loader.py
from pypdf import PdfReader

def load_resume_text(path: str) -> str:
    reader = PdfReader(path)
    return "\n".join(page.extract_text() or "" for page in reader.pages)
```

```python
# клітинка
from connectors.resume_loader import load_resume_text

resume_text = load_resume_text("data/resume.pdf")
print(resume_text[:500])  # бачимо «сирий» текст
```

---

# Task 2 — Моделі ядра

**Мета:** а зараз ми опишемо, *що саме* хочемо знати — як Pydantic-моделі.

**Пояснення:** схема — це не «обгортка над даними», а формулювання задачі: «ось поля, які мають значення». `CandidateProfile` — хто пошукач (з резюме). `SearchPreferences` — чого він хоче (заповнює сам, бо в резюме цього нема). `Vacancy` — куди парсимо оголошення; `apply_url` тут ключове, бо це вхід для «рук» агента. `MatchResult` — наскільки вакансія підходить; повноту даних рахуємо окремо й **алгоритмічно** (`core/logic.missing_fields`), не моделлю.

**Результат:**

```python
# core/models.py
from enum import Enum
from pydantic import BaseModel, Field


class WorkFormat(str, Enum):
    onsite = "onsite"
    hybrid = "hybrid"
    remote = "remote"


class CandidateProfile(BaseModel):
    """Хто пошукач — витягуємо з резюме."""
    full_name: str | None = None
    title: str | None = None              # "Python Backend Developer"
    years_experience: float | None = None
    seniority: str | None = None          # junior / middle / senior
    tech_stack: list[str] = Field(default_factory=list)
    summary: str | None = None


class SearchPreferences(BaseModel):
    """Чого хоче пошукач — заповнює руками (в резюме цього нема)."""
    desired_roles: list[str]
    min_salary: int | None = None
    work_formats: list[WorkFormat] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    must_have: list[str] = Field(default_factory=list)      # обов'язкові умови
    deal_breakers: list[str] = Field(default_factory=list)  # стоп-слова


class Vacancy(BaseModel):
    """Куди парсимо оголошення."""
    company: str | None = None
    role: str | None = None
    location: str | None = None
    work_format: WorkFormat | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    tech_stack: list[str] = Field(default_factory=list)
    posting_language: str | None = None   # ISO 639-1 мови оголошення — щоб відповісти тією ж
    apply_url: str | None = None          # ключове для "рук" агента (URL вакансії на DOU)
    source_url: str | None = None
    raw_text: str = ""                     # оригінал; заповнюємо кодом, не LLM


class MatchResult(BaseModel):
    """Наскільки вакансія підходить пошукачу."""
    score: int = Field(ge=0, le=100)
    reasons: list[str] = Field(default_factory=list)
```

Поряд — **порти** (контракти, які реалізують конектори). Ядро залежить від них, а не від конкретного Gmail чи HN:

```python
# core/ports.py
from __future__ import annotations
from datetime import datetime
from typing import Protocol

from core.models import Attachment, IncomingMessage

class VacancySource(Protocol):
    """Будь-яке джерело вакансій повертає сирі тексти оголошень."""
    def fetch(self, limit: int = 15) -> list[str]: ...

class MessageSender(Protocol):
    """Канал відправки: email, веб-форма борду тощо."""
    def send(
        self,
        to: str,
        subject: str,
        body: str,
        attachments: list[Attachment] | None = None,   # ← резюме, портфоліо тощо
    ) -> None: ...

class MessageReceiver(Protocol):
    """Канал отримання (опціонально; деякі джерела його не мають)."""
    def fetch_unread(self, limit: int = 5) -> list[IncomingMessage]: ...

# ── Календар (заглушка-порт для майбутньої інтеграції) ────────────

class CalendarProvider(Protocol):
    """Доступ до календаря для узгодження зустрічей.

    Локальний календар (LocalCalendar) уже реалізує цю логіку
    неявно; коли підключимо Google Calendar — створимо адаптер,
    що реалізує цей порт.
    """
    def is_available(self, dt: datetime) -> bool: ...
    def next_free_slot(self, after: datetime) -> datetime: ...
    def create_event(self, title: str, start: datetime, end: datetime) -> str: ...
```

> **Attachment** — файл-вкладення (резюме, портфоліо). `MessageSender.send()` приймає `attachments` опціонально — адаптери, що не підтримують файли (наприклад, форма DOU), просто ігнорують цей параметр.
>
> **IncomingMessage** — типізована заміна `dict` у `MessageReceiver.fetch_unread()`. Тепер вхідні листи мають явну структуру: `sender`, `subject`, `body`, `attachments`.
>
> **CalendarProvider** — порт для майбутньої інтеграції з Google Calendar. Наразі `LocalCalendar` (Task 15) неявно реалізує цей контракт; для реального календаря потрібен OAuth-адаптер.

---

# Task 3 — LLM-конектор + перша екстракція (резюме)

**Мета:** а зараз ми зробимо конектор до LLM і вперше перетворимо сирий текст резюме на типізований `CandidateProfile`.

**Пояснення:** спершу варто показати механіку «руками» — промпт повертає JSON-рядок, ми робимо `CandidateProfile.model_validate_json(...)`. Видно, що ніякої магії нема. Потім підключаємо `instructor`: він патчить клієнт `genai`, сам просить структуровану відповідь, валідує її в нашу модель і ретраїть при невдачі. Це «чистий» спосіб, і він крос-провайдерний — провайдера міняємо в одному місці.

> Звірити точний конструктор `instructor.from_genai(...)` / `mode` при першому запуску — інтеграція instructor↔genai інколи змінюється між версіями.

**Результат:**

```python
# connectors/llm.py
import os
import instructor
from google import genai
from pydantic import BaseModel

_gemini = instructor.from_genai(genai.Client(api_key=os.environ["GOOGLE_API_KEY"]))

EXTRACT_MODEL = "gemini-3.1-flash-lite"


def extract[T: BaseModel](
    text: str,
    schema: type[T],
    instruction: str,
    model: str = EXTRACT_MODEL,
) -> T:
    """Сирий текст → екземпляр Pydantic-моделі."""
    return _gemini.chat.completions.create(
        model=model,
        response_model=schema,
        messages=[
            {"role": "user", "content": f"{instruction}\n\n---\n{text}"},
        ],
    )
```

> Це базова версія для розуміння instructor. У фінальному `connectors/llm.py` `extract` іде через `_call_with_fallback` — ретраї з backoff + **крос-провайдерний фолбек Gemini→Mistral** (поряд із `_gemini` є `_mistral = instructor.from_provider("mistral/...")`); для суджень є `JUDGE_MODEL="gemini-3.5-flash"`. Деталі — у наступних тасках і самому файлі.

```python
# клітинка
from connectors.llm import extract
from core.models import CandidateProfile

profile = extract(
    resume_text,
    CandidateProfile,
    instruction=(
        "Витягни профіль кандидата з тексту резюме. "
        "Якщо поля нема — лиши None або порожній список."
    ),
)
profile
```

---

# Task 4 — Побажання пошукача (ручний ввід)

**Мета:** а зараз ми задамо те, чого нема в резюме — побажання до вакансії.

**Пояснення:** агенту потрібні дані, яких нема в жодному документі: бажана вилка, формат, стоп-умови. Їх дає людина — просто інстанціюємо модель значеннями в клітинці. Це найпростіший шлях (YAML — зайва ланка для демо), і він наочно показує: частину контексту в агента вкладає саме людина. Це природний місток до approval gate у частині 2.

**Результат:**

```python
# клітинка
from core.models import SearchPreferences, WorkFormat

prefs = SearchPreferences(
    desired_roles=["Python Backend Developer", "Backend Engineer"],
    min_salary=4000,
    work_formats=[WorkFormat.remote, WorkFormat.hybrid],
    locations=["Europe", "Remote"],
    must_have=["Python"],
    deal_breakers=["unpaid", "internship"],
)
prefs
```

---

# Task 5 — Джерело вакансій (DOU)

**Мета:** а зараз ми заберемо реальні оголошення з jobs.dou.ua.

**Пояснення:** беремо DOU, бо це найпопулярніший майданчик в Україні. Запит — GET до сторінки пошуку. Кожне оголошення — HTML-текст. Ми використаємо `BeautifulSoup` для очищення базових тегів, щоб передати чистіший текст у LLM. Це ідеальний матеріал для «Парсинг 2.0».

**Результат:**

```python
# connectors/vacancy_source.py
import httpx
from bs4 import BeautifulSoup
from core.ports import VacancySource   # реалізуємо цей контракт

# DOU віддає інший контент без браузерного User-Agent — підставляємо реалістичний
_HEADERS = {"User-Agent": "Mozilla/5.0 (...) Chrome/124.0 Safari/537.36"}

class DouSource:
    """VacancySource на базі jobs.dou.ua. Отримує HTML і витягує текст."""
    LIST_URL = "https://jobs.dou.ua/vacancies/?category=Python"

    def fetch(self, limit: int = 15) -> list[str]:
        resp = httpx.get(self.LIST_URL, headers=_HEADERS, timeout=30, follow_redirects=True)
        soup = BeautifulSoup(resp.text, "html.parser")
        # ЧОМУ a.vt (звірено з реальним HTML): старий селектор
        # "div.vacancy div.title a.vt" застарів і дає 0 збігів.
        links = [a["href"] for a in soup.select("a.vt")][:limit]

        texts = []
        for link in links:
            v_resp = httpx.get(link, headers=_HEADERS, timeout=30, follow_redirects=True)
            v_soup = BeautifulSoup(v_resp.text, "html.parser")
            body = v_soup.select_one(".b-typo.vacancy-section")
            text = body.get_text(separator=" ", strip=True) if body else ""
            texts.append(f"URL: {link}\n\n{text}")

        return texts

_check: VacancySource = DouSource()   # статична перевірка: клас задовольняє порт
```

> Фінальний `connectors/vacancy_source.py` додає до цього: **пагінацію** `start_page`/`stop_page` (наступні сторінки — POST на `…/xhr-load/` з `csrfmiddlewaretoken`+`count`, порції перекриваються → дедуп) і **кеш-фолбек** `use_cache=True` (знімок у `fixtures/dou_vacancies.json`). Не всі вакансії «internal»: «external» (`.replied-external`) ведуть на сайт компанії.

```python
# клітинка
from connectors.vacancy_source import DouSource

source = DouSource()
raw_postings = source.fetch(limit=5) # для демо беремо 5, щоб не чекати довго

print(f"оголошень: {len(raw_postings)}")
print(raw_postings[0][:600])  # сирий текст з URL на початку
```

---

# Task 6 — Вакансії → list[Vacancy]

**Мета:** а зараз ми перетворимо кожне сире оголошення на типізовану `Vacancy` — тією самою технікою, що й резюме.

**Пояснення:** це і є момент «ага»: екстракція резюме і екстракція вакансії — *один і той самий* інструмент (`extract`), просто інша схема. Просимо модель витягти й `apply_url`, і визначити `posting_language` (мову оголошення — нею писатимемо лист у ч.2), і зберегти оригінал у `raw_text` (знадобиться далі для листа). Прогін по кількох оголошеннях — щоб бачити таблицю.

**Результат:**

```python
# клітинка
from core.models import Vacancy

VACANCY_INSTRUCTION = (
    "Витягни структуровані дані вакансії з тексту оголошення. "
    "Обов'язково знайди URL вакансії (apply_url), який вказаний на початку тексту. "
    "Визнач мову оголошення (posting_language, ISO 639-1: 'uk', 'en'...). "
    "Поле raw_text залиш порожнім — його заповнить код. "
    "Якщо поля нема — None або порожній список."
)

vacancies: list[Vacancy] = []
for text in raw_postings:
    v = extract(text, Vacancy, instruction=VACANCY_INSTRUCTION)
    v.raw_text = text  # гарантуємо оригінал
    vacancies.append(v)

# швидкий огляд
for v in vacancies[:5]:
    print(v.company, "|", v.role, "|", v.apply_url)
```

---

# Task 7 — Алгоритмічний фільтр (без LLM)

**Мета:** а зараз ми дешево, без LLM, відсіємо очевидно невідповідні вакансії.

**Пояснення:** що можна вирішити детерміновано — вирішуємо кодом: це безкоштовно, миттєво й економить виклики LLM на тих, де відповідь і так зрозуміла. Перевіряємо стоп-слова, невідповідність формату, вилку нижче порогу та відсутність обов'язкового (`must_have`) скіла кандидата в тексті. **Грубий скіл-геп проти всього стеку кандидата свідомо НЕ робимо** — він легко викидає придатну вакансію через синонім («JS» vs «JavaScript»); тонке «наскільки підходить» — робота LLM-матчингу (Task 9).

**Результат:**

```python
# core/logic.py
from core.models import Vacancy, SearchPreferences, CandidateProfile


def rejection_reason(
    v: Vacancy,
    prefs: SearchPreferences,
    profile: CandidateProfile,
) -> str | None:
    """Причину відсіву або None, якщо вакансія проходить далі."""
    text = (v.raw_text or "").lower()

    # стоп-слова
    for word in prefs.deal_breakers:
        if word.lower() in text:
            return f"deal-breaker: {word!r}"

    # формат роботи (відсіваємо лише коли формат вакансії відомий)
    if prefs.work_formats and v.work_format and v.work_format not in prefs.work_formats:
        return f"формат {v.work_format.value} не серед бажаних"

    # вилка нижче порогу (порівнюємо лише коли число відоме)
    if prefs.min_salary and v.salary_max and v.salary_max < prefs.min_salary:
        return f"вилка {v.salary_max} < мінімум {prefs.min_salary}"

    # обов'язкові умови кандидата: must-have skill узагалі не згадано в тексті
    for skill in prefs.must_have:
        if skill.lower() not in text:
            return f"немає обов'язкового: {skill!r}"

    return None
```

```python
# клітинка
from core.logic import rejection_reason

survivors = []
for v in vacancies:
    reason = rejection_reason(v, prefs, profile)
    if reason:
        print(f"✗ {v.company}: {reason}")
    else:
        survivors.append(v)

print(f"\nпройшли фільтр: {len(survivors)} з {len(vacancies)}")
```

---

# Task 8 — Повнота даних (алгоритмічно)

**Мета:** а зараз ми для кожної вакансії перевіримо, чи достатньо в ній даних, щоб брати її в шортліст, — і запам'ятаємо, чого бракує.

**Пояснення:** після Task 6 дані вже структуровані в поля `Vacancy`, тож «чи є вилка/формат/стек» — це **факт** (поле `is None`), а не судження. За принципом Task 7 робимо це **алгоритмічно** в `core/logic.py`, без LLM: дешево, миттєво, надійно. Достатність — **не жорсткі ворота**: вакансію з невеликим gap (1–2 порожні поля) усе одно беремо в шортліст, а `missing` запам'ятовуємо — у частині 2 ці поля стануть **питаннями в кінці мотиваційного листа** (окремої гілки «уточнюючий лист» більше немає).

**Результат:**

```python
# core/logic.py — додаємо
from core.models import Vacancy, SearchPreferences

def missing_fields(v: Vacancy, prefs: SearchPreferences) -> list[str]:
    """Які важливі для рішення поля порожні — детерміновано, без LLM."""
    gaps: list[str] = []
    if prefs.min_salary and not (v.salary_min or v.salary_max):
        gaps.append("зарплатна вилка")
    if prefs.work_formats and v.work_format is None:
        gaps.append("формат роботи")
    if prefs.locations and not v.location:
        gaps.append("локація")
    if not v.tech_stack:
        gaps.append("стек технологій")
    return gaps

def has_enough_info(v: Vacancy, prefs: SearchPreferences, max_gap: int = 2) -> bool:
    """Чи брати вакансію в шортліст (невеликий gap — усе одно беремо)."""
    return len(missing_fields(v, prefs)) <= max_gap
```

```python
# клітинка
from core.logic import missing_fields, has_enough_info

# (вакансія, чого бракує) — gap зберігаємо, він стане питаннями в листі (ч.2)
shortlist_candidates: list[tuple[Vacancy, list[str]]] = []
for v in survivors:
    gaps = missing_fields(v, prefs)
    if has_enough_info(v, prefs):
        shortlist_candidates.append((v, gaps))

print(f"у шортлисті: {len(shortlist_candidates)} з {len(survivors)}")
```

---

# Task 9 — Матчинг (LLM, головне судження)

**Мета:** а зараз ми для вакансій із шортлиста оцінимо, наскільки вони підходять, і відсортуємо шортліст.

**Пояснення:** це головне судження пайплайна, тому беремо `JUDGE_MODEL` — reasoning-модель. **«Мислення» вмикається саме вибором моделі** (judge аналізує, на відміну від легкої extract-моделі), а не низькорівневим параметром. Модель повертає `score` і `reasons` — пояснення «чому», яке робить рішення прозорим для людини. Сортуємо за score: на виході — впорядкований шортліст з причинами.

> **Чому не `thinking_config`/`thinking_budget`:** Gemini дозволяє керувати бюджетом мислення через `GenerateContentConfig`, але цей параметр **провайдер-специфічний** (genai-only) — він зламав би наш крос-провайдерний фолбек на Mistral. Тому «мислення» реалізуємо переносимо: вибором моделі. Виклик іде через `_call_with_fallback` (як і решта), тож фолбек Gemini → Mistral працює і тут.

**Результат:**

```python
# connectors/llm.py — додаємо
from core.models import MatchResult

def score_match(vacancy_raw: str, profile_summary: str, prefs_summary: str) -> MatchResult:
    instruction = (
        "Оціни відповідність вакансії кандидату за шкалою 0..100 "
        "і поясни причини.\n"
        f"Кандидат: {profile_summary}\n"
        f"Пріоритети: {prefs_summary}"
    )
    return _call_with_fallback(
        schema=MatchResult, model=JUDGE_MODEL,
        messages=[{"role": "user", "content": f"{instruction}\n\n---\n{vacancy_raw}"}],
    )
```

```python
# клітинка
profile_summary = f"{profile.title}, {profile.seniority}, стек: {profile.tech_stack}"

# зберігаємо gap поряд зі score — він знадобиться для питань у листі (ч.2)
shortlist: list[tuple[Vacancy, MatchResult, list[str]]] = []
for v, gaps in shortlist_candidates:
    m = score_match(v.raw_text, profile_summary, prefs_summary)
    shortlist.append((v, m, gaps))

shortlist.sort(key=lambda t: t[1].score, reverse=True)

for v, m, gaps in shortlist:
    flag = f"  (уточнити: {gaps})" if gaps else ""
    print(f"{m.score:>3}  {v.company} — {v.role}{flag}")
    for r in m.reasons:
        print(f"      • {r}")
```

---

## Стан на виході (кінець частини 1)

У пам'яті ноутбука:
- `profile: CandidateProfile`, `prefs: SearchPreferences`
- `shortlist: list[tuple[Vacancy, MatchResult, list[str]]]` — впорядкований за score; третій елемент — `missing` (чого бракує) для питань у листі

Це вхід для «рук» агента (частина 2): беремо топ `shortlist`; для кожної вакансії генеруємо мотиваційний лист, а якщо її `missing` непорожній — додаємо в кінець питання по цих полях. Окремої гілки «уточнюючий лист» немає: уточнення вбудоване в мотиваційний лист.

### Снапшот стану для частини 2

Дві зустрічі — різні дні й різні ноутбуки, а БД ми свідомо не заводили. Тому в кінці частини 1 серіалізуємо стан у простий JSON (не БД — лише `model_dump`), а частина 2 його завантажує. Якщо стан не зберігся — частина 2 просто переганяє пайплайн ч.1 заново (recap-блок).

```python
# клітинка — кінець частини 1
import json
snapshot = {
    "profile": profile.model_dump(),
    "prefs": prefs.model_dump(),
    "shortlist": [
        {"vacancy": v.model_dump(), "match": m.model_dump(), "missing": gaps}
        for v, m, gaps in shortlist
    ],
}
with open("data/state.json", "w") as f:
    json.dump(snapshot, f, ensure_ascii=False, indent=2, default=str)
```

## Кліфхенгер

Агент має впорядкований шортліст і *знає, чого бракує* в кожній вакансії (`missing`) — але ще не вміє нічого з цим зробити: ні відгукнутися, ні спитати про вилку. У частині 2 дамо йому «руки».
