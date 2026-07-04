"""
Конектор до LLM: текст → типізовані дані (Pydantic-моделі).

Використовуємо instructor поверх кількох провайдерів:
- instructor патчить клієнт, додає автоматичні ретраї з валідацією
- response_model — Pydantic-модель, яка є і схемою для LLM, і валідатором
- крос-провайдерний: той самий виклик працює і для Gemini, і для Mistral

Надійність (важливо на FREE TIER, де моделі часто недоступні):
- instructor сам робить валідаційні ретраї (схема не зійшлась → LLM виправляє)
- _call_with_fallback: при 5xx/429 повтори з backoff, далі — фолбек на іншу
  модель І НАВІТЬ ІНШОГО ПРОВАЙДЕРА. Коли весь безкоштовний Gemini лежить,
  останній рятувальник у ланцюзі — Mistral (окремий API-ключ, окрема квота).

Навчальна теза вебінару — «модель за задачею»:
- парсинг (екстракція) — механічна операція → ДЕШЕВА/ПРОСТА модель
- судження (матчинг) — потрібен reasoning → ВАЖЧА/ДОРОЖЧА модель
Тому і в Gemini, і в Mistral ми тримаємо ОКРЕМІ моделі під ці два типи задач.
"""

import logging
import os
import time
from datetime import datetime
import instructor
from google import genai
from google.genai import types
from pydantic import BaseModel

from core.models import EmailDraft, InterviewProposal, MatchResult, ReplyAnalysis

# Приглушуємо «балакучі» внутрішні ERROR-логи instructor про невдалі спроби
# (англомовні "API call failed...", "Max retries exceeded..."). Це не наші
# помилки: ретраї та фолбек ми й так показуємо власними чистими повідомленнями.
logging.getLogger("instructor").setLevel(logging.CRITICAL)

# ── Клієнти провайдерів ───────────────────────────────────────────
# Основний провайдер — Gemini. Mistral підключаємо як крос-провайдерний
# фолбек: instructor.from_provider("mistral/<model>") сам створює клієнт
# mistralai і читає MISTRAL_API_KEY з оточення.
# ЧОМУ два окремі instructor-клієнти, а не один: фолбек має перемикати не
# лише модель, а й провайдера — у кожного власний SDK, ключ і квота.

_gemini = instructor.from_genai(
    # ЧОМУ timeout: free tier інколи віддає 503 з підвисанням з'єднання, а genai
    # без timeout чекає хвилинами замість того, щоб ШВИДКО впасти й піти у фолбек
    # (Gemini → Mistral). 30с достатньо для нормальної відповіді, але рятує демо
    # від зависань. Цей же _gemini використовується в усіх ланках _FALLBACKS нижче.
    genai.Client(
        api_key=os.environ["GOOGLE_API_KEY"],
        http_options=types.HttpOptions(timeout=30_000),  # мілісекунди
    ),
)
_mistral = instructor.from_provider("mistral/mistral-small-latest")

# ── Моделі за призначенням ────────────────────────────────────────
# EXTRACT — парсинг (механіка) → проста модель.
# JUDGE   — судження (reasoning) → розумніша модель.

EXTRACT_MODEL = "gemini-3.1-flash-lite"     # екстракція (резюме, вакансії) — легка, нове покоління
JUDGE_MODEL = "gemini-3.5-flash"            # достатність, матчинг, генерація — потужніша

# Mistral-відповідники під ті самі два типи задач (та сама теза «модель за задачею»):
# - екстракція → open-mistral-nemo: легка open-модель, її досить для парсингу
# - судження   → mistral-small-latest: сильніша, бо потрібен reasoning
MISTRAL_EXTRACT_MODEL = "open-mistral-nemo"
MISTRAL_JUDGE_MODEL = "mistral-small-latest"

# ── Ланцюжки фолбеків ─────────────────────────────────────────────
# Елемент ланцюга = (instructor-клієнт, назва моделі) — щоб перемикати й
# провайдера. Порядок: спершу вичерпуємо БЕЗКОШТОВНИЙ Gemini (різні моделі),
# і лише в КІНЦІ ланцюга — Mistral як останній рятувальник (бережемо його квоту).
# Ланцюги розділені за типом задачі: легкі моделі тримаємо з легкими.
_FALLBACKS: dict[str, list[tuple[instructor.Instructor, str]]] = {
    EXTRACT_MODEL: [                           # основна: gemini-3.1-flash-lite
        (_gemini, "gemini-2.5-flash-lite"),    # стабільна легка з попереднього покоління
        (_gemini, "gemini-2.5-flash"),
        (_mistral, MISTRAL_EXTRACT_MODEL),     # ← інший провайдер, кінець ланцюга
    ],
    JUDGE_MODEL: [                             # основна: gemini-3.5-flash
        (_gemini, "gemini-2.5-flash"),         # стабільна важча з попереднього покоління
        (_mistral, MISTRAL_JUDGE_MODEL),       # ← інший провайдер, кінець ланцюга
    ],
}

# Підрядки помилок, на які ВАРТО ретраїти/фолбекати (серверні + rate limit
# обох провайдерів). Клієнтські помилки (400/404) сюди не входять — їх не лікують ретраї.
_RETRYABLE = ("503", "429", "500", "502", "504", "UNAVAILABLE", "capacity", "rate limit")


# ── Виклик з ретраями та фолбеком ─────────────────────────────────

def _call_with_fallback[T: BaseModel](
    schema: type[T],
    messages: list[dict],
    model: str,
    max_attempts: int = 3,
    backoff: float = 2.0,
) -> T:
    """Викликає LLM з ретраями та фолбеком на іншу модель/провайдера.

    Логіка:
    1. Пробуємо основну модель max_attempts разів з лінійним backoff
    2. Якщо все одно серверна помилка / rate limit — переходимо до наступного
       елемента ланцюга (інша модель, можливо інший провайдер)
    3. Якщо нічого не спрацювало — кидаємо останню помилку
    """
    # Ланцюг: основна модель (завжди на Gemini) + її фолбеки.
    chain: list[tuple[instructor.Instructor, str]] = [(_gemini, model)] + _FALLBACKS.get(model, [])
    last_error: Exception | None = None

    for client, current_model in chain:
        for attempt in range(1, max_attempts + 1):
            try:
                result = client.chat.completions.create(
                    model=current_model,
                    response_model=schema,
                    messages=messages,
                    # strict=False: lax-валідація коерсить «брудний» вивід LLM
                    # (рядок 'remote' → WorkFormat, '4000' → int). У strict-режимі
                    # рядок не приводиться до Enum — і екстракція падає на ретраях.
                    strict=False,
                )
                # Якщо модель змінилась — повідомляємо (корисно для дебагу наживо)
                if current_model != model:
                    print(f"  ⚠️  Використано фолбек-модель: {current_model}")
                return result

            except Exception as e:
                last_error = e
                error_str = str(e)
                # Ретраї лише для серверних помилок і rate limit
                if any(marker in error_str for marker in _RETRYABLE):
                    wait = backoff * attempt
                    print(f"  ⏳ API {current_model}: {error_str[:80]}... "
                          f"(спроба {attempt}/{max_attempts}, чекаємо {wait:.0f}с)")
                    time.sleep(wait)
                else:
                    # Клієнтська помилка (400, 404) — ретраї не допоможуть
                    raise

        # Усі спроби для поточної моделі вичерпано — переходимо до наступного фолбеку
        if len(chain) > 1:
            print(f"  🔄 Модель {current_model} недоступна, пробуємо наступну...")

    # Усе вичерпано
    raise last_error  # type: ignore[misc]


# ── Універсальна екстракція ───────────────────────────────────────

def extract[T: BaseModel](
    text: str,
    schema: type[T],
    instruction: str,
    model: str = EXTRACT_MODEL,
) -> T:
    """Сирий текст → екземпляр Pydantic-моделі.

    Одна функція для всього: резюме → CandidateProfile,
    вакансія → Vacancy, лист → InterviewProposal.
    Змінюється лише schema та instruction.
    """
    return _call_with_fallback(
        schema=schema,
        messages=[
            {"role": "user", "content": f"{instruction}\n\n---\n{text}"},
        ],
        model=model,
    )


# ── Матчинг (головне судження) ────────────────────────────────────

def score_match(vacancy_raw: str, profile_summary: str, prefs_summary: str) -> MatchResult:
    """Наскільки вакансія підходить кандидату: score 0..100 + причини.

    Це головне судження пайплайна, тому беремо JUDGE_MODEL — reasoning-модель.
    «Мислення» вмикається саме ВИБОРОМ МОДЕЛІ (judge аналізує, на відміну від
    легкої extract-моделі), а не низькорівневим thinking_config: той провайдер-
    специфічний (genai-only) і зламав би наш крос-провайдерний фолбек на Mistral.
    Поле reasons робить рішення прозорим для людини.
    """
    instruction = (
        "Оціни відповідність вакансії кандидату за шкалою 0..100 і поясни причини.\n"
        f"Кандидат: {profile_summary}\n"
        f"Пріоритети: {prefs_summary}"
    )
    return _call_with_fallback(
        schema=MatchResult,
        messages=[
            {"role": "user", "content": f"{instruction}\n\n---\n{vacancy_raw}"},
        ],
        model=JUDGE_MODEL,
    )


# ── Генерація листа (мотивація + питання по gap) ──────────────────

def draft_application(
    vacancy_raw: str,
    profile_summary: str,
    sender: str,
    missing: list[str],
    language: str | None = None,
    candidate_name: str | None = None,
) -> EmailDraft:
    """Яскравий мотиваційний лист ВІД ІМЕНІ AI-АГЕНТА, що діє в інтересах кандидата.

    Фішка для роботодавця: лист пише не сам кандидат, а його персональний
    AI-агент — і це навмисно видно. Сам факт, що в кандидата є такий агент, —
    сигнал про його технічну кмітливість (саме цьому ми й вчимося на вебінарі).

    Окремої гілки «уточнюючий лист» немає: список missing підмішує блок питань у
    кінець. LLM відповідає лише за ТЕКСТ, не за рішення слати — між ним і реальною
    відправкою стоїть людина (approval gate, Task 12). Поле to не просимо в LLM —
    проставимо кодом (apply_url). Мова листа = мова оголошення.
    """
    ask = (
        f"Наприкінці природно постав 1–3 ввічливі уточнюючі питання саме по цих "
        f"відсутніх деталях вакансії: {missing}."
        if missing else
        "Додаткових питань не став — даних достатньо."
    )
    lang_rule = (
        f"МОВА ЛИСТА — СУВОРО '{language}' (ISO 639-1). Пиши subject і body ВИКЛЮЧНО "
        "цією мовою, незалежно від мови цієї інструкції чи профілю кандидата."
        if language else
        "Напиши лист тією самою мовою, якою написане оголошення нижче "
        "(визнач її сам), незалежно від мови цієї інструкції."
    )
    # ЧОМУ окремо: імʼя — відомий факт із резюме, тож подаємо його ПРЯМО, а не
    # лишаємо LLM транслітерувати/вгадувати (інакше «Зівенко/Живенко/Михайло»).
    name_rule = (
        f"Імʼя кандидата — «{candidate_name}». Вживай його в листі ДОСЛІВНО (саме в "
        "такому написанні): не транслітеруй, не перекладай і не вигадуй інше."
        if candidate_name else ""
    )
    instruction = (
        "Ти — персональний AI-агент, який шукає роботу в інтересах свого кандидата "
        f"({sender}). Напиши лист роботодавцю ВІД СВОГО ІМЕНІ як його агент і "
        "елегантно, з гумором познач, що пишеш саме ти, AI-агент кандидата — це "
        "навмисна фішка, що демонструє технічну кмітливість кандидата. "
        f"Профіль кандидата: {profile_summary}. {name_rule} "
        "Тон — яскравий, живий, чіпкий, але професійний; жодної води й канцеляриту. "
        f"{lang_rule} "
        f"{ask} Поверни subject і body; kind='application', to лиши порожнім."
    )
    return _call_with_fallback(
        schema=EmailDraft,
        messages=[
            {"role": "user", "content": f"{instruction}\n\n---\n{vacancy_raw}"},
        ],
        model=JUDGE_MODEL,
    )


# ── Розбір вхідної відповіді роботодавця ──────────────────────────

def analyze_reply(reply_text: str, companies: list[str]) -> ReplyAnalysis:
    """Вхідний лист роботодавця → структурований розбір (матчинг + 3 чинники).

    Один виклик визначає все, що потрібно для рішення: до якої вакансії лист
    (matched_company зі списку companies), чи це відмова, які дані дослали
    (вилка/формат/локація) і чи пропонують час зустрічі. Routing за цими
    чинниками — вже детермінований код, не LLM.

    ВАЖЛИВО: reply_text — ПОВНИЙ лист (From/Subject/Body), бо назва компанії
    часто лише у відправнику чи темі, а не в тілі.
    """
    instruction = (
        "Розбери вхідний лист-відповідь роботодавця кандидату. Визнач:\n"
        f"- matched_company: до якої компанії/вакансії стосується лист "
        f"(обери з-поміж: {companies});\n"
        "- is_rejection: чи це відмова;\n"
        "- дослані дані вакансії, якщо є: salary_min, salary_max, work_format, location;\n"
        "- meeting_proposal: якщо пропонують час зустрічі — наведи його як є (текстом);\n"
        "- summary: одне речення суті листа."
    )
    return _call_with_fallback(
        schema=ReplyAnalysis,
        messages=[
            {"role": "user", "content": f"{instruction}\n\n---\n{reply_text}"},
        ],
        model=JUDGE_MODEL,
    )


# ── Співбесіда: розбір часу + лист-відповідь ──────────────────────

def parse_meeting(meeting_text: str, now_hint: str) -> InterviewProposal:
    """Сирий текст про час → InterviewProposal{when: datetime | None}.

    Відносні дати («четвер о 15:00») потребують орієнтиру, тому передаємо
    поточну дату now_hint, щоб LLM обчислив абсолютний datetime. Це витяг —
    легка EXTRACT_MODEL.

    ВАЖЛИВО: when=None, якщо КОНКРЕТНОГО часу в тексті немає (напр. голе «так,
    підходить») — тоді час візьметься з памʼяті розмови (Conversation), а не
    вигадається. Без цього LLM повертала «сьогодні 00:00» і ламала логіку.
    """
    instruction = (
        f"Сьогодні {now_hint}. Якщо в тексті є КОНКРЕТНИЙ час зустрічі — витягни "
        "його в поле when як абсолютний datetime. Якщо конкретного часу НЕМАЄ "
        "(напр. лише згода на кшталт «так, підходить») — залиш when порожнім (null). "
        "Якщо є примітка — note."
    )
    return _call_with_fallback(
        schema=InterviewProposal,
        messages=[
            {"role": "user", "content": f"{instruction}\n\n---\n{meeting_text}"},
        ],
        model=EXTRACT_MODEL,
    )


def draft_meeting_reply(
    action: str,
    slot: datetime,
    employer: str,
    sender: str,
    language: str | None = None,
    candidate_name: str | None = None,
) -> EmailDraft:
    """Лист-відповідь про зустріч від імені AI-агента: підтвердження або контр-пропозиція.

    action='accept' → підтверджуємо запропонований час; інакше → ввічливо
    пропонуємо найближчий вільний слот. Мова — як в оголошенні (language).
    """
    if action == "accept":
        intent = f"Підтверди співбесіду на {slot:%Y-%m-%d %H:%M}, коротко подякуй."
        kind = "confirmation"
    else:
        intent = (
            f"Запропонований час не підходить — ввічливо запропонуй натомість "
            f"{slot:%Y-%m-%d %H:%M}, збережи зацікавленість."
        )
        kind = "counter_proposal"
    lang_rule = (
        f"МОВА ЛИСТА — СУВОРО '{language}' (ISO 639-1)."
        if language else
        "Напиши мовою попереднього листування."
    )
    # Імʼя кандидата подаємо ПРЯМО (з резюме), а не з email-адреси, щоб LLM не
    # вгадувала прізвище з «...zivenko@...» і не псувала транслітерацію.
    name_rule = (
        f"Імʼя кандидата — «{candidate_name}»; вживай його ДОСЛІВНО, не транслітеруй."
        if candidate_name else ""
    )
    instruction = (
        f"Ти — персональний AI-агент кандидата ({sender}), листуєшся з роботодавцем. "
        f"{name_rule} Напиши короткий лист від свого імені. {intent} {lang_rule} "
        f"Поверни subject і body; kind='{kind}', to лиши порожнім."
    )
    return _call_with_fallback(
        schema=EmailDraft,
        messages=[
            {"role": "user", "content": f"{instruction}\n\n---\nЛистування з: {employer}"},
        ],
        model=JUDGE_MODEL,
    )
