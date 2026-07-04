"""
Чиста доменна логіка — без I/O та без LLM.

Принцип «спершу алгоритм, потім LLM»: усе, що можна вирішити детерміновано,
вирішуємо звичайним кодом. Це дешевше (нуль токенів), швидше (нуль мережі) і,
головне, надійніше: LLM стохастична за природою, тож має ненульову ймовірність
помилки навіть на очевидному. Дорогу «думаючу» модель бережемо на крок суджень,
де справді потрібен аналіз тексту (достатність і матчинг — Task 8–9).
"""

from datetime import datetime

from core.ports import CalendarProvider
from core.models import (
    CandidateProfile,
    Conversation,
    ConversationStage,
    ReplyAnalysis,
    SearchPreferences,
    SlotDecision,
    Vacancy,
)


def rejection_reason(
    v: Vacancy,
    prefs: SearchPreferences,
    profile: CandidateProfile,
) -> str | None:
    """Причина відсіву вакансії або None, якщо вона проходить далі.

    Лише дешеві детерміновані перевірки. Тонке судження «наскільки кандидат
    підходить за змістом» свідомо лишаємо LLM-матчингу (Task 9): це оцінка, не факт.

    Args:
        v: структурована вакансія (з raw_text для текстових перевірок).
        prefs: побажання пошукача (вилка, формат, стоп-слова, must-have).
        profile: профіль кандидата (наразі не використовується у відсіві —
            залишений у сигнатурі для майбутніх детермінованих перевірок).

    Returns:
        Рядок із причиною відсіву, або None якщо вакансія проходить.
    """
    text = (v.raw_text or "").lower()

    # 1. Стоп-слова: явний сигнал «не моє» прямо в тексті оголошення.
    for word in prefs.deal_breakers:
        if word.lower() in text:
            return f"deal-breaker: {word!r}"

    # 2. Формат роботи: відсіваємо лише коли формат вакансії ВІДОМИЙ і не бажаний.
    #    work_format часто None — тоді мовчимо, це вже питання до Task 8 (достатність).
    if prefs.work_formats and v.work_format and v.work_format not in prefs.work_formats:
        return f"формат {v.work_format.value} не серед бажаних"

    # 3. Вилка нижче порогу: порівнюємо ТІЛЬКИ коли число справді відоме.
    if prefs.min_salary and v.salary_max and v.salary_max < prefs.min_salary:
        return f"вилка {v.salary_max} < мінімум {prefs.min_salary}"

    # 4. Обов'язкові умови кандидата: якщо must-have взагалі не згадано в тексті —
    #    відсіваємо дешево. Точне «чи справді підходить» — робота LLM, не цього коду.
    for skill in prefs.must_have:
        if skill.lower() not in text:
            return f"немає обов'язкового: {skill!r}"

    return None


# ── Повнота даних (алгоритмічно, замість LLM-достатності) ─────────

def missing_fields(v: Vacancy, prefs: SearchPreferences) -> list[str]:
    """Які важливі для рішення поля у вакансії порожні — детерміновано, без LLM.

    Після Task 6 дані вже структуровані в поля Vacancy, тож «чи є вилка/формат»
    — це факт (поле is None), а не судження. Перевіряємо лише те, що цікавить
    кандидата (prefs). Повертає короткі українські мітки — вони ж стануть
    питаннями в листі роботодавцю (частина 2).
    """
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
    """Чи брати вакансію в шортліст на матчинг.

    Не жорсткі ворота: вакансію з невеликим gap (≤ max_gap незаповнених полів)
    усе одно беремо — бракуючі деталі потім спитаємо в листі. Відсіюємо лише
    зовсім «порожні» оголошення, де оцінювати просто нема чого.
    """
    return len(missing_fields(v, prefs)) <= max_gap


# ── Памʼять розмови: який час зараз обговорюється ──────────────────

def resolve_meeting_time(
    proposal_when: datetime | None,
    conv: Conversation,
) -> datetime | None:
    """Який час обговорюється — З УРАХУВАННЯМ ПАМʼЯТІ розмови, без LLM.

    Узгодження — не один крок, тому без стану голе «так» втрачає контекст:
    - LLM витяг конкретний час із листа → беремо його;
    - часу в листі нема (напр. «так, підходить»), але ми вже щось пропонували
      й досі узгоджуємо → це згода на НАШ останній запропонований слот;
    - інакше невідомо (None) — агент перепитає.
    """
    if proposal_when is not None:
        return proposal_when
    if conv.stage == ConversationStage.negotiating and conv.last_proposed_slot is not None:
        return conv.last_proposed_slot
    return None


# ── Обробка вхідної відповіді (матчинг + дозаповнення) — без LLM ───

def match_reply_to_vacancy(
    company_hint: str | None,
    vacancies: list[Vacancy],
) -> Vacancy | None:
    """Знаходить вакансію, до якої стосується відповідь, за згадкою компанії.

    Детермінований матчинг: LLM лише витяг назву компанії з листа (analyze_reply),
    а зіставлення з нашим шортлистом — звичайне порівняння рядків.
    """
    if not company_hint:
        return None
    hint = company_hint.lower()
    for v in vacancies:
        company = (v.company or "").lower()
        if company and (company in hint or hint in company):
            return v
    return None


def apply_reply_updates(v: Vacancy, analysis: ReplyAnalysis) -> None:
    """Дозаповнює ПОРОЖНІ поля вакансії досланими даними (наявні не чіпаємо).

    Мутує v на місці. Після цього missing_fields(v) поверне менший gap.

    ЧОМУ МУТАЦІЯ, А НЕ КОПІЯ: для навчального проєкту — простіше. У продакшені
    краще іммутабельний підхід: v = v.model_copy(update={"salary_min": ...}),
    щоб зберігати трасованість (хто і коли змінив поле). Мутація на місці
    простіша, але ускладнює дебаг: значення salary_min «з'явилось із нізвідки».
    """
    v.salary_min = v.salary_min or analysis.salary_min
    v.salary_max = v.salary_max or analysis.salary_max
    v.work_format = v.work_format or analysis.work_format
    v.location = v.location or analysis.location


# ── Планування слота зустрічі — без LLM ───────────────────────────

def resolve_slot(proposed: datetime, cal: CalendarProvider) -> SlotDecision:
    """Рішення щодо запропонованого часу — ДЕТЕРМІНОВАНО, без LLM.

    Розбір дати з листа — робота LLM (Task 16); а «вільно/зайнято/найближчий
    слот» — чиста логіка календаря. Повертаємо рішення як дані (SlotDecision),
    а не діємо одразу — щоб далі вмонтувати approval gate.
    """
    # LLM інколи повертає datetime із tzinfo (offset-aware), а LocalCalendar
    # працює в naive локальному часі — прибираємо tz, щоб порівняння не падало.
    if proposed.tzinfo is not None:
        proposed = proposed.replace(tzinfo=None)
    if cal.is_available(proposed):
        return SlotDecision(action="accept", slot=proposed)
    return SlotDecision(action="propose_alternative", slot=cal.next_free_slot(proposed))
