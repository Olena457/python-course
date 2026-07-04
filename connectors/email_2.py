"""
DouFormSender — відправка відгуку на DOU через форму.

Реалізує порт MessageSender (core/ports.py). Це «німий» I/O: він НЕ вирішує,
кому й коли слати, не питає підтвердження — лише викликає хелпер. Рішення «чи
діяти» приймає цикл агента, дозвіл дає людина (approval gate в ноутбуці). Так
руки відокремлені від голови, і весь реальний сайд-ефект — в одному місці.
"""

import os

from core.models import Attachment
from core.ports import MessageSender
from helpers import dou_helper


class DouFormSender:
    """MessageSender для відгуку на DOU. Тонкий адаптер над dou_helper."""

    def __init__(self, dry_run: bool = True) -> None:
        # dry_run=True (МОК) за замовчуванням — безпечно; реальний відгук = False.
        self.dry_run = dry_run

    def send(
        self,
        to: str,
        subject: str,
        body: str,
        attachments: list[Attachment] | None = None,
    ) -> None:
        # 'to' використовуємо як URL вакансії (apply_url).
        # 'subject' ігноруємо — форма DOU має лише текст (descr).
        # attachments: беремо перший файл як резюме (user_cv), якщо є.
        cv_path = attachments[0].path if attachments else None
        dou_helper.apply_for_vacancy(
            url=to,
            message=body,
            sessionid=os.environ["DOU_SESSIONID"],
            csrftoken=os.environ["DOU_CSRFTOKEN"],
            cv_path=cv_path,
            dry_run=self.dry_run,
        )


# ПЕРЕВІРКА КОНТРАКТУ: Python — duck typing, і компілятор не перевіряє, чи клас
# справді реалізує Protocol (на відміну від Go/Java, де це помилка компіляції).
# Рядок нижче — трюк: створюємо екземпляр і присвоюємо його змінній з типом порту.
# Якщо клас НЕ реалізує send() з правильною сигнатурою — mypy/pyright покаже помилку.
# Без type-checker'а це лише документація наміру. У продакшені — mypy --strict
# із Protocol перевірятиме контракти автоматично при кожному коміті (CI).
# Аналогічний патерн — у email.py, vacancy_source.py; gcal.py має варіацію через
# те, що GoogleCalendar потребує OAuth при створенні екземпляра.
_check: MessageSender = DouFormSender()
