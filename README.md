# CSV Email Assistant

A local FastAPI web app that previews and sends personalized emails from `filtered_contacts_under35_male_FIXED.csv` through Gmail SMTP. It validates contacts, skips already-contacted email addresses by default, and sends through a persistent SQLite queue at a configurable interval during business hours.

## Setup

1. Copy `.env.example` to `.env`.
2. Set `SMTP_USERNAME`, `SMTP_PASSWORD`, and `FROM_EMAIL`.
3. Install and run:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open `http://localhost:8000`, paste your subject/body template, preview, and create the queue.

`SMTP_PASSWORD` must be a Google app password, not your regular Google password.
Put additional contact CSV files in the project root and they will appear in the contact file dropdown.

## Notes

- The original CSV is not modified.
- Successful sends are recorded in `email_assistant.sqlite3`.
- The queue survives restarts and the scheduler resumes pending jobs when the app starts.
- Emails are sent one at a time and the next pending item is delayed by the configured interval.
