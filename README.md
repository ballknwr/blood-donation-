# RakhtConnect

A mobile-friendly Indian blood-donation coordination prototype. Built from an empty repository with Python, Flask, SQLite, HTML, CSS and JavaScript. It connects requesters to willing volunteers; it is **not an emergency dispatch service, a verified national blood-bank directory, or a clinical eligibility system**.

## Start in five minutes

Requires Python 3.12 or newer. No Node build step or paid service is needed.

```bash
cd /workspace/blood-donation-
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python app.py
```

The development server uses port 5000. Open the app through your development environment's port forwarding, or your local browser on port 5000. Do not expose Flask's development server to public traffic. On a personal Windows computer use `.venv\Scripts\python` and `.venv\Scripts\pip` instead.

SQLite initializes automatically at `instance/app.sqlite`. Stop with Ctrl+C; restart with the same command. Without `APP_SECRET`, restart invalidates sessions but preserves accounts and requests. To keep sessions across restarts, set a long randomly generated `APP_SECRET` in your environment; never commit it. `.env.example` documents optional variables but is **not loaded automatically**. Use your hosting platform's secure environment-variable settings or export the variables in your shell.

## Try the whole flow

1. Create a donor account using a test email and a unique password with at least 12 characters. There are no hard-coded accounts.
2. Choose Bengaluru in the location bar. Save a donor profile with group O+, age 25, weight 65 kg, and a test phone in `+91XXXXXXXXXX` format. Leave the donation date blank if never donated, and check availability and storage consent. WhatsApp opt-in is optional.
3. Open a separate private/incognito browser window. Create a different requester account. This prevents one account's session from replacing the other's.
4. In that account, post an O+ request for a test hospital in Bengaluru. It should report one matched volunteer. Your own account is never matched to your own request.
5. In the donor window, refresh the connection desk or wait up to 15 seconds. Review the in-app notification and donor inbox. WhatsApp should show `dry-run` when opted in; **no WhatsApp message was sent**.
6. Review and accept, then complete the self-declaration. A date within the last 120 days is rejected. Alternatively decline the request. Responses cannot subsequently be changed through this prototype.
7. In the requester window, refresh and see the donor's provisional acceptance. Hospital staff still need to verify the request and coordinate screening; there is no automatic booking or contact exchange.
8. Close the request when no longer needed. Closed requests cannot receive further acceptances.

Use invented test information, not actual patient records. The app does not collect a patient's name, diagnosis or payment.

## Implemented

- Account creation, password hashing, login/logout and cookie sessions.
- CSRF protection, ownership checks, input validation and parameterized database queries.
- Clearly labelled fictional centre directory ordered by straight-line distance.
- City selection, manual Indian coordinates, and optional browser geolocation.
- Donor profiles, availability, donation date and separate WhatsApp consent.
- Requests for 1–10 units with a hospital and city.
- Up to five nearest same-group available volunteers within 50 km. Recently donated profiles are excluded.
- In-app notifications, polling, read state, and optional foreground browser notifications.
- Accept/decline, a preliminary screening form, owner status updates and request closing.
- Durable WhatsApp outbox and an opt-in Meta Cloud API sender command, disabled by default.
- Automated integration tests. No live external messaging occurs in the tests.

## Deliberate limits

- **Centres are fictional samples.** No real centre or donor is pre-registered. There is no live inventory. Never visit a sample location.
- This version offers the directory first and lets the requester explicitly alert volunteers. It does not automatically decide whether a nearby centre can meet the need. Distance alone cannot answer whether the correct component is available.
- Donor matching uses the same stated group as a lead, not a transfusion compatibility algorithm. The model does not yet handle platelets, plasma, apheresis or rare phenotypes.
- It screens conservatively for at least 120 days since donation. A universal “last three months” rule is inappropriate; actual rules depend on donor and donation type, current Indian guidance, and clinical assessment. The app never marks anyone medically eligible.
- Browser notifications work only while the page is open. No background mobile push, service worker, WhatsApp reply buttons or delivery webhooks are implemented.
- Matching happens when a request is posted. Registering later does not backfill earlier requests. There is no repeated automatic escalation, expiry, appointment scheduling, hospital chat or completed-donation tracking yet.
- Acceptance records willingness. It does not confirm transport, a screened donation, blood availability, crossmatching or treatment. The donor must use the hospital's official channels before travelling.
- Requester sees donor name, approximate distance and status, but not phone or exact donor coordinates. Users supply unverified profile names.
- Email/mobile verification, account recovery, deletion UI, moderation and hospital verification are not implemented. **Live WhatsApp is intentionally gated on phone verification**, and this prototype does not offer an OTP flow. Use dry-run until one is implemented.
- Session state is protected, but SQLite contains sensitive profile data without application-level encryption. This is a local learning prototype, not a production health-data platform.

## Project layout

```text
app.py                 Flask routes, SQLite schema, matching, screening, WhatsApp worker
requirements.txt       Pinned Python dependencies
.env.example           Configuration names (never real credentials)
templates/index.html   Page and accessible forms/dialogs
static/style.css       Responsive design
static/app.js          Forms, API calls, inbox, polling and browser alerts
tests/test_app.py      API integration tests using temporary databases
GUIDE.md                Learning path, architecture, WhatsApp and launch roadmap
instance/app.sqlite    Generated local data, ignored by Git
```

## Run checks

```bash
.venv/bin/python -m unittest discover -s tests -v
node --check static/app.js  # optional if Node is installed
.venv/bin/flask --app app send-whatsapp  # safe dry-run by default
```

For WhatsApp setup and a detailed explanation of what to learn and build next, read [GUIDE.md](GUIDE.md).
