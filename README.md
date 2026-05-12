# Outlook CSV Email Assistant

A local FastAPI web app that previews and sends personalized Outlook emails from `filtered_contacts_under35_male_FIXED.csv` through Microsoft Graph. It validates contacts, skips already-contacted email addresses by default, and sends through a persistent SQLite queue at a configurable interval during business hours.

## Setup

1. Create a Microsoft Entra app registration for a public client/native app.
2. Add redirect URI: `http://localhost:8000/auth/callback`.
3. Grant delegated Microsoft Graph permissions: `Mail.Send` and `User.Read`.
4. Copy `.env.example` to `.env` and set `MICROSOFT_CLIENT_ID`.
5. Install and run:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open `http://localhost:8000`, connect Outlook, paste your subject/body template, preview, and create the queue.

## Notes

- The original CSV is not modified.
- Successful sends are recorded in `email_assistant.sqlite3`.
- The queue survives restarts and the scheduler resumes pending jobs when the app starts.
- Emails are sent one at a time and the next pending item is delayed by the configured interval.
