"""
GoogleCalendar — реальний адаптер CalendarProvider через Google Calendar API.

Камео (Task 17): та сама логіка, що в LocalCalendar (вільно/зайнято/найближчий
слот/створити подію), але на РЕАЛЬНОМУ календарі. Доводить тезу ports & adapters:
`resolve_slot` і цикл агента не змінюються — змінюється лише адаптер.

─────────────────────────────────────────────────────────────────────────────
SETUP (один раз, робить користувач):
1. Google Cloud Console → новий проект → увімкнути «Google Calendar API».
2. APIs & Services → OAuth consent screen → External → додати себе в Test users.
3. Credentials → Create credentials → OAuth client ID → тип «Desktop app» →
   завантажити JSON як `credentials.json` у корінь проєкту.
4. Перший запуск GoogleCalendar() відкриє браузер для згоди — після неї
   збережеться `token.json` (наступні запуски — без браузера).
Обидва файли вже в .gitignore.
─────────────────────────────────────────────────────────────────────────────
"""

import os.path
import pathlib
from datetime import datetime, timedelta

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from core.ports import CalendarProvider

_SCOPES = ["https://www.googleapis.com/auth/calendar"]
# ЧОМУ абсолютні шляхи: ноутбук працює з cwd=notebooks/, а файли — у корені проєкту.
# Відносні "credentials.json"/"token.json" → FileNotFoundError → тихий фолбек на
# LocalCalendar. Прив'язуємо до кореня через __file__ (як _CACHE у vacancy_source.py).
_ROOT = pathlib.Path(__file__).resolve().parent.parent
_CREDENTIALS = str(_ROOT / "credentials.json")
_TOKEN = str(_ROOT / "token.json")
def _rfc3339(dt: datetime) -> str:
    """naive datetime → RFC3339 з offset (Google API вимагає tz-aware).

    Naive-час трактуємо в ЛОКАЛЬНОМУ поясі системи (.astimezone()), а НЕ в
    захардкодженому. Інакше час зсувається: машина в GMT+2, а хардкод
    Europe/Kyiv (GMT+3) → і подія, і перевірка зайнятості на годину раніше.
    """
    if dt.tzinfo is None:
        dt = dt.astimezone()   # naive → aware у локальному поясі системи
    return dt.isoformat()


def _load_service():
    """OAuth: token.json → (refresh) → інакше браузер-згода через credentials.json."""
    creds = None
    if os.path.exists(_TOKEN):
        creds = Credentials.from_authorized_user_file(_TOKEN, _SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(_CREDENTIALS, _SCOPES)
            creds = flow.run_local_server(port=0)
        with open(_TOKEN, "w") as f:
            f.write(creds.to_json())
    return build("calendar", "v3", credentials=creds)


class GoogleCalendar:
    """CalendarProvider на реальному Google Calendar (той самий контракт, що LocalCalendar)."""

    def __init__(
        self,
        calendar_id: str = "primary",
        work_start: int = 10,
        work_end: int = 19,
        slot: timedelta = timedelta(hours=1),
    ) -> None:
        self._svc = _load_service()
        self.calendar_id = calendar_id
        self.work_start = work_start
        self.work_end = work_end
        self.slot = slot

    # ⚠️ ДУБЛЮВАННЯ: _within_hours і next_free_slot ідентичні з LocalCalendar (core/calendar.py).
    # Це свідомий компроміс для навчального проєкту. Варіанти усунення:
    #   1. Mixin-клас (CalendarMixin) з робочими годинами і пошуком слотів — обидва
    #      календарі наслідують його, додаючи лише свою реалізацію is_available.
    #   2. Базовий абстрактний клас (ABC) замість Protocol — із default-реалізацією
    #      _within_hours і next_free_slot, але тоді втрачаємо duck typing.
    #   3. Утілітна функція within_hours(dt, start, end) у core/ — обидва імпортують.
    # Для навчального проєкту дублювання прийнятне, бо кожен адаптер лишається
    # самодостатнім і зрозумілим окремо (один файл — одна реалізація).

    def _within_hours(self, dt: datetime) -> bool:
        return self.work_start <= dt.hour < self.work_end

    def is_available(self, dt: datetime) -> bool:
        if not self._within_hours(dt):
            return False
        # freebusy: чи зайнятий інтервал [dt, dt+slot] у реальному календарі
        result = self._svc.freebusy().query(body={
            "timeMin": _rfc3339(dt),
            "timeMax": _rfc3339(dt + self.slot),
            "items": [{"id": self.calendar_id}],
        }).execute()
        busy = result["calendars"][self.calendar_id]["busy"]
        return len(busy) == 0

    def next_free_slot(self, after: datetime) -> datetime:
        dt = after
        for _ in range(7 * 24):  # тиждень уперед максимум
            dt += self.slot
            if self.is_available(dt):
                return dt
        raise RuntimeError("немає вільних слотів на тиждень уперед")

    def create_event(self, title: str, start: datetime, end: datetime) -> str:
        """Створює РЕАЛЬНУ подію в календарі; повертає посилання на неї."""
        event = self._svc.events().insert(calendarId=self.calendar_id, body={
            "summary": title,
            "start": {"dateTime": _rfc3339(start)},
            "end": {"dateTime": _rfc3339(end)},
        }).execute()
        return event.get("htmlLink", event["id"])


# Статична перевірка контракту виконується ліниво (потребує OAuth), тож тут
# лишаємо лише анотацію наміру — реальний _check робиться при інстанціюванні.
_: type[CalendarProvider] = GoogleCalendar
