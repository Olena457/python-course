"""
Хелпер відправки відгуку на jobs.dou.ua — низькорівневий POST.

Винесено з вебінарного коду, щоб не перевантажувати його деталями куків,
csrf-токена та структури форми. На самому вебінарі цей файл показуємо оглядово
(«тут нудна сантехніка»), а в ноутбуці працюємо через DouFormSender.

БЕЗПЕКА: за замовчуванням dry_run=True (МОК) — нічого реально не надсилається,
лише друкуємо, що відправилося б. Реальний відгук — явно dry_run=False.

Структура форми відгуку (розвідано на реальній internal-вакансії DOU):
- кнопка «Откликнуться» (id=reply-btn-id) відкриває приховану форму id=replied-id;
- форма POST-иться з полями: csrfmiddlewaretoken, descr (текст відгуку),
  user_cv (файл резюме, опційно);
- автентифікація — кукам sessionid + csrftoken.
"""

import httpx

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def apply_for_vacancy(
    url: str,
    message: str,
    sessionid: str,
    csrftoken: str,
    cv_path: str | None = None,
    dry_run: bool = True,
) -> None:
    """Відправляє відгук на вакансію DOU (або імітує його при dry_run).

    Args:
        url: повна URL вакансії (вона ж endpoint форми відгуку).
        message: текст відгуку (піде в поле descr).
        sessionid, csrftoken: куки автентифікації (з браузера, через .env).
        cv_path: шлях до файлу резюме (поле user_cv); None — без вкладення.
        dry_run: True — нічого не шлемо, лише друкуємо (МОК); False — реальний POST.
    """
    if dry_run:
        print("🧪 [DRY-RUN] відгук НЕ відправлено (мок). Реально пішло б:")
        print(f"   POST  {url}")
        print(f"   descr ({len(message)} символів): {message[:120]}{'…' if len(message) > 120 else ''}")
        print(f"   user_cv: {cv_path or '—'}")
        return

    cookies = {"sessionid": sessionid, "csrftoken": csrftoken}
    # Django CSRF: значення поля форми = значення cookie csrftoken
    data = {"csrfmiddlewaretoken": csrftoken, "descr": message}
    headers = {"User-Agent": _UA, "Referer": url, "X-Requested-With": "XMLHttpRequest"}

    files = None
    cv_file = None
    try:
        if cv_path:
            cv_file = open(cv_path, "rb")
            files = {"user_cv": cv_file}
        resp = httpx.post(
            url, data=data, files=files, cookies=cookies, headers=headers,
            timeout=30, follow_redirects=True,
        )
        resp.raise_for_status()
    finally:
        if cv_file is not None:
            cv_file.close()

    print(f"✅ відгук відправлено: HTTP {resp.status_code}")
