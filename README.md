# SignalDesk AI — Evidence-first Action & Automation Hub

SignalDesk converts unstructured work updates into reviewable action candidates with source evidence, visible uncertainty, dependency tracking, explainable priority scoring, and a human approval gate.

## Why this project
**Domain:** Technology (with a healthcare-operations scenario). **Area:** Automation / Innovation.
Teams lose track of who owns what, which deadlines are real, and what is blocked, because updates arrive as free text. Plain LLM extraction makes this worse by turning guesses into facts ("might check" becomes "owner: Ananya, due Friday"). SignalDesk is built around preventing exactly that.

## How AI was used
- **Development:** the design, prompt engineering, code and tests were developed with an AI assistant (LLM-assisted pair programming and prompt iteration; see `PROMPT_ITERATION_LOG.md`).
- **In the product:** an optional OpenAI-compatible model does the extraction using the evidence-first prompt in `signaldesk/prompts.py`; its output is then checked by deterministic validators and a human approval gate.
- **Demo mode:** a transparent rule-based engine, so the app works with no API key and behaves repeatably.

## Features
- **Smart Intake:** paste meeting notes, emails, project updates, or incident reports.
- **Two extraction modes:** deterministic demo rules, or optional OpenAI-compatible Chat Completions API.
- **Evidence-linked items:** preserve the source sentence behind each extracted candidate.
- **Uncertainty-aware fields:** tentative vs. confirmed owner, textual vs. explicit date, reported intent, blockers, missing details.
- **Validation checks:** flags evidence not found in source, invented dates, and overconfident claims.
- **Review Queue:** edit, approve, or reject candidates; validation flags block approval.
- **Task Board:** track approved work through Approved, In progress, and Done.
- **Bottleneck Radar:** highlights blockers and missing information.
- **Scenario Lab:** fictional technology, healthcare operations, and product launch scenarios.
- **Activity log and CSV/JSON exports.**
- **SQLite persistence** in the app folder.

## Run locally
Requires Python 3.10+.

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

The app opens in your browser. Demo mode works without an API key.

## Optional real AI mode
1. In Smart Intake, expand **Optional real AI provider**.
2. Enable **Use real AI model for this intake**.
3. Supply an API key, model name, and OpenAI-compatible API base URL.
4. Run extraction and inspect all evidence and validation flags before approving.

For deployment, set `OPENAI_API_KEY` in Streamlit Secrets instead of typing the key. Example `.streamlit/secrets.toml` (do not commit this file):

```toml
OPENAI_API_KEY = "your-key-here"
```

The default endpoint is `https://api.openai.com/v1` and the default model name is `gpt-4o-mini`. Availability and pricing depend on your provider/account. The real-model path is optional; it has not been run against a live provider by the author of this package, so verify it with your own key before relying on it.

## Deploy on Streamlit Community Cloud
1. Create a GitHub repository and upload this project (do not upload `signaldesk.db`, `.venv`, or secrets).
2. Visit https://share.streamlit.io/ and connect GitHub.
3. Select the repository, branch, and `app.py` as the main file.
4. Deploy. Streamlit installs dependencies from `requirements.txt`.
5. If using real AI mode, add `OPENAI_API_KEY` in the app's **Settings → Secrets** dashboard.

**Persistence note:** Community Cloud local filesystem storage may not be durable across restarts/redeploys. SQLite persistence is suitable for a demo session, not production. For durable production storage, use a managed database.

## Tests
Run:
```bash
python -m unittest discover -s tests -v
```

Tests cover demo extraction, tentative language, pronoun-owner handling, schedule signals, priority explanation, and evidence validation. CI runs them on every push (`.github/workflows/tests.yml`).

## Prompt engineering story
The prompt iteration log in `PROMPT_ITERATION_LOG.md` documents failures from an intentionally flawed baseline and guardrails added to prevent:
- converting weekday phrases to invented calendar dates;
- treating tentative or reported owners as confirmed;
- merging similar issues without evidence;
- turning uncertain release timing into a task;
- dropping blockers and missing-information questions.

The deterministic demo engine mirrors selected principles for repeatable demos. It is **not** a general-purpose model. The optional real AI path calls a model and then runs lightweight evidence/consistency checks; those checks are advisory and cannot guarantee correctness.

## Limitations and safety
- Do not use real patient data or sensitive company data in a demo.
- AI extraction and heuristic priority are fallible; human review is required.
- The current app does not integrate with email, Slack, Jira, calendars, or other systems.
- No external action occurs when a task is approved.
