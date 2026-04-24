# Agent Instructions — Bridge Club Aanmeldingsapp

This file defines the rules that all AI agents and contributors must follow when working on this project.

---

## Core Rules

1. **One user story per change.** Every code change must implement exactly one user story from [spec.md](spec.md). Never combine multiple user stories in a single commit or pull request.
2. **Tests first.** Before marking a user story as done, at least one automated test must exist that covers its acceptance criteria.
3. **All tests must pass.** After every change, run the full test suite. Do not proceed if any test fails.
4. **The app must build without errors.** After every change, verify the app starts successfully. Do not leave the app in a broken state.

---

## Workflow per User Story

Follow these steps in order for every user story:

### Step 1 — Identify the story
- Reference the user story by its ID (e.g. `US-01`) from [spec.md](spec.md).
- Read the full story including all acceptance criteria before writing any code.
- Do not start work on a story if a previous story's tests are failing.

### Step 2 — Write the test(s) first
- Create or extend test file(s) in `tests/` before implementing the feature.
- Each acceptance criterion must map to at least one test case.
- Tests must be failing (red) before implementation starts.
- Test file naming: `tests/test_<area>_<story_id_lowercase>.py`  
  Example: `tests/test_auth_us01.py`

### Step 3 — Implement the feature
- Implement only what is needed to make the story's tests pass.
- Do not implement functionality from other user stories, even if it seems convenient.
- Follow the project coding conventions below.

### Step 4 — Verify
Run these commands in order. All must succeed before the story is considered done:

```bash
# 1. Run the full test suite
pytest tests/ -v

# 2. Verify the app starts without errors
python -c "from app.main import app; print('Build OK')"
```

- If any test fails, fix the implementation or the test before continuing.
- If the app fails to start, fix the error before continuing.

### Step 5 — Confirm done
A user story is **done** when:
- [ ] All acceptance criteria have at least one test.
- [ ] All tests in the full suite pass (`pytest` exits with code 0).
- [ ] The app starts without errors.
- [ ] No unrelated files were modified.

### Step 6 — Commit to git
Once all done criteria are met, commit the change:

```bash
git add -A
git commit -m "<US-XX>: <short description of what was implemented>"
```

- The commit message must start with the user story ID (e.g. `US-01`).
- One commit per user story. Do not bundle multiple stories in one commit.
- Do not commit if any test is failing or the app does not start.

---

## Project Structure

```
app/
  main.py             # FastAPI app entry point
  models.py           # SQLAlchemy ORM models
  schemas.py          # Pydantic schemas
  database.py         # DB session and engine setup
  auth.py             # OAuth and session handling
  routes/             # One file per functional area
    auth.py
    registrations.py
    evenings.py
    members.py
    admin.py
  templates/          # Jinja2 HTML templates
  static/             # CSS, icons, service worker
tests/
  conftest.py         # Shared fixtures (test DB, test client)
  test_<area>_<us_id>.py
alembic/              # Database migrations
spec.md               # User stories and acceptance criteria
implementatieplan.md  # Implementation plan
agents.md             # This file
```

---

## Coding Conventions

- **Language:** Python 3.12+
- **Framework:** FastAPI with Jinja2 templates
- **ORM:** SQLAlchemy (declarative models in `app/models.py`)
- **Migrations:** Alembic — create a migration for every model change
- **Tests:** pytest with `httpx.AsyncClient` for route tests; use an in-memory SQLite database in tests
- **Formatting:** Black (`black app/ tests/`)
- **Linting:** Ruff (`ruff check app/ tests/`)
- **HTML/CSS:** Jinja2 templates only; no JavaScript frameworks; vanilla JS only where strictly necessary (service worker, install prompt)
- **Secrets:** Never hardcode secrets; use environment variables loaded via `python-dotenv`

---

## Test Conventions

- Every test file must import from `tests/conftest.py` for the test client and database fixtures.
- Use descriptive test function names: `test_<us_id>_<what_is_being_tested>`  
  Example: `test_us01_invitation_token_is_unique`
- Test the happy path **and** at least one failure/edge case per acceptance criterion.
- Do not use production database credentials in tests; always use the in-memory test database.
- Shared fixtures go in `tests/conftest.py`, not duplicated across files.

### Minimum test coverage per story

| Story area | Minimum tests |
|---|---|
| Auth & invitations (US-01 – US-05) | 2 per story |
| Role management (US-06 – US-07) | 2 per story |
| Public view (US-08 – US-09) | 1 per story |
| Registration flow (US-10 – US-15) | 2 per story |
| Modification flow (US-16 – US-22) | 2 per story |
| Admin features (US-23 – US-28) | 1 per story |
| Member import (US-29 – US-32) | 2 per story |
| GDPR (US-33 – US-36) | 1 per story |
| PWA & UX (US-37 – US-40) | 1 per story |

---

## Scope Boundaries

- Do not modify `spec.md` or `implementatieplan.md` as part of a code change.
- Do not refactor code unrelated to the current user story.
- Do not add dependencies not listed in `requirements.txt` without updating that file.
- Do not change the database schema without creating an Alembic migration.

---

## Commands Reference

```bash
# Install dependencies
pip install -r requirements.txt

# Run the app (development)
uvicorn app.main:app --reload

# Run all tests
pytest tests/ -v

# Run tests for a specific story
pytest tests/ -v -k "us01"

# Check formatting
black --check app/ tests/

# Check linting
ruff check app/ tests/

# Create a new Alembic migration
alembic revision --autogenerate -m "<description>"

# Apply migrations
alembic upgrade head

# Commit a completed user story
git add -A
git commit -m "US-XX: <short description>"
```
