"""
Локальний календар пошукача (варіант A) — без OAuth, без мережі.

Головна теза кроку: розбір дати з листа — робота LLM, а рішення «вільно /
зайнято / який найближчий слот» — ДЕТЕРМІНОВАНА логіка, тому чистий Python у
ядрі. Це надійно й тестовано без жодного виклику. Реальний Google Calendar
(Task 17) реалізуватиме той самий контракт CalendarProvider (core/ports.py).
"""

from datetime import datetime, timedelta


class LocalCalendar:
    """Зайняті інтервали + робочі години → доступність і найближчий вільний слот."""

    def __init__(
        self,
        busy: list[tuple[datetime, datetime]],
        work_start: int = 10,
        work_end: int = 19,
        slot: timedelta = timedelta(hours=1),
    ) -> None:
        self.busy = busy
        self.work_start = work_start
        self.work_end = work_end
        self.slot = slot

    def _within_hours(self, dt: datetime) -> bool:
        return self.work_start <= dt.hour < self.work_end

    def _free(self, dt: datetime) -> bool:
        return all(not (start <= dt < end) for start, end in self.busy)

    def is_available(self, dt: datetime) -> bool:
        return self._within_hours(dt) and self._free(dt)

    def next_free_slot(self, after: datetime) -> datetime:
        dt = after
        for _ in range(7 * 24):  # тиждень уперед максимум
            dt += self.slot
            if self.is_available(dt):
                return dt
        raise RuntimeError("немає вільних слотів на тиждень уперед")

    def book(self, start: datetime) -> None:
        """Позначає слот зайнятим (додає інтервал [start, start+slot])."""
        self.busy.append((start, start + self.slot))

    def create_event(self, title: str, start: datetime, end: datetime) -> str:
        """Реалізує контракт CalendarProvider: «створює» подію (локально).

        Для локального календаря це просто бронювання інтервалу. Реальний
        GoogleCalendar (connectors/gcal.py) реалізує той самий метод через API.
        """
        self.busy.append((start, end))
        return f"local-event:{title}@{start:%Y-%m-%d %H:%M}"
