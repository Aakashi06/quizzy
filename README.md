# Quizzy
**Learn.Quiz.Grow**

A local Class 9 Science learning prototype with a playful quest-board dashboard, persistent light/dark themes, earned XP and levels, daily five-question missions, student accounts, curated quizzes, deterministic server-side grading, explanations, activity heatmap, weighted chapter mastery, revision suggestions and badges.

## Run

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
.venv/bin/python backend/server.py
```

Open http://localhost:8000 and create an account. Python 3.9+ and pypdf are required for the complete notes workflow. SQLite records are saved in `data/quizzy.db`. Sessions are in memory and require signing in again after restarting the server.

## Notes-based AI generation

Install and start Ollama, then run `ollama pull qwen3:4b`. Choose **Upload notes** in the sidebar or **Upload my notes** on the dashboard. Select or drag in a PDF, DOCX, or TXT file (up to 5 MB), or paste text. Review the extracted text before generating. **My progress** includes a chapter-filtered accuracy graph for the most recent eight completed quizzes, with accessible score and date details. Configure `OLLAMA_MODEL` or `OLLAMA_URL` through environment variables to change the model/provider endpoint. Generation has a 120-second timeout. Output must contain exactly the requested number of questions, four distinct options, a valid answer index, an explanation, an allowed difficulty and an exact evidence quote from the notes. These checks do not establish factual correctness or answer ambiguity.

## Included curriculum

255 prototype questions (85 per chapter) across Motion, Force & laws of motion, and Gravitation. These questions and explanations were authored by the coding assistant from general science knowledge; they were not extracted from NCERT or another textbook and have not been independently verified against NCERT. The “Quizzy curated Class 9 Science library” label refers to this local question bank, not an external textbook citation. The included library supports quizzes of 5, 10, 15, or 25 questions at Easy, Medium, or Hard difficulty. Numerical practice variants use deterministic physics formulas. Generated keys remain on the backend until submission. Completed quiz records drive all dashboard values; no fabricated student statistics are shown.

## Implementation

An HTML/CSS/JavaScript frontend and Python HTTP server with SQLite make the first milestone immediately runnable. This differs from the proposed Next.js/FastAPI stack. Each user owns their quiz and attempt records. Passwords are hashed with scrypt and random salts. The server binds only to localhost, uses HttpOnly SameSite cookies, and rejects cross-site browser requests. Activity uses the browser's local calendar date; mastery is weighted accuracy over the last 40 answers per topic, with a five-answer threshold for labels.

## Checks

```sh
python3 -m unittest discover -s backend/tests -v
node --check frontend/app.js
```

## Remaining blueprint work

OCR for scanned PDFs, a provider abstraction with OpenRouter support, retries, durable sessions, database migrations, explicit started attempts, a verified 30–50 question AI evaluation set and deployment hardening. This is a local prototype and has not been prepared for public deployment. AI calls need a running Ollama instance and have not been quality-evaluated here.
