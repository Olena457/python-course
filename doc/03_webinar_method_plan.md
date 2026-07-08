

---

# Webinar: Idea and Theme

## 1. Concept

**What will be done:** In Jupyter, live, step by step, we build an AI agent that searches for a job on behalf of its “sponsor”:

1. **Start with the resume** — take the sponsor’s resume (PDF) and ask the LLM to structure it into a Pydantic model `CandidateProfile`. First demo of “Parsing 2.0” on a small personal document.  
2. **Job seeker’s preferences** — things missing from the resume (salary range, format, stop conditions), entered manually as `SearchPreferences`.  
3. **Parse vacancies** — collect job postings from jobs.dou.ua, where descriptions are HTML text.  
4. **Structure them** — same technique: posting → `Vacancy` model (with `apply_url`).  
5. **Filter and evaluate** — algorithmic filter without LLM → data completeness check → matching via LLM. Output: ordered shortlist with reasons and `gap` (missing details).  
6. **Write a letter** — from the **AI agent candidate** (a unique hook for employers), in the language of the posting, based on `CandidateProfile × Vacancy`. If there’s a `gap`, add polite questions at the end.  
7. **Apply and correspond** — agent applies via DOU form (using sessionid), then reads employer’s reply from email, proposes next step (interview), and responds via regular email.  

**Why this works:**
- Webinar audience = people learning programming = people looking for jobs. The agent searches *for them* — personal, not abstract.  
- **The letter is written by the agent — visibly.** For employers, such a letter signals technical ingenuity, not just another template. This turns “automated applications” from a spam risk into an advantage.  
- Natural hybrid of organizer’s request (“Parsing 2.0”) and agent theme: parsing = connector “world → LLM”, email = connector “LLM → world” (MCP/tool use).  
- Demonstrates full agent pattern **parse → reason → act** — evergreen YouTube content.  
- Jupyter provides the right narrative: cell → result → next step; no code wall.  

## 2. Technical Core (What the Audience Learns)

| Block | Content |
|---|---|
| Input connector | Resume (PDF→text) and vacancies (DOU, httpx + bs4) → LLM extraction into Pydantic models (structured output via instructor) |
| Manual input | `SearchPreferences` — job seeker’s wishes not in the resume |
| Reasoning | Algorithmic filter (no LLM) → data completeness check → matching (LLM, judge model); then one agent-written letter + questions for `gap` |
| Action connector | Tool use: apply via DOU form (POST via helper), read replies from Gmail (IMAP), schedule interview via calendar |
| Architecture | `core/` (models + pure logic, no I/O) ↔ `connectors/` (PDF, HTTP, LLM); notebook = conductor. Human-in-the-loop: agent proposes → human approves (approval gate) |

Full agent pattern: **parse → reason → act**. State lives in notebook memory (list of objects) — no DB needed.  

## 3. Breakdown into Two Sessions (≤1.5h each)

### Session 1 — “Agent Sees the World”
- Problem statement + teaser demo of final result  
- Resume → LLM extraction → `CandidateProfile` (first “Parsing 2.0” on personal doc)  
- `SearchPreferences` — manual input by seeker  
- Vacancies from DOU: parse list → `Vacancy` model with `apply_url`  
- Selection: algorithmic filter → data sufficiency → matching (LLM)  
- **Cliffhanger:** shortlist + “missing details” list, but agent can’t act yet — “what’s next?”  

### Session 2 — “Agent Acts”
- Short recap of Part 1 (+ link to recording)  
- Agent anatomy: state → decision → tool  
- Reasoning fork: missing data → clarifying letter; all matches → motivational letter + resume  
- MCP/tool use: send letter, read reply  
- Approval gate: why agent doesn’t act without human confirmation  
- Finale: full end-to-end pipeline run; CTA to ITVDN/CBS courses  

## 4. Risk Decisions

1. **Vacancy source:** jobs.dou.ua. Parse links and vacancy texts. Instead of employer email, store application form URL. Cached snapshot of response as fallback.  
2. **Application:** To apply on DOU, user manually retrieves `sessionid` and `csrftoken` from browser. To avoid low-level POST code overload, form submission logic is in helper `dou_helper.py`. Employer replies read from Gmail (where DOU sends notifications).  
3. **Human-in-the-loop:** Agent never submits autonomously; approval gate required. Presented not as demo limitation but as agent design principle.  

## 5. Title Candidates

Working link: personal benefit + Python + AI/agent.

1. **“An Agent That Finds a Job for You: Building an AI Agent in Python”** — main candidate  
2. “Parsing 2.0 → Agent 1.0: From Data Collection to AI Acting for You” — bridge from organizer’s initial theme  
3. “Python + AI: An Agent That Finds Vacancies and Corresponds with Employers”  

Subtitles for sessions:
- Part 1: “Agent Sees the World: Parsing and Understanding Data via LLM”  
- Part 2: “Agent Acts: Reasoning, MCP, and Correspondence on Your Behalf”  

## 6. Promo Hook (shorts, ≤1 min)

“I built an agent in Python that finds vacancies, asks employers questions, and arranges interviews. In two sessions, I’ll show how to build one — from scratch, in Jupyter. Join us.”  

---

Would you like me to polish the **titles and promo hook** into more marketing-style phrasing (catchier headlines, stronger call-to-action), or keep them in this practical, explanatory tone?