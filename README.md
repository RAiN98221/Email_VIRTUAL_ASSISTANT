# CSV Email Assistant

A local FastAPI web app that previews and sends personalized emails from a contacts CSV through an SMTP email provider (Brevo recommended, or custom SMTP). It validates contacts, skips already-contacted email addresses by default, and sends through a persistent SQLite queue at a configurable interval during business hours.

## Setup

1. Copy `.env.example` to `.env`.
2. Pick a provider with `MAIL_PROVIDER` and set `SMTP_HOST`, `SMTP_PORT`, `SMTP_SECURITY`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `FROM_EMAIL`, and optional `FROM_NAME`. You can also add/manage providers in **Settings > Email Provider** (stored locally in the app database; an active in-app account overrides `.env`).
3. Install and run:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open `http://localhost:8000`, paste your subject/body template, preview, and create the queue.

Put additional contact CSV files in the project root and they will appear in the contact file dropdown. You can also use **Import CSV** in the app to pick a local CSV file; the app saves a validated copy under `uploaded_csv/` and leaves the original file unchanged.

## Email providers

### Brevo (recommended)

[Brevo](https://www.brevo.com/) offers a free tier of 300 emails/day over its SMTP relay. Setup ([SMTP docs](https://developers.brevo.com/docs/smtp-integration)):

1. Create a Brevo account.
2. Authenticate your sending domain (DKIM + Brevo code + DMARC) on the [Domains page](https://app.brevo.com/senders/domain/list). You need your own domain - free addresses like `@gmail.com` cannot be authenticated.
3. Create a verified sender (`you@your-domain.com`) on the [Senders page](https://app.brevo.com/senders/list).
4. Generate an SMTP key (not an API key) at [SMTP & API > SMTP](https://app.brevo.com/settings/keys/smtp).
5. In the app, open **Settings > Email Provider**, choose **Brevo**, and enter your From name/email, the SMTP login, and the SMTP key. Or set the env vars:

```
MAIL_PROVIDER=brevo
SMTP_HOST=smtp-relay.brevo.com
SMTP_PORT=587
SMTP_SECURITY=starttls
SMTP_USERNAME=your-brevo-smtp-login
SMTP_PASSWORD=your-brevo-smtp-key
FROM_EMAIL=you@your-domain.com
FROM_NAME=Your Name
```

The app trusts SMTP acceptance from your provider. It does not confirm recipient inbox delivery.

### Custom SMTP

Choose **Custom SMTP** in **Settings > Email Provider** (or set `MAIL_PROVIDER=smtp`) and enter your provider's host, port, security mode, login, and password.

## Live send test

For a controlled one-off live check, call:

```powershell
Invoke-RestMethod http://localhost:8000/api/send-test `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"to_email":"your-test-address@example.com"}'
```

This confirms the SMTP server accepted the message. It does not prove the recipient inbox delivered or displayed it.

## Automatic suppression

The app keeps a local do-not-email list in SQLite. Suppressed contacts are marked invalid during preview and are not queued.

Automatic sources:

- Hard SMTP failures: clear 5xx recipient failures are suppressed as `bounced` or `blocked`.

Suppression state stays in `email_assistant.sqlite3`; source CSV files are not modified. View the current list with `GET /api/suppressions` or the Suppressed section in the app.

## Automatic job pause

Jobs can auto-pause after a configurable number of failed sends. The queue form includes `Max failures` and `Auto-pause on failures`; when the threshold is reached, the job status changes to `paused` and the pause reason is shown in the Jobs section. Resume keeps the existing queue and clears the pause reason.

## Git on Windows / Cursor

Run once after cloning (or if `git status` looks wrong):

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup-git.ps1
```

This installs repo hooks, stores the Git index under `%LOCALAPPDATA%/email_virtual_assistant/git-indexes/` (avoids sandbox locks on `.git/index`), and configures your local VS Code terminal env. For ad-hoc commands in Cursor, use:

```powershell
.\scripts\git.ps1 status
.\scripts\git.ps1 add -A
.\scripts\git.ps1 commit -m "message"
.\scripts\git.ps1 push origin dev
```

If Git still looks stale, run `scripts/repair-git.ps1` or `scripts/sync-git-index.ps1` (refreshes what Cursor's source control panel reads).

## Notes

- The original CSV is not modified.
- Successful sends are recorded in `email_assistant.sqlite3`.
- Hard recipient failures are recorded as suppressed contacts in `email_assistant.sqlite3`.
- Repeated send failures can auto-pause a job before the app continues through the remaining queue.
- The queue survives restarts and the scheduler resumes pending jobs when the app starts.
- Emails are sent one at a time and the next pending item is delayed by the configured interval.
