# Вебінар: специфікація «Руки агента» (таски)

Це деталізація **правої половини** пайплайна — від готового шортліста (вихід частини 1) до дій у світі.
Вхід: `shortlist` (кожен елемент несе `missing` — чого бракує), `profile`, `prefs` — усе в пам'яті ноутбука.

## Принципи

- **Руки окремо, голова окремо.** Конектори (`GmailSender`, `ImapReceiver`, календар) — німий I/O, нічого не вирішують. Рішення «чи діяти» приймає цикл агента; дозвіл дає людина (approval gate).
- **Адаптери портів.** Відправка й отримання реалізують `MessageSender` / `MessageReceiver` з `core/ports.py`. Email — один адаптер; веб-форма українського борду — інший (`FormSender`), з тим самим методом `send()`. Зміна каналу = новий клас, без змін у ядрі та циклі.
- **Вкладення (attachments).** `MessageSender.send()` приймає опціональний `attachments: list[Attachment]` — файли (резюме, портфоліо), які адаптер долучає до повідомлення. Адаптери, що не підтримують файли (наприклад, форма DOU), просто ігнорують цей параметр.
- **Типізовані вхідні повідомлення.** `MessageReceiver.fetch_unread()` повертає `list[IncomingMessage]` замість `list[dict]` — з явними полями `sender`, `subject`, `body`, `attachments`.
- **Що детерміноване — без LLM.** Повнота даних вакансії (`missing_fields`) і планування слотів — чистий Python у `core/logic`. LLM лише витягує дані з вільного тексту й генерує тексти листів.
- **wow = реальний відгук та лист.** Відправка первинного відгуку йде через закритий API DOU (за допомогою нашого хелпера). А відповіді від роботодавця прилітають на вказаний Gmail, з яким ми працюємо через IMAP.
- Стан — у пам'яті (без БД). Календар — локальний об'єкт (варіант A); реальний Google Calendar — камео в кінці.

## Облік і доступи (зробити заздалегідь)

- Окремий персональний Gmail (напр. `job.agent.demo@gmail.com`), **не** Workspace.
- Увімкнена 2-Step Verification → згенерований App Password (16 символів).
- `.env`: `AGENT_EMAIL=...`, `GMAIL_APP_PASSWORD=...`, `DOU_SESSIONID=...`, `DOU_CSRFTOKEN=...`; `.env` у `.gitignore`.
- На демо ми показуємо реальний відгук на DOU (або мокуємо його відправку, якщо вакансія не тестова), а для другої частини імітуємо отримання листа-відповіді від "роботодавця" на наш Gmail.

## Структура (доповнення до частини 1)

```
core/
  models.py      # + EmailDraft, ReplyAnalysis, InterviewProposal, SlotDecision
                 #   (Attachment, IncomingMessage вже були в ч.1)
  ports.py       # MessageSender (+ attachments), MessageReceiver (→ IncomingMessage),
                 #   CalendarProvider
  logic.py       # + resolve_slot(); apply_reply_updates(); match_reply_to_vacancy()
                 #   (next_free_slot — це метод LocalCalendar, не logic)
  calendar.py    # LocalCalendar (варіант A): зайняті слоти + робочі години + create_event
connectors/
  dou_form.py    # DouFormSender(MessageSender) — обгортка над dou_helper (dry_run)
  email.py       # ImapReceiver + MockReceiver (MessageReceiver) та GmailSender (dry_run)
  gcal.py        # камео: реальний GoogleCalendar(CalendarProvider) через OAuth
```

## Моделі LLM (ті самі, що в ч.1)

| Крок | Модель | Призначення |
|---|---|---|
| Генерація листа | `gemini-3.5-flash` (`JUDGE_MODEL`) | мотиваційний текст + питання по gap |
| Екстракція з відповіді | `gemini-3.1-flash-lite` (`EXTRACT_MODEL`) | дані уточнення / дата-час запрошення |
| Рішення в циклі агента | `gemini-3.5-flash` + tool use | який інструмент викликати |

> Усі виклики — через `_call_with_fallback` (фолбек Gemini → Mistral). Повнота
> даних рахується алгоритмічно ще в ч.1 (`core/logic.missing_fields`), тож тут
> LLM-кроку «достатність» немає.

---

# ОБОВ'ЯЗКОВЕ: відгук

## Task 10 — Конектор форми: DouFormSender (відгук)

**Мета:** а зараз ми навчимо агента робити відгук на DOU — спершу безпечно (мок), з готовністю до реального POST.

**Пояснення:** конектор робить рівно одне — викликає `dou_helper.apply_for_vacancy()`. Він «німий»: не вирішує, кому й коли слати, не питає підтвердження. Так руки відокремлені від голови (одне місце з реальним сайд-ефектом). Оформлюємо як клас-адаптер `DouFormSender`, що реалізує порт `MessageSender`. Низькорівневий HTTP (POST на форму, куки `sessionid`/`csrftoken`, поля `descr`/`user_cv`/csrf) схований у `helpers/dou_helper.py`.

> **Структура форми відгуку (розвідано на реальній internal-вакансії):** кнопка «Откликнуться» відкриває приховану форму, яка POST-иться на URL вакансії з полями `csrfmiddlewaretoken`, `descr` (текст) і `user_cv` (файл резюме, опційно). Не всі вакансії internal: «external» ведуть на сайт компанії — для них форма не діє.
>
> **dry_run** (безпечний дефолт): `DouFormSender(dry_run=True)` нічого не шле, лише друкує, що відправив би. Реальний відгук — `dry_run=False`. На вебінарі тримаємо мок, поки немає активної тестової вакансії; реальну відправку показуємо одним перемиканням прапорця.

**Результат:**

```python
# connectors/dou_form.py
import os
from core.models import Attachment
from core.ports import MessageSender
from helpers import dou_helper

class DouFormSender:
    """MessageSender для відгуку на DOU. Тонкий I/O, жодних рішень."""

    def __init__(self, dry_run: bool = True) -> None:
        self.dry_run = dry_run   # МОК за замовчуванням — безпечно

    def send(
        self,
        to: str,
        subject: str,
        body: str,
        attachments: list[Attachment] | None = None,
    ) -> None:
        # 'to' = URL вакансії; 'subject' ігноруємо (форма має лише текст);
        # перший attachment -> user_cv (резюме)
        cv_path = attachments[0].path if attachments else None
        dou_helper.apply_for_vacancy(
            url=to, message=body,
            sessionid=os.environ["DOU_SESSIONID"],
            csrftoken=os.environ["DOU_CSRFTOKEN"],
            cv_path=cv_path, dry_run=self.dry_run,
        )

_check: MessageSender = DouFormSender()   # статична перевірка контракту
```

---

## Task 11 — Лист від AI-агента (мотивація + питання по gap)

**Мета:** а зараз ми згенеруємо яскравий лист на вакансію зі шортлиста — **від імені AI-агента** кандидата, мовою оголошення, з питаннями по `gap` у кінці.

**Пояснення:** головна фішка — лист пише **не кандидат, а його персональний AI-агент**, і це навмисно видно з тексту. Сам факт наявності такого агента — сигнал технічної кмітливості кандидата (саме того, чого вчить вебінар), тому тон яскравий і живий. Лист пишемо **мовою оголошення** (`posting_language` з Task 6). Окремої гілки «уточнюючий лист» немає (див. оновлений Task 8): `missing` лише підмішує блок питань у кінець. LLM відповідає за *текст* і *мову*, не за рішення слати; поле `to` ставимо кодом (`apply_url`). Повертаємо `EmailDraft`, щоб людина бачила його до відправки.

**Результат:**

```python
# core/models.py — додаємо
from pydantic import BaseModel

class EmailDraft(BaseModel):
    to: str = ""             # ставимо кодом (apply_url), не покладаючись на LLM
    subject: str = ""
    body: str = ""
    kind: str = "application"  # application | confirmation | counter_proposal
```

```python
# connectors/llm.py — додаємо
from core.models import EmailDraft

def draft_application(
    vacancy_raw: str, profile_summary: str, sender: str,
    missing: list[str], language: str | None = None,
) -> EmailDraft:
    ask = (
        f"Наприкінці природно постав 1–3 ввічливі уточнюючі питання по цих "
        f"відсутніх деталях вакансії: {missing}."
        if missing else
        "Додаткових питань не став — даних достатньо."
    )
    lang_rule = (
        f"МОВА ЛИСТА — СУВОРО '{language}' (ISO 639-1): пиши ВИКЛЮЧНО цією мовою, "
        "незалежно від мови цієї інструкції чи профілю."
        if language else
        "Напиши лист тією ж мовою, якою написане оголошення нижче."
    )
    instruction = (
        "Ти — персональний AI-агент, який шукає роботу в інтересах кандидата "
        f"({sender}). Напиши лист роботодавцю ВІД СВОГО ІМЕНІ як його агент і "
        "елегантно, з гумором познач, що пишеш саме ти, AI-агент — це навмисна "
        f"фішка, що демонструє кмітливість кандидата. Профіль: {profile_summary}. "
        f"Тон — яскравий, живий, без води. {lang_rule} {ask} "
        "Поверни subject і body; kind='application', to лиши порожнім."
    )
    return _call_with_fallback(
        schema=EmailDraft, model=JUDGE_MODEL,
        messages=[{"role": "user", "content": f"{instruction}\n\n---\n{vacancy_raw}"}],
    )
```

> Виклик іде через `_call_with_fallback` (а не напряму в `_llm`) — як і решта LLM-кроків, щоб працював крос-провайдерний фолбек Gemini → Mistral.

---

## Task 12 — Approval gate + відправка

**Мета:** а зараз ми покажемо лист людині й відправимо лише після підтвердження.

**Пояснення:** агент пропонує — людина вирішує. Це не обмеження демо, а принцип проєктування: між наміром LLM і реальним сайд-ефектом завжди стоїть людина. Найпростіша реалізація gate — показ чернетки + `input()`. На вебінарі: підтвердив → переключився на вкладку Gmail → лист уже там.

**Результат:**

```python
# клітинка
from connectors.dou_form import DouFormSender
from core.models import Attachment

sender = DouFormSender(dry_run=True)   # МОК; реальний відгук — dry_run=False
# беремо топ зі шортлиста: (vac, match, gaps) — gaps стануть питаннями в листі
vac, match, gaps = shortlist[0]
draft = draft_application(vac.raw_text, profile_summary, os.environ["AGENT_EMAIL"],
                          gaps, language=vac.posting_language)
draft.to = vac.apply_url or ""   # кому слати — ставимо кодом, не LLM
print(f"[{draft.kind}] до: {draft.to}\n\n{draft.body}")

# резюме як вкладення (піде в user_cv форми DOU)
resume = Attachment(filename="resume.pdf", path="data/resume.pdf", mime_type="application/pdf")

if input("\nВідправити відгук на DOU? [y/N] ").strip().lower() == "y":
    sender.send(draft.to, draft.subject, draft.body, attachments=[resume])
    print("✅ відгук відправлено (або dry-run) — очікуємо відповіді на email")
else:
    print("✋ скасовано")
```

---

# ОПЦІОНАЛЬНЕ: отримання

## Task 13 — Email-конектор: ImapReceiver (отримання)

**Мета:** а зараз ми навчимо агента читати вхідні відповіді.

**Пояснення:** друга «рука» — теж німий I/O: дістає непрочитані листи через IMAP (та сама скринька, той самий App-пароль) і повертає типізовані `IncomingMessage`. Оформлюємо як `ImapReceiver`, що реалізує порт `MessageReceiver`.

**Демо-стійкість (важливо):** реальний шлях демонстрації — надіслати листа з будь-якої пошти на `AGENT_EMAIL` (можна самому собі від імені «роботодавця»), і `ImapReceiver` його прочитає. Фолбек — `MockReceiver` (теж `MessageReceiver`), що повертає заготовлену відповідь без мережі. Обидва — той самий порт, перемикання одним рядком. Заготовлена відповідь навмисно містить вилку (закриває `gap`) і пропозицію часу (місток до Task 16).

> App Password у `.env` часто записаний із пробілами (`xxxx xxxx xxxx xxxx`) — перед `login` прибираємо їх: `pwd = os.environ["GMAIL_APP_PASSWORD"].replace(" ", "")`.

**Результат:**

```python
# connectors/email.py — додаємо
import imaplib, email as emaillib
from email.message import Message
from core.models import IncomingMessage
from core.ports import MessageReceiver

def _extract_plain_text(msg: Message) -> str:
    """Дістає text/plain з листа (multipart або простого)."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True) or b""
                return payload.decode(part.get_content_charset() or "utf-8", "replace")
        return ""
    payload = msg.get_payload(decode=True) or b""
    return payload.decode(msg.get_content_charset() or "utf-8", "replace")

class ImapReceiver:
    """MessageReceiver через Gmail IMAP."""
    HOST = "imap.gmail.com"

    def fetch_unread(self, limit: int = 5) -> list[IncomingMessage]:
        out: list[IncomingMessage] = []
        pwd = os.environ["GMAIL_APP_PASSWORD"].replace(" ", "")  # App Password інколи з пробілами
        with imaplib.IMAP4_SSL(self.HOST) as m:
            m.login(os.environ["AGENT_EMAIL"], pwd)
            m.select("INBOX")
            _, ids = m.search(None, "UNSEEN")
            for num in ids[0].split()[:limit]:
                _, data = m.fetch(num, "(RFC822)")
                msg = emaillib.message_from_bytes(data[0][1])
                out.append(IncomingMessage(
                    sender=msg["From"] or "",
                    subject=msg["Subject"] or "",
                    body=_extract_plain_text(msg),
                ))
        return out

_check: MessageReceiver = ImapReceiver()   # статична перевірка контракту
```

> Не кожне джерело має канал отримання: для борду без email `MessageReceiver` може бути відсутнім — тоді гілки T14/T16 у демо працюють лише з email-джерелом.

---

## Task 14 — Обробка відповіді: матчинг + розвилка

**Мета:** а зараз ми навчимо агента розбирати вхідний лист, зіставляти його з вакансією і діяти за **набором чинників**: дослані дані / пропозиція часу / відмова.

**Пояснення:** один LLM-розбір (`analyze_reply` → `ReplyAnalysis`) визначає все: до якої компанії лист, чи це відмова, які дані дослали (вилка/формат/локація) і чи пропонують час. Матчинг до шортлиста — **детермінований** (`match_reply_to_vacancy`, звичайне порівняння рядків). Далі routing кодом: дослали дані → `apply_reply_updates` (лише порожні поля) → `missing_fields` стискається → переоцінка `score_match` (петля ч.1 складається заново); є час → гілка співбесіди (Task 16); відмова → наступна вакансія.

> **Грабля:** назва компанії часто лише у `From`/`Subject`, не в тілі. Тому в `analyze_reply` передаємо ПОВНИЙ лист: `f"Від: {reply.sender}\nТема: {reply.subject}\n\n{reply.body}"`.

**Результат:**

```python
# core/models.py: ReplyAnalysis (matched_company, is_rejection, salary_min/max,
#   work_format, location, meeting_proposal); connectors/llm.py: analyze_reply();
#   core/logic.py: match_reply_to_vacancy(), apply_reply_updates()

# клітинка
reply = receiver.fetch_unread()[0]                       # IncomingMessage
reply_text = f"Від: {reply.sender}\nТема: {reply.subject}\n\n{reply.body}"
analysis = analyze_reply(reply_text, [v.company for v in vacancies])
vac = match_reply_to_vacancy(analysis.matched_company, vacancies)

if analysis.is_rejection:
    ...                                                  # відмова → наступна
elif vac is not None:
    if any([analysis.salary_min, analysis.salary_max,    # (A) дозаповнення
            analysis.work_format, analysis.location]):
        apply_reply_updates(vac, analysis)
        match = score_match(vac.raw_text + "\n" + reply.body, profile_summary, prefs_summary)
    if analysis.meeting_proposal:                        # (B) зустріч → Task 16
        ...
```

---

## Task 15 — Календар (варіант A): локальний планувальник

**Мета:** а зараз ми зробимо «календар пошукача» і логіку добору слота — без жодного LLM.

**Пояснення:** це серце опціональної частини й головна теза про конектори: розбір дати з листа — робота LLM, а рішення «вільно / зайнято / який найближчий слот» — детермінована логіка, тому чистий Python у `core`. Локальний календар (список зайнятих інтервалів + робочі години) дає всю логіку, тестовану й надійну, без OAuth. Рішення повертаємо як дані (`SlotDecision`), а не одразу діємо — щоб далі вмонтувати approval gate.

**Результат:**

```python
# core/calendar.py
from datetime import datetime, timedelta

class LocalCalendar:
    def __init__(self, busy: list[tuple[datetime, datetime]],
                 work_start=10, work_end=19, slot=timedelta(hours=1)):
        self.busy, self.work_start, self.work_end, self.slot = busy, work_start, work_end, slot

    def _within_hours(self, dt): return self.work_start <= dt.hour < self.work_end
    def _free(self, dt):
        return all(not (s <= dt < e) for s, e in self.busy)

    def is_available(self, dt):
        return self._within_hours(dt) and self._free(dt)

    def next_free_slot(self, after: datetime) -> datetime:
        dt = after
        for _ in range(7 * 24):                       # тиждень уперед максимум
            dt += self.slot
            if self.is_available(dt):
                return dt
        raise RuntimeError("немає вільних слотів")

    def book(self, start: datetime) -> None:          # позначити слот зайнятим
        self.busy.append((start, start + self.slot))
```

```python
# core/models.py + core/logic.py
from datetime import datetime

class SlotDecision(BaseModel):
    action: str          # "accept" | "propose_alternative"
    slot: datetime

def resolve_slot(proposed: datetime, cal: LocalCalendar) -> SlotDecision:
    # LLM інколи повертає datetime із tzinfo; LocalCalendar — naive → прибираємо tz
    if proposed.tzinfo is not None:
        proposed = proposed.replace(tzinfo=None)
    if cal.is_available(proposed):
        return SlotDecision(action="accept", slot=proposed)
    return SlotDecision(action="propose_alternative", slot=cal.next_free_slot(proposed))
```

---

## Task 16 — Гілка 2: запрошення на співбесіду (showpiece)

**Мета:** а зараз ми зберемо повний цикл: лист-запрошення → розбір часу → рішення → подія + відповідь.

**Пояснення:** з'єднуємо все. LLM витягує запропонований час із листа (`InterviewProposal`), детермінований `resolve_slot` вирішує; за рішенням генеруємо відповідний лист (підтвердження або контр-пропозиція) і «вставляємо» подію в локальний календар. Розгалуження роблять правила, текст — LLM, відправку — людина. Видно, як три інструменти (читання, календар, відправка) складаються в один прохід.

**Результат:**

```python
# core/models.py
class InterviewProposal(BaseModel):
    when: datetime              # не називаємо поле 'datetime' — не затіняємо тип
    note: str | None = None
```

```python
# connectors/llm.py — додаємо
def parse_meeting(meeting_text: str, now_hint: str) -> InterviewProposal:
    # відносні дати («четвер о 15:00») потребують орієнтиру → передаємо сьогодні
    instruction = (
        f"Сьогодні {now_hint}. Витягни запропоновані дату й час співбесіди у "
        "поле when як абсолютний datetime. Якщо є примітка — note."
    )
    return _call_with_fallback(
        schema=InterviewProposal, model=EXTRACT_MODEL,
        messages=[{"role": "user", "content": f"{instruction}\n\n---\n{meeting_text}"}],
    )

def draft_meeting_reply(action, slot, employer, sender, language=None) -> EmailDraft:
    # одна функція замість двох: accept -> підтвердження, інакше -> контр-пропозиція
    if action == "accept":
        intent, kind = f"Підтверди співбесіду на {slot:%Y-%m-%d %H:%M}, подякуй.", "confirmation"
    else:
        intent = f"Запропонований час не підходить — ввічливо запропонуй {slot:%Y-%m-%d %H:%M}."
        kind = "counter_proposal"
    lang = f"МОВА — СУВОРО '{language}'." if language else "Мовою попереднього листування."
    instruction = (
        f"Ти — AI-агент кандидата ({sender}), листуєшся з роботодавцем. "
        f"Напиши короткий лист від свого імені. {intent} {lang} "
        f"Поверни subject і body; kind='{kind}', to лиши порожнім."
    )
    return _call_with_fallback(
        schema=EmailDraft, model=JUDGE_MODEL,
        messages=[{"role": "user", "content": f"{instruction}\n\n---\nЛистування з: {employer}"}],
    )
```

```python
# клітинка — повний прохід (reply, analysis, vac, cal — з попередніх кроків)
from datetime import datetime
from connectors.email import GmailSender

now = datetime.now()
proposal = parse_meeting(analysis.meeting_proposal, now.strftime("%Y-%m-%d (%A)"))
decision = resolve_slot(proposal.when, cal)               # без LLM
if decision.action == "accept":
    cal.book(decision.slot)                               # подія в календар

draft = draft_meeting_reply(decision.action, decision.slot,
                            employer=reply.sender, sender=os.environ["AGENT_EMAIL"],
                            language=vac.posting_language if vac else None)
draft.to = reply.sender
print(decision.action, "→", decision.slot, "\n", draft.body)

# approval gate → GmailSender(dry_run=True).send(draft.to, draft.subject, draft.body)
```

---

## Task 17 — Камео: реальний Google Calendar (наприкінці)

**Мета:** а зараз — короткий показ, як та сама логіка підключається до реального календаря.

**Пояснення:** локальний `LocalCalendar` і реальний `GoogleCalendar` (`connectors/gcal.py`) — це один інтерфейс (`CalendarProvider`), різні адаптери. `GoogleCalendar` реалізує ті самі `is_available` / `next_free_slot` / `create_event`, але через Google Calendar API (`freebusy` + `events.insert`). Тому `cal = LocalCalendar(...)` → `cal = GoogleCalendar()` — і `resolve_slot` та цикл агента **не змінюються**. Це той самий аргумент, що й MCP: логіку написали раз, а продакшн-конектор лише реалізує контракт.

**Setup (один раз, користувач):** Google Cloud → увімкнути Calendar API → OAuth consent (External, себе в Test users) → OAuth client ID (Desktop app) → `credentials.json` у корінь. Перший запуск `GoogleCalendar()` відкриє браузер; після згоди збережеться `token.json`. Обидва файли в `.gitignore`.

> **Демо-стійкість:** якщо `credentials.json` немає — у ноутбуці робимо фолбек на `LocalCalendar` (`try: GoogleCalendar() except: LocalCalendar()`), тож камео не зриває ефір.
> **Нюанс tz:** Google API вимагає tz-aware RFC3339; naive datetime з `resolve_slot` локалізуємо в `Europe/Kyiv` усередині `gcal.py`.

**Результат:** `GoogleCalendar().create_event(...)` → реальна подія в Google Calendar (повертає посилання).

---

## Стан на виході (кінець частини 2)

Повний прохід end-to-end: резюме → шортліст → лист → відповідь → (уточнення | співбесіда) → подія в календарі → лист-підтвердження. Усі рішення — через approval gate; уся детермінована логіка — без LLM.

## Зв'язок з MCP (фінальний слайд)

Усе, що ми зробили руками (`GmailSender`, `ImapReceiver`, календар) — це інструменти, які стандартизує MCP. Наступний крок розвитку: замінити власні конектори на готові MCP-сервери (пошта, календар, CRM), лишивши незмінними `core/` і цикл агента.
