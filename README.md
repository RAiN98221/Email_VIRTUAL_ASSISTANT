# CSV Email Assistant

A local FastAPI web app that previews and sends personalized emails from `filtered_contacts_under35_male_FIXED.csv` through Gmail SMTP. It validates contacts, skips already-contacted email addresses by default, and sends through a persistent SQLite queue at a configurable interval during business hours.

## Setup

1. Copy `.env.example` to `.env`.
2. Set `SMTP_USERNAME`, `SMTP_PASSWORD`, and `FROM_EMAIL`.
3. Keep the matching `IMAP_*` settings enabled if you want each send verified against Gmail Sent Mail.
4. Install and run:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open `http://localhost:8000`, paste your subject/body template, preview, and create the queue.

`SMTP_PASSWORD` must be a Google app password, not your regular Google password.
Put additional contact CSV files in the project root and they will appear in the contact file dropdown. You can also use **Import CSV** in the app to pick a local CSV file; the app saves a validated copy under `uploaded_csv/` and leaves the original file unchanged.

## Live send verification

Every outgoing message gets its own `Message-ID`. After Gmail SMTP accepts the message, the app can log in to Gmail IMAP and look for that same `Message-ID` in Sent Mail. Queue rows store the SMTP message ID plus `verification_status`, `verification_detail`, and `verified_at`.

Verification statuses:

- `sent_mail_found`: Gmail SMTP accepted the message and Gmail Sent Mail contains the same `Message-ID`.
- `sent_mail_not_found`: Gmail SMTP accepted the message, but the Message-ID was not visible in Sent Mail before the timeout.
- `skipped`: Sent Mail verification is disabled or IMAP credentials are not configured.

This confirms Gmail accepted and recorded the outgoing email. It does not prove the recipient inbox delivered or displayed it, because bounces and recipient-side filtering can happen later.

For a controlled one-off live check, call:

```powershell
Invoke-RestMethod http://localhost:8000/api/send-test `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"to_email":"your-test-address@gmail.com"}'
```

## Notes

- The original CSV is not modified.
- Successful sends and Sent Mail verification results are recorded in `email_assistant.sqlite3`.
- The queue survives restarts and the scheduler resumes pending jobs when the app starts.
- Emails are sent one at a time and the next pending item is delayed by the configured interval.
