# ✅ Pre-flight: 10 хвилин до ефіру

Чек-лист, який треба пройти **за ~10 хв до старту вебінару**, щоб наскрізний
демо-цикл `parse → reason → act` на реальній вакансії
[exsol-doo/363796](https://jobs.dou.ua/companies/exsol-doo/vacancies/363796/)
точно спрацював наживо.

> Усі команди запускати **з кореня проекту**. Демо-стійкість закладена в код:
> майже на кожному кроці є фолбек (див. розділ E) — але краще, щоб спрацював
> реальний шлях.

---

## A. Критичне — без цього зламається

> Це не «можливо», а «впаде». Пройти обов'язково.

- [ ] **1. Свіжі DOU-куки.** `DOU_SESSIONID` / `DOU_CSRFTOKEN` у `.env` протухають —
  це найімовірніша причина падіння реального відгуку.
  Chrome → відкрити jobs.dou.ua (залогінений) → DevTools (`⌥⌘I`) →
  вкладка **Application** → Storage → **Cookies** → `https://jobs.dou.ua` →
  скопіювати значення `sessionid` і `csrftoken` → вставити в `.env` → **зберегти**.

- [ ] **2. Вакансія ще в зоні досяжності `fetch(limit=…)`.** Стрічка
  `category=Python` повзе вниз із кожною новою вакансією. Перевірити позицію:

  ```bash
  uv run python - <<'PY'
  import httpx
  from bs4 import BeautifulSoup
  H={"User-Agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
  LIST="https://jobs.dou.ua/vacancies/?category=Python"; XHR="https://jobs.dou.ua/vacancies/xhr-load/?category=Python"
  links=[]; seen=set()
  with httpx.Client(headers=H,timeout=30,follow_redirects=True) as c:
      first=c.get(LIST).text; csrf=c.cookies.get("csrftoken","")
      for p in range(1,12):
          html=first if p==1 else c.post(XHR,data={"csrfmiddlewaretoken":csrf,"count":str((p-1)*20)},headers={"X-Requested-With":"XMLHttpRequest","Referer":LIST}).json().get("html","")
          new=[a["href"] for a in BeautifulSoup(html,"html.parser").select("a.vt") if a.get("href") and a["href"] not in seen]
          [seen.add(x) for x in new]; links+=new
          if not new: break
  pos=next((i+1 for i,l in enumerate(links) if "363796" in l), None)
  print(f"Позиція exsol-doo/363796: #{pos} з {len(links)}" if pos else "❌ вакансії НЕМАЄ у стрічці!")
  PY
  ```

  - Якщо позиція **> 5** → у `part1`, Task 5 підняти `DouSource(...).fetch(limit=…)`
    до значення **більшого за позицію** (напр. `limit=10` чи `15`).
  - Якщо `❌` — вакансія зникла зі стрічки (знята/перемодерована) → демо на ній
    неможливе, потрібна інша активна вакансія.

- [ ] **3. «Лист роботодавця» вже у скриньці й НЕпрочитаний.**
  З *іншої* пошти надіслати листа на `AGENT_EMAIL`. Дві жорсткі умови з коду:
  - у **From / Subject / Body** має бути назва компанії **`exsol`** — інакше
    `match_reply_to_vacancy` не зіставить лист із вакансією (`vac=None`);
  - у тілі — **пропозиція часу** (напр. «Чи зручно вам у четвер о 15:00?») —
    інакше не запуститься гілка календаря (Task 16).
  - ⚠️ **Не відкривати** цей лист у вебі Gmail — `ImapReceiver` бере лише `UNSEEN`;
    відкриєш → стане «прочитаним» → код впаде на `MockReceiver`.

  Приклад тексту листа:
  > Тема: `Re: відгук на Python-вакансію (Exsol)`
  > Доброго дня! Дякуємо за відгук, профіль цікавий. Зарплатна вилка $5000–7000.
  > Чи зручно вам онлайн-співбесіда у четвер о 15:00?

---

## B. Швидкі смоук-тести середовища

- [ ] **4. Усі ключі в `.env` на місці** (вони gitignored — мають бути скопійовані
  в проект разом із `data/`, `credentials.json`, `token.json`):

  ```bash
  uv run python -c "import os; from dotenv import load_dotenv; load_dotenv(); ks=['GOOGLE_API_KEY','MISTRAL_API_KEY','AGENT_EMAIL','GMAIL_APP_PASSWORD','DOU_SESSIONID','DOU_CSRFTOKEN']; miss=[k for k in ks if not os.getenv(k)]; print('❌ бракує:', miss) if miss else print('✅ всі ключі є')"
  ```

- [ ] **5. LLM відповідає** (перевіряє Gemini, а заразом увесь ланцюг фолбеку до Mistral):

  ```bash
  uv run python -c "from connectors.llm import extract; from core.models import CandidateProfile; p=extract('John Doe, Python backend developer, 5 years', CandidateProfile, 'Витягни профіль'); print('✅ LLM ok:', p.title)"
  ```

- [ ] **6. Gmail IMAP логіниться і бачить лист роботодавця** (підтверджує App
  Password + що лист із кроку 3 справді `UNSEEN`):

  ```bash
  uv run python -c "from connectors.email import ImapReceiver; msgs=ImapReceiver().fetch_unread(); print(f'✅ IMAP ok, непрочитаних: {len(msgs)}'); [print('  від:', m.sender, '|', m.subject) for m in msgs]"
  ```

  Очікування: ≥1 лист, серед них — твій «лист роботодавця» зі словом `exsol`.

- [ ] **7. Google Calendar token живий** (OAuth не протух):

  ```bash
  uv run python -c "from connectors.gcal import GoogleCalendar; GoogleCalendar(); print('✅ Google Calendar ok')"
  ```

  Якщо просить повторний OAuth-флоу — пройти його **зараз**, не наживо.

- [ ] **8. Резюме та fixtures на місці** (фолбек DOU):

  ```bash
  ls -la data/Kostiantyn_Zivenko_Resume_EN.pdf fixtures/dou_vacancies.json
  ```

---

## C. Перемикачі `dry_run` на час демо

За замовчуванням sender-и в **МОК-режимі** (нічого реально не шлють). Для
наскрізного «по-справжньому» перемкнути на місці, перед відповідним кроком:

- [ ] **Task 10/12** (відгук на DOU): `DouFormSender(dry_run=False)`
- [ ] **Task 16** (відповідь роботодавцю): `GmailSender(dry_run=False)`

> Лишити `dry_run=True`, якщо демонструєш «руки» агента без реальної відправки.
> Approval gate (`input("...[y/N]")`) спрацьовує в обох режимах — підтверджувати `y`.

⚠️ **`shortlist[0]` ≠ exsol.** Task 11 і Task 10/12 беруть `shortlist[0]` — це
вакансія з **найвищим score**, не обов'язково твоя тестова. Щоб відгук пішов саме
на exsol, вибрати її явно:

```python
vac, match, gaps = next(t for t in shortlist if "363796" in (t[0].apply_url or ""))
```

---

## D. Прибирання перед стартом

- [ ] **9. Видалити старі тестові події** в Google Calendar (з попередніх прогонів),
  щоб демо-подія була єдиною й чистою.
- [ ] **10. Визначитись зі `state.json`:** або генеруємо наживо (повний `part1`),
  або тримаємо відомий-робочий `data/state.json` як фолбек, щоб `part2` стартував
  навіть якщо `part1` наживо зіб'ється.

---

## E. Якщо щось падає наживо — фолбеки (демо-стійкість)

| Крок | Реальний шлях | Один рядок — і працює далі |
|---|---|---|
| LLM | Gemini | автоматично → Mistral (інший провайдер, у коді) |
| Вакансії з DOU | `DouSource(use_cache=False)` | `DouSource(use_cache=True)` — знімок із `fixtures/` |
| Відгук на DOU | `DouFormSender(dry_run=False)` | `dry_run=True` — мок, показуємо що пішло б |
| Відповідь роботодавця | `ImapReceiver` | `MockReceiver()` — заготовлений лист |
| Відповідь роботодавцю | `GmailSender(dry_run=False)` | `dry_run=True` — мок |
| Календар | `GoogleCalendar()` | `LocalCalendar(...)` — той самий порт |

> Принцип: **усі адаптери взаємозамінні** (ports & adapters) — фолбек це заміна
> одного рядка, ядро й цикл агента не змінюються.

---

### 30-секундний фінальний смоук (усе разом)

```bash
uv run python -c "import os; from dotenv import load_dotenv; load_dotenv(); print('keys:', all(os.getenv(k) for k in ['GOOGLE_API_KEY','MISTRAL_API_KEY','AGENT_EMAIL','GMAIL_APP_PASSWORD','DOU_SESSIONID','DOU_CSRFTOKEN']))" \
&& uv run python -c "from connectors.email import ImapReceiver; print('imap unread:', len(ImapReceiver().fetch_unread()))" \
&& uv run python -c "from connectors.gcal import GoogleCalendar; GoogleCalendar(); print('calendar: ok')"
```

Усе зелене — можна виходити в ефір. 🎙️
