"""
Email-конектори для частини 2.

ImapReceiver реалізує порт MessageReceiver: дістає непрочитані листи зі скриньки
агента через IMAP і повертає типізовані IncomingMessage. Друга «рука» агента —
теж німий I/O: лише читає, нічого не вирішує.

Демо-стійкість: MockReceiver (теж MessageReceiver) повертає заготовлену відповідь
«роботодавця» — фолбек, якщо IMAP недоступний або скринька порожня. Перемикання
адаптера = один рядок; ядро й цикл агента не змінюються (ports & adapters).

Реальний шлях демонстрації: надіслати листа з будь-якої пошти на AGENT_EMAIL —
ImapReceiver його прочитає (лист має бути непрочитаним, IMAP увімкнено в Gmail).
"""

import email as emaillib
import imaplib
import os
import smtplib
from email.header import decode_header, make_header
from email.message import Message
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parseaddr

from core.models import Attachment, IncomingMessage
from core.ports import MessageReceiver, MessageSender


def _decode_header(value: str) -> str:
    """MIME encoded-word заголовок (=?UTF-8?B?...?=) → звичайний рядок.

    Gmail кодує не-ASCII теми й імена за RFC 2047 (=?UTF-8?B?...?=). Без
    декодування у subject/sender лізе сирий «=?UTF-8?B?...?=» — псує і вигляд,
    і вхід для LLM. make_header(decode_header()) збирає з частин читабельний текст.
    """
    if not value:
        return ""
    return str(make_header(decode_header(value)))


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
        # App Password у .env інколи з пробілами (формат 'xxxx xxxx xxxx xxxx') — прибираємо.
        pwd = os.environ["GMAIL_APP_PASSWORD"].replace(" ", "")
        with imaplib.IMAP4_SSL(self.HOST) as m:
            m.login(os.environ["AGENT_EMAIL"], pwd)
            m.select("INBOX")
            _, ids = m.search(None, "UNSEEN")
            for num in ids[0].split()[:limit]:
                _, data = m.fetch(num, "(RFC822)")
                msg = emaillib.message_from_bytes(data[0][1])
                out.append(
                    IncomingMessage(
                        sender=_decode_header(msg["From"] or ""),
                        subject=_decode_header(msg["Subject"] or ""),
                        body=_extract_plain_text(msg),
                    )
                )
        return out


# Заготовлена відповідь «роботодавця» для демо-фолбеку: одразу містить і вилку
# (закриває gap), і пропозицію часу — це знадобиться для гілки «співбесіда» (Task 16).
_DEFAULT_REPLY = IncomingMessage(
    sender="HR Techery <hr@techery.example>",
    subject="Re: відгук на Senior Python Engineer",
    body=(
        "Доброго дня! Дякуємо за відгук — профіль цікавий, і ваш AI-агент вразив. "
        "Зарплатна вилка для позиції — $5000–7000. "
        "Чи зручно вам онлайн-співбесіда у четвер о 15:00?"
    ),
)


class MockReceiver:
    """Фолбек-MessageReceiver: повертає заготовлену відповідь без мережі."""

    def __init__(self, messages: list[IncomingMessage] | None = None) -> None:
        self._messages = messages if messages is not None else [_DEFAULT_REPLY]

    def fetch_unread(self, limit: int = 5) -> list[IncomingMessage]:
        return self._messages[:limit]


class GmailSender:
    """MessageSender через Gmail SMTP — для листування (відповіді роботодавцю).

    dry_run=True за замовчуванням (МОК): нічого не шле, лише друкує лист.
    Реальна відправка — dry_run=False (SMTP на AGENT_EMAIL з App Password).
    """

    HOST = "smtp.gmail.com"
    PORT = 587

    def __init__(self, dry_run: bool = True) -> None:
        self.dry_run = dry_run

    def send(
        self,
        to: str,
        subject: str,
        body: str,
        attachments: list[Attachment] | None = None,
    ) -> None:
        sender = os.environ["AGENT_EMAIL"]
        to_addr = parseaddr(to)[1] or to  # 'HR <hr@x>' -> 'hr@x'

        if self.dry_run:
            print("🧪 [DRY-RUN] лист НЕ надіслано (мок). Реально пішло б:")
            print(f"   From: {sender}  →  To: {to_addr}")
            print(f"   Subject: {subject}")
            print(f"   {body[:160]}{'…' if len(body) > 160 else ''}")
            return

        msg = MIMEMultipart()
        msg["From"], msg["To"], msg["Subject"] = sender, to_addr, subject
        msg.attach(MIMEText(body, "plain", "utf-8"))
        for att in attachments or []:
            with open(att.path, "rb") as f:
                part = MIMEApplication(f.read())
            part.add_header("Content-Disposition", "attachment", filename=att.filename)
            msg.attach(part)

        pwd = os.environ["GMAIL_APP_PASSWORD"].replace(" ", "")
        with smtplib.SMTP(self.HOST, self.PORT) as s:
            s.starttls()
            s.login(sender, pwd)
            s.send_message(msg)
        print(f"✅ лист надіслано на {to_addr}")


_check_imap: MessageReceiver = ImapReceiver()  # статична перевірка контракту
_check_mock: MessageReceiver = MockReceiver()
_check_gmail: MessageSender = GmailSender()
