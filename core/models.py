from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field

class WorkFormat(str, Enum):
    onsite = "onsite"
    hybrid = "hybrid"
    remote = "remote"

class LanguageSkill(BaseModel):
    language_code: str | None = Field(None, description="ISO 639-1 code, e.g., 'en', 'uk'")
    level: str | None = Field(None, description="CEFR level if specified, e.g., 'B2', 'C1', 'Native'")

class ExperienceEntry(BaseModel):
    """Один запис у комерційному досвіді."""
    company: str | None = None
    role: str | None = None
    years: float | None = Field(None, description="Тривалість у роках (приблизно)")
    highlights: list[str] = Field(default_factory=list, description="Ключові досягнення")

class Education(BaseModel):
    """Один запис про освіту."""
    degree: str | None = None               # "Master's", "Bachelor's"
    field: str | None = None                 # "Radio Engineering"
    institution: str | None = None

class CandidateProfile(BaseModel):
    """Хто пошукач — витягуємо з резюме."""
    full_name: str | None = None
    title: str | None = None              # "Python Backend Developer"
    location: str | None = None           # поточна локація кандидата
    years_experience: float | None = None
    seniority: str | None = None          # junior / middle / senior
    tech_stack: list[str] = Field(default_factory=list)
    languages: list[LanguageSkill] = Field(default_factory=list)
    experience: list[ExperienceEntry] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    summary: str | None = None
    additional_info: str | None = Field(None, description="Будь-яка інша корисна інформація, що не лягає в структуру")

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
    seniority: str | None = None          # junior / middle / senior — якого рівня шукають
    location: str | None = None
    work_format: WorkFormat | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    tech_stack: list[str] = Field(default_factory=list)
    languages: list[LanguageSkill] = Field(default_factory=list)
    posting_language: str | None = Field(None, description="ISO 639-1 мови, якою НАПИСАНЕ оголошення (щоб відповісти тією ж), напр. 'uk', 'en'")
    additional_info: str | None = Field(None, description="Усе, що не структурується в інші поля")
    apply_url: str | None = None          # ключове для "рук" агента (URL вакансії на DOU)
    source_url: str | None = None
    raw_text: str = ""                     # оригінал; заповнюємо кодом, не LLM

class MatchResult(BaseModel):
    """Наскільки вакансія підходить пошукачу."""
    score: int = Field(ge=0, le=100)
    reasons: list[str] = Field(default_factory=list)

class Attachment(BaseModel):
    """Файл-вкладення до повідомлення (резюме, портфоліо тощо)."""
    filename: str                                          # "resume.pdf"
    path: str                                              # шлях до файлу на диску
    mime_type: str = "application/octet-stream"             # "application/pdf"

class IncomingMessage(BaseModel):
    """Вхідний лист / повідомлення — типізована заміна dict."""
    sender: str                                             # "recruiter@company.com"
    subject: str = ""
    body: str = ""
    attachments: list[Attachment] = Field(default_factory=list)

class EmailDraft(BaseModel):
    """Чернетка листа — людина бачить її до відправки (approval gate, ч.2)."""
    to: str = ""                          # заповнюємо кодом (apply_url), не покладаючись на LLM
    subject: str = ""
    body: str = ""
    kind: str = "application"             # application | confirmation | counter_proposal

class ConversationStage(str, Enum):
    """Стадія листування з роботодавцем по одній вакансії."""
    applied = "applied"            # відгук надіслано, чекаємо відповіді
    negotiating = "negotiating"    # узгоджуємо час зустрічі
    scheduled = "scheduled"        # час узгоджено, подію створено
    rejected = "rejected"          # роботодавець відмовив

class Conversation(BaseModel):
    """Памʼять агента про діалог по ОДНІЙ вакансії.

    Узгодження зустрічі — це НЕ один крок: агент пропонує час, роботодавець
    відповідає, агент реагує. Щоб реагувати правильно (напр. зрозуміти голе
    «так» як згоду на свій останній запропонований слот), треба памʼятати
    стадію й останню пропозицію. Це той стан, який фреймворки (LangGraph/
    LangChain) дають «з коробки» — а ми тримаємо його явно, простим обʼєктом.
    """
    company: str                                   # привʼязка до вакансії (за назвою компанії)
    stage: ConversationStage = ConversationStage.applied
    last_proposed_slot: datetime | None = None     # останній час, що ЗАПРОПОНУВАВ агент
    agreed_slot: datetime | None = None            # узгоджений час (коли stage=scheduled)
    history: list[IncomingMessage] = Field(default_factory=list)  # уся переписка

class ReplyAnalysis(BaseModel):
    """Розбір вхідної відповіді роботодавця: до якої вакансії й що в ній."""
    matched_company: str | None = None    # компанія/роль із листа — для матчингу до вакансії
    is_rejection: bool = False            # це відмова?
    # дозаповнення по вакансії (якщо роботодавець відповів на наші питання):
    salary_min: int | None = None
    salary_max: int | None = None
    work_format: WorkFormat | None = None
    location: str | None = None
    # призначення зустрічі — сирий текст про час (точну дату парсимо в гілці співбесіди):
    meeting_proposal: str | None = None
    summary: str | None = None

class SlotDecision(BaseModel):
    """Рішення щодо запропонованого часу зустрічі."""
    action: str                 # "accept" | "propose_alternative"
    slot: datetime

class InterviewProposal(BaseModel):
    """Запропонований роботодавцем час співбесіди (розібраний у datetime).

    when=None, якщо в листі немає КОНКРЕТНОГО часу (напр. голе «так, підходить»):
    тоді час береться з памʼяті розмови (Conversation.last_proposed_slot), а не
    вигадується.
    """
    when: datetime | None = None   # не називаємо поле 'datetime' — не затіняємо тип
    note: str | None = None
