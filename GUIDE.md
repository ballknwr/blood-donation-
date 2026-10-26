# Build and launch roadmap

## 1. Understand the product before adding more code

There are three operational roles: a person requesting help, a volunteer donor, and staff at a licensed blood centre/hospital. A fourth role, an administrator, is needed for a public system to verify centres, investigate abuse, manage directory records and handle privacy requests.

The safe end-to-end workflow is:

1. The treating hospital determines the blood component, group, quantity and urgency.
2. A requester finds verified nearby blood centres. The app shows the freshness and source of availability information, if it has permission to obtain it.
3. The requester contacts a centre to confirm stock. A location match never promises stock.
4. If more help is needed, the requester asks for donor volunteers. Verified requests should expire automatically and alert a bounded number of available, opted-in donors.
5. A donor receives an in-app alert and, with permission, a WhatsApp message. The donor signs in to review it and accepts or declines.
6. An accepting donor completes a preliminary self-declaration. Passing this step means willing to attend screening, not medically eligible.
7. Centre staff confirm the request and appointment, assess eligibility, collect through licensed channels, perform infection testing and arrange component processing/crossmatching.
8. Staff confirm completion and the requester closes the request. Donor availability and donation history are updated with appropriate consent.

The current code implements the request, volunteer matching, notifications and provisional response portions. Centre verification and clinical operations remain external.

## 2. Languages and tools to learn

You do not need to learn every technology at once.

| Tool | What it does in this app | What to learn first |
|---|---|---|
| HTML | Forms, headings, page structure | Semantic elements, labels, form validation |
| CSS | Mobile layout and visual design | Flexbox, Grid, spacing, responsive breakpoints |
| JavaScript | Browser interactions and API calls | Objects, events, promises, fetch, DOM updates |
| Python | Accounts, request validation and matching | Functions, dictionaries, modules, exceptions |
| Flask | Routes and sessions | HTTP, JSON, request/response, authentication |
| SQL / SQLite | Stores users, donors and requests | SELECT, INSERT, UPDATE, joins, constraints, transactions |
| Git | Tracks and reviews changes | status, diff, add, commit, branches, push |
| HTTP and JSON | Connects browser, backend and Meta | Methods, status codes, headers, authentication |

Start by running the app, changing page text, tracing one form through JavaScript into its Flask route, and inspecting the database with test data. Then work on one feature at a time with tests. React and TypeScript are optional later improvements, not requirements for this version. For native Android/iOS after the web workflow is proven, React Native with TypeScript or Flutter with Dart are reasonable options. Keep matching, authorization and clinical rules on the server.

## 3. How the implemented app works

```text
Browser (HTML + CSS + JavaScript)
         | same-origin JSON API + session cookie + CSRF token
         v
Flask application ---- SQLite database
         |
         +-- in-app notifications, fetched every 15 seconds
         |
         +-- durable outbox -- manual worker command -- Meta WhatsApp Cloud API
                                                    (disabled by default)
```

The browser never gets a WhatsApp token. Backend access to the database uses parameterized SQL. Passwords use Werkzeug's salted password hashing. Sessions store the user ID, not passwords. CSRF tokens protect write requests; each action also checks the logged-in user's ownership or donor assignment. Browser rendering escapes user-provided strings.

### Database tables

| Table | Purpose |
|---|---|
| `users` | Account identity and password hash |
| `donors` | One donor profile per user; group, area, availability, phone and consent |
| `centres` | Sample location directory; records explicitly flagged as sample |
| `requests` | Hospital, location, units, group, owner and open/closed status |
| `matches` | A donor invited to a request and their pending/accepted/declined response |
| `notifications` | Private in-app messages belonging to an account |
| `outbox` | WhatsApp intent and processing status per matched donor |

### Matching algorithm

The server excludes the requester, unavailable donors, different groups, and profiles reporting a donation within 120 days. It computes Haversine distance using latitude/longitude, keeps candidates within 50 km, sorts by distance and alerts at most five. This is straight-line distance, not a route calculation. Donor matching is initiated by the request submission, independent of the fictional centre list.

For a city-scale prototype this is enough. For India-wide scale, use PostgreSQL with PostGIS, a spatial index and a background job queue. Add configurable radius expansion, availability schedules, request expiry, cooldowns, per-donor alert limits and escalation after a timeout. Use deduplication and atomic state transitions to prevent repeated or contradictory notifications.

### API map

| Method and route | Purpose |
|---|---|
| `GET /api/session` | Current account and CSRF token |
| `POST /api/register`, `/api/login`, `/api/logout` | Account lifecycle |
| `GET /api/centres?lat=...&lon=...` | Sample centres ordered by distance |
| `POST /api/donor` | Save/update the current account's donor profile |
| `POST /api/requests` | Create a request and matching invitations |
| `GET /api/dashboard` | Current user's requests, inbox and notifications |
| `POST /api/matches/<id>/respond` | Invited donor's provisional response |
| `POST /api/requests/<id>/close` | Owner closes their request |
| `POST /api/notifications/read` | Mark the user's notifications read |

All POST routes require `X-CSRF-Token` from the session endpoint. The browser client handles this automatically.

## 4. Medical screening: why three months is not enough

Do not implement “has not donated in three months” as the only eligibility criterion. Indian whole-blood guidance commonly distinguishes intervals, including 90 days for men and 120 days for women, while other donation types and circumstances have different requirements. Confirm the current applicable NBTC/NACO/CDSCO guidance with a licensed blood-centre medical officer before implementing policy; this guide is not a clinical protocol.

The prototype uses a conservative 120-day self-reported minimum for everyone and limits volunteer registration to ages 18–65 and weight at least 45 kg. These checks are incomplete. Haemoglobin, collection volume, pregnancy/postpartum status, medications, illness, infections, recent procedures, vaccination and other deferrals require professional assessment. Health questions should be designed with clinicians and collect only necessary data, with an appropriate retention policy.

Blood group is also self-reported here. Never authorize transfusion using a user's selected group or a software compatibility table. Licensed-centre testing and crossmatching remain necessary. Do not build direct person-to-person transfusion arrangements or paid blood brokerage.

## 5. How to connect WhatsApp officially

Use **Meta's WhatsApp Business Platform Cloud API**, or a provider such as Twilio if you prefer its onboarding and billing. This code uses Meta directly. Do not automate WhatsApp Web, scrape accounts or use a personal WhatsApp session as a messaging server.

Official starting points:

- [WhatsApp Cloud API documentation](https://developers.facebook.com/docs/whatsapp/cloud-api/)
- [Meta WhatsApp platform](https://developers.facebook.com/docs/whatsapp/)
- [WhatsApp Business messaging policy](https://business.whatsapp.com/policy)

Meta changes console screens, API versions, template classifications, pricing and limits. Follow its current documentation rather than assuming a fixed approval time, free quota or price.

### A. Create your Meta setup

1. Create a Meta developer account and the appropriate app for WhatsApp Business use.
2. Connect a business portfolio and WhatsApp Business Account. Complete the verification steps Meta requires for your usage.
3. In development, use Meta's test sender and allowed test recipients. For production, register an eligible business phone number and configure billing and business access as required.
4. Obtain the **phone number ID**, which is a numeric API resource ID, not the phone number itself.
5. Obtain a scoped access token with the necessary WhatsApp messaging permission. Short-lived test tokens expire; use Meta's documented production token/system-user process for deployment.
6. Store tokens only in a backend secret manager or secure environment settings. Never put them in JavaScript, screenshots, source control or a mobile bundle.

### B. Obtain consent and verify the recipient

Ask for explicit, recorded permission for blood-request notifications. Explain who sends messages, the purpose, opt-out and how the number is stored. Implement a phone ownership verification flow before enabling live sending; the prototype deliberately leaves `phone_verified=0` and provides no endpoint to bypass it.

A production OTP implementation needs a verified provider, server-side challenge storage, short expiry, hashed codes, attempt limits, resend cooldowns, enumeration resistance and abuse monitoring. Do not mark a phone verified based solely on a checkbox or a test message. Reset verification when the number changes (the code already does this).

The current opt-in can be withdrawn by editing the donor profile and saving it. A production system should additionally honor WhatsApp STOP/unsubscribe events and maintain a consent audit trail. Consent withdrawal and account deletion must take effect in queued workers too.

### C. Get an approved message template

A blood-request alert is generally business-initiated and needs an approved template outside an eligible conversation window. Submit a policy-compliant template to Meta. Do not send sensitive medical details.

The implemented sender expects **exactly one body parameter**, a request ID. An example template body is:

> A new volunteer blood donation request, reference {{1}}, is available. Sign in to RakhtConnect to review it. Donation is subject to licensed blood centre screening. You can opt out in your donor profile.

Name it, for example, `blood_donor_request`, choose the language you actually approved, and follow Meta's classification decision. This prototype omits a dynamic link; you can include your real, static HTTPS app address in the approved template text. Do not put example or local URLs in messages to real donors. Template structure and the backend parameters must match exactly.

### D. Configure the server

The following are **variable names**, not values to paste publicly:

| Variable | Purpose |
|---|---|
| `WHATSAPP_MODE` | Leave `dry-run` for development; `live` enables queued API sends |
| `WHATSAPP_TOKEN` | Backend-only Meta access token |
| `WHATSAPP_PHONE_NUMBER_ID` | Numeric sender resource ID |
| `WHATSAPP_TEMPLATE` | Exact approved template name |
| `WHATSAPP_TEMPLATE_LANGUAGE` | Exact approved language code, default `en` |
| `WHATSAPP_API_VERSION` | A supported version for your Meta app; example config uses `v23.0` |

Confirm the API version's current support before deployment. HTTPS egress to `graph.facebook.com` is needed for live sends. Local dry-run needs no Meta account, credentials or network access to Meta.

After implementing and validating phone verification, configuring approved recipients and obtaining consent, create a request. Verified opted-in matched donors get `queued` outbox entries. Then run:

```bash
.venv/bin/flask --app app send-whatsapp
```

The command sends queued items once and exits. It is not a permanently running background service. In production, invoke a job worker or scheduled task with monitoring. A successful API response is stored as `submitted`, **not delivered**. Ambiguous errors become `unknown` and are not automatically retried because the original call may have reached Meta. Reconcile in Meta before retrying. A crash can leave a record `sending`; that also needs reconciliation. A production worker needs robust retry/backoff, provider status handling, concurrency control and rate limiting.

Do not retroactively turn old `dry-run` messages into live alerts; create a new, still-valid verified request after live setup is ready. Dry-run records are intentionally not queued for delivery.

### E. Accept/decline on WhatsApp

The current donor responds in the authenticated app. Native WhatsApp reply buttons require additional work:

1. Create a Meta-approved interactive template with suitable quick replies, and update the sender's payload to match it.
2. Provide a public HTTPS webhook endpoint and implement Meta's GET verification handshake using a separate verification token.
3. Validate POST webhook signatures (`X-Hub-Signature-256`) against your Meta app secret over the exact raw request body.
4. Map the WhatsApp sender to a verified account and the reply payload to a valid invitation. Use opaque, bound identifiers; do not trust a numeric request ID alone.
5. Deduplicate events, reject expired or closed requests and unauthorized senders, and record the response transactionally.
6. Treat an “accept” button as willingness to review, then send the donor into the authenticated screening flow. Never skip screening or infer clinical consent from a quick reply.
7. Process delivery, read, failure and opt-out events. Keep logs free of tokens, message bodies and sensitive medical information.

These webhook and quick-reply features are not implemented in this version. Do not configure Meta to point to a nonexistent webhook route.

## 6. Real Indian centre data

Start with [e-RaktKosh](https://eraktkosh.mohfw.gov.in/) and discussions with licensed blood centres and relevant authorities. Confirm current official access paths, licenses and integration permissions. There is no verified national API connected to this repository, and no claim that every Indian centre is registered.

Do not scrape or republish a website merely because it is accessible. Agree on data access, update frequency and stock freshness. A useful centre record needs its official identity/licence details, address, validated coordinates, official contact, operating hours, component services, source, verification date and update timestamp. Distinguish centre location, claimed stock and confirmed availability in the interface.

For centre onboarding, add a staff/admin portal, document verification, role-based access and an audit history. A self-registration form must not instantly produce a “verified centre.” Remove sample records before importing validated data; do not mark sample rows as verified.

A later centre-first routing flow should use verified availability and a user-set radius: show centre options, ask whether the hospital has confirmed availability, and offer volunteer outreach if needed. Travel time estimates require a mapping/routing provider, billing controls and proper map attribution.

## 7. From prototype to a public service

Build and review these milestones before inviting real patients:

### Milestone 1: Verified identities and accountable operations

Add email/phone verification, account recovery, request verification by a hospital, roles for staff/admins, abuse reporting, moderation, duplicate detection and request expiration. Limit request creation, donor alerts and OTP use. The existing login throttle is only per process and does not replace shared rate limiting.

### Milestone 2: Data protection

Review applicable Indian privacy law, including the DPDP framework and current rules, with qualified counsel. Define your lawful processing basis, consent notices, purpose limits, retention periods, deletion/export procedures, breach response and processor agreements. Do not promise compliance just because a checkbox exists.

Use HTTPS, secure cookies, managed secrets, least-privilege access, encrypted storage/backups, access auditing and consent history. Minimize donor location precision and restrict access to contact/health information. Add an account deletion workflow that also cancels queued notifications and follows retention obligations. Do not collect Aadhaar simply to make a prototype look verified.

### Milestone 3: Reliable infrastructure

Move to managed PostgreSQL/PostGIS and versioned database migrations. Use a production WSGI server behind HTTPS; do not deploy `python app.py` as your public server. Use a stable secret, `COOKIE_SECURE=1`, separate staging/production databases and least-privilege credentials. Add a background worker and queue, health checks, alerts, backups and restore drills. Avoid logging health data or session secrets.

### Milestone 4: Notifications

Add an authenticated web push subscription flow with a service worker and VAPID keys for background browser delivery, or Firebase Cloud Messaging/APNs for native apps. Collect permissions and support opt-out. Add Meta webhooks, delivery tracking and a bounded escalation policy. No notification channel guarantees immediate delivery.

### Milestone 5: Clinical partnership and accessibility

Have licensed-centre clinicians review wording and screening. Pilot with a small set of verified centres, train coordinators, define escalation responsibilities and test unavailability scenarios. Support relevant Indian languages, screen readers, large text, low bandwidth and slow devices. Keep an obvious emergency route to 112 and the treating hospital.

### Milestone 6: Testing and launch

Test account isolation, consent withdrawal, request expiration, duplicate sends, concurrent donor responses, worker crashes, slow networks, provider failures, abuse and backups. Run mobile/desktop browser tests, accessibility checks, load tests, dependency/security review and a privacy/clinical review. Monitor successful connections separately from clinically completed donations. Do not advertise a guaranteed supply of blood.

## 8. Suggested learning and implementation order

1. Learn enough HTML/CSS to understand the two forms and mobile layout.
2. Learn JavaScript events and `fetch`; trace `request-form` into `/api/requests`.
3. Learn Python/Flask; modify only a small, well-understood route and add a test.
4. Learn SQL; understand how users, requests and matches connect.
5. Work through the two-account manual demo in README.
6. Add verified identities and hospital request approval before real messaging.
7. Use Meta's test setup, then implement phone verification, approved templates and delivery webhooks.
8. Partner with licensed centres and integrate permissioned data.
9. Harden and deploy staging, complete reviews, then pilot publicly in a limited area.
10. Add native mobile apps only after the core coordination process is useful and reliable.

For the current version, the next meaningful external steps are obtaining a clinical/centre partner and deciding on verified identity and messaging providers. Buying a domain or adding a native app alone does not solve those requirements.
