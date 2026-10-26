"""RakhtConnect: local-development prototype, not a clinical decision system."""
import functools
import json
import math
import os
import re
import secrets
import sqlite3
import time
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

import click
from flask import Flask, g, jsonify, render_template, request, session
from werkzeug.security import check_password_hash, generate_password_hash

GROUPS = ('A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-')
MIN_DAYS = 120  # Conservative prototype screen, not a clinical eligibility decision.

SCHEMA = '''
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
 password TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS donors (
 user_id INTEGER PRIMARY KEY REFERENCES users(id), blood_group TEXT NOT NULL,
 city TEXT NOT NULL, lat REAL NOT NULL, lon REAL NOT NULL, phone TEXT NOT NULL,
 whatsapp_consent INTEGER NOT NULL DEFAULT 0, phone_verified INTEGER NOT NULL DEFAULT 0,
 available INTEGER NOT NULL DEFAULT 1, last_donation TEXT, age INTEGER NOT NULL,
 weight REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS centres (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, city TEXT NOT NULL,
 lat REAL NOT NULL, lon REAL NOT NULL, sample INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS requests (
 id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
 blood_group TEXT NOT NULL, units INTEGER NOT NULL, hospital TEXT NOT NULL,
 city TEXT NOT NULL, lat REAL NOT NULL, lon REAL NOT NULL, status TEXT NOT NULL DEFAULT 'open',
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS matches (
 id INTEGER PRIMARY KEY, request_id INTEGER NOT NULL REFERENCES requests(id),
 donor_id INTEGER NOT NULL REFERENCES users(id), distance REAL NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL,
 UNIQUE(request_id,donor_id)
);
CREATE TABLE IF NOT EXISTS notifications (
 id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
 message TEXT NOT NULL, created_at TEXT NOT NULL, read INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS outbox (
 id INTEGER PRIMARY KEY, match_id INTEGER UNIQUE NOT NULL REFERENCES matches(id),
 status TEXT NOT NULL, detail TEXT NOT NULL, updated_at TEXT NOT NULL
);
'''


def now():
    return datetime.now(timezone.utc).isoformat()


def distance(lat1, lon1, lat2, lon2):
    a, b = math.radians(lat1), math.radians(lat2)
    h = math.sin((b-a)/2)**2 + math.cos(a)*math.cos(b)*math.sin(math.radians(lon2-lon1)/2)**2
    return round(6371 * 2 * math.asin(min(1, math.sqrt(h))), 1)


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(SECRET_KEY=os.environ.get('APP_SECRET') or secrets.token_hex(32),
                      DATABASE=os.environ.get('DATABASE_PATH', str(Path(__file__).parent / 'instance/app.sqlite')),
                      MAX_CONTENT_LENGTH=16_384, SESSION_COOKIE_HTTPONLY=True,
                      SESSION_COOKIE_SAMESITE='Lax', SESSION_COOKIE_SECURE=os.getenv('COOKIE_SECURE') == '1')
    if test_config:
        app.config.update(test_config)
    Path(app.config['DATABASE']).parent.mkdir(parents=True, exist_ok=True)

    def db():
        if 'db' not in g:
            g.db = sqlite3.connect(app.config['DATABASE'], timeout=10)
            g.db.row_factory = sqlite3.Row
            g.db.execute('PRAGMA foreign_keys=ON')
        return g.db

    @app.teardown_appcontext
    def close(_):
        if 'db' in g:
            g.db.close()

    with app.app_context():
        db().executescript(SCHEMA)
        if not db().execute('SELECT 1 FROM centres LIMIT 1').fetchone():
            db().executemany('INSERT INTO centres(name,city,lat,lon) VALUES(?,?,?,?)', [
                ('Sample Central Blood Centre', 'Bengaluru', 12.9716, 77.5946),
                ('Sample North Blood Centre', 'Bengaluru', 13.015, 77.600),
                ('Sample Mumbai Blood Centre', 'Mumbai', 19.076, 72.8777),
                ('Sample Delhi Blood Centre', 'New Delhi', 28.6139, 77.2090),
            ])
            db().commit()

    def fail(message, status=400):
        return jsonify(error=message), status

    def auth(fn):
        @functools.wraps(fn)
        def wrapped(*args, **kwargs):
            if not session.get('uid'):
                return fail('Please sign in first.', 401)
            return fn(*args, **kwargs)
        return wrapped

    @app.before_request
    def protect():
        if request.path.startswith('/api/') and request.method not in ('GET', 'HEAD', 'OPTIONS'):
            token = session.get('csrf')
            if not token or not secrets.compare_digest(request.headers.get('X-CSRF-Token', ''), token):
                return fail('Refresh the page and try again (security token missing).', 403)

    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Content-Security-Policy'] = "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
        if request.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.errorhandler(400)
    def bad_request(_):
        return fail('Invalid request data.')

    @app.errorhandler(413)
    def too_large(_):
        return fail('Request is too large.', 413)

    def data():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            raise ValueError('Send a JSON object.')
        return payload

    def text(d, key, minimum=1, maximum=120):
        value = d.get(key)
        if not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum:
            raise ValueError(f'{key.replace("_", " ").title()} must be {minimum}–{maximum} characters.')
        return value.strip()

    def coords(d):
        lat, lon = float(d['lat']), float(d['lon'])
        if not math.isfinite(lat) or not math.isfinite(lon) or not (6 <= lat <= 38 and 68 <= lon <= 98):
            raise ValueError('Use valid coordinates within India.')
        return lat, lon

    def group(d):
        value = d.get('blood_group')
        if value not in GROUPS:
            raise ValueError('Choose a valid blood group.')
        return value

    @app.errorhandler(ValueError)
    @app.errorhandler(KeyError)
    @app.errorhandler(TypeError)
    @app.errorhandler(OverflowError)
    def validation(error):
        return fail(str(error) if isinstance(error, ValueError) else 'A required field is missing or invalid.')

    @app.get('/')
    def index():
        return render_template('index.html')

    @app.get('/api/session')
    def whoami():
        session.setdefault('csrf', secrets.token_hex(24))
        user = db().execute('SELECT id,name,email FROM users WHERE id=?', (session.get('uid'),)).fetchone()
        donor = db().execute('SELECT blood_group,city,available,last_donation,whatsapp_consent,phone_verified FROM donors WHERE user_id=?',
                             (session.get('uid'),)).fetchone()
        return jsonify(csrf=session['csrf'], user=dict(user) if user else None,
                       donor=dict(donor) if donor else None, whatsapp_mode=os.getenv('WHATSAPP_MODE','dry-run'))

    @app.post('/api/register')
    def register():
        d = data()
        name = text(d, 'name', 2, 80)
        email = text(d, 'email', 5, 254).lower()
        password = text(d, 'password', 12, 128)
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
            return fail('Enter a valid email address.')
        try:
            cur = db().execute('INSERT INTO users(name,email,password,created_at) VALUES(?,?,?,?)',
                               (name, email, generate_password_hash(password), now()))
            db().commit()
        except sqlite3.IntegrityError:
            return fail('That email is already registered.', 409)
        session.clear()
        session.update(uid=cur.lastrowid, csrf=secrets.token_hex(24))
        return jsonify(ok=True), 201

    # Local-process throttling; replace with shared rate limiting before public deployment.
    failures = {}

    @app.post('/api/login')
    def login():
        d = data()
        email = text(d, 'email', 5, 254).lower()
        key = (request.remote_addr, email)
        attempts = [t for t in failures.get(key, []) if time.monotonic()-t < 300]
        if len(attempts) >= 8:
            return fail('Too many attempts. Try again in five minutes.', 429)
        user = db().execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
        password = text(d, 'password', 1, 128)
        if not user or not check_password_hash(user['password'], password):
            failures[key] = attempts + [time.monotonic()]
            return fail('Email or password is incorrect.', 401)
        failures.pop(key, None)
        session.clear()
        session.update(uid=user['id'], csrf=secrets.token_hex(24))
        return jsonify(ok=True)

    @app.post('/api/logout')
    @auth
    def logout():
        session.clear()
        return jsonify(ok=True)

    @app.get('/api/centres')
    def centres():
        lat, lon = coords(request.args)
        items = [dict(r) for r in db().execute('SELECT * FROM centres')]
        for item in items:
            item['distance_km'] = distance(lat, lon, item['lat'], item['lon'])
        return jsonify(centres=sorted(items, key=lambda c: c['distance_km']),
                       notice='Sample locations only. No verified directory or live blood inventory is connected.')

    @app.post('/api/donor')
    @auth
    def donor():
        d = data()
        blood = group(d)
        lat, lon = coords(d)
        city = text(d, 'city', 2, 80)
        phone = text(d, 'phone', 10, 16)
        if not re.fullmatch(r'\+91[6-9][0-9]{9}', phone):
            return fail('Use an Indian mobile number in +91XXXXXXXXXX format.')
        age = int(d['age'])
        weight = float(d['weight'])
        if not 18 <= age <= 65 or not math.isfinite(weight) or not 45 <= weight <= 300:
            return fail('This prototype accepts volunteers aged 18–65 and weighing at least 45 kg. A clinician must assess eligibility.')
        last = d.get('last_donation') or None
        if last and date.fromisoformat(last) > date.today():
            return fail('Last donation cannot be in the future.')
        if d.get('privacy_consent') is not True:
            return fail('Consent to store your donor profile is required.')
        whatsapp = int(d.get('whatsapp_consent') is True)
        available = int(d.get('available') is True)
        db().execute('''INSERT INTO donors(user_id,blood_group,city,lat,lon,phone,whatsapp_consent,available,last_donation,age,weight)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET
                       blood_group=excluded.blood_group,city=excluded.city,lat=excluded.lat,lon=excluded.lon,
                       phone_verified=CASE WHEN donors.phone=excluded.phone THEN donors.phone_verified ELSE 0 END,
                       phone=excluded.phone,whatsapp_consent=excluded.whatsapp_consent,available=excluded.available,
                       last_donation=excluded.last_donation,age=excluded.age,weight=excluded.weight''',
                     (session['uid'],blood,city,lat,lon,phone,whatsapp,available,last,age,weight))
        db().commit()
        return jsonify(ok=True)

    def notify(uid, message):
        db().execute('INSERT INTO notifications(user_id,message,created_at) VALUES(?,?,?)', (uid,message,now()))

    @app.post('/api/requests')
    @auth
    def create_request():
        d = data()
        blood = group(d)
        lat, lon = coords(d)
        units = int(d['units'])
        if not 1 <= units <= 10:
            return fail('Request between 1 and 10 units.')
        hospital, city = text(d,'hospital',3,120), text(d,'city',2,80)
        with db():
            cur = db().execute('INSERT INTO requests(user_id,blood_group,units,hospital,city,lat,lon,created_at) VALUES(?,?,?,?,?,?,?,?)',
                               (session['uid'],blood,units,hospital,city,lat,lon,now()))
            rid = cur.lastrowid
            # Same-group volunteers only: this does not determine component compatibility.
            donors = db().execute('SELECT * FROM donors WHERE blood_group=? AND available=1 AND user_id<>?', (blood,session['uid'])).fetchall()
            candidates = []
            for donor in donors:
                if donor['last_donation'] and (date.today()-date.fromisoformat(donor['last_donation'])).days < MIN_DAYS:
                    continue
                km = distance(lat,lon,donor['lat'],donor['lon'])
                if km <= 50:
                    candidates.append((km,donor))
            for km, donor in sorted(candidates,key=lambda pair: pair[0])[:5]:
                match = db().execute('INSERT INTO matches(request_id,donor_id,distance,created_at) VALUES(?,?,?,?)', (rid,donor['user_id'],km,now()))
                notify(donor['user_id'],f'Request #{rid}: a {blood} volunteer is needed at {hospital}, {city}. Review your donor inbox.')
                state = 'dry-run' if donor['whatsapp_consent'] else 'skipped'
                detail = 'Simulated only; no WhatsApp message sent.' if donor['whatsapp_consent'] else 'No WhatsApp opt-in.'
                if os.getenv('WHATSAPP_MODE') == 'live' and donor['whatsapp_consent']:
                    state, detail = ('queued','Awaiting worker.') if donor['phone_verified'] else ('skipped','Phone ownership is not verified.')
                db().execute('INSERT INTO outbox(match_id,status,detail,updated_at) VALUES(?,?,?,?)',(match.lastrowid,state,detail,now()))
        return jsonify(id=rid,matched=min(len(candidates),5)),201

    @app.get('/api/dashboard')
    @auth
    def dashboard():
        uid = session['uid']
        own = [dict(r) for r in db().execute('SELECT * FROM requests WHERE user_id=? ORDER BY id DESC',(uid,))]
        for item in own:
            # Do not expose donor phone numbers or exact home coordinates.
            item.pop('lat'); item.pop('lon')
            item['matches'] = [dict(m) for m in db().execute('''SELECT m.id,m.status,m.distance,u.name
                FROM matches m JOIN users u ON m.donor_id=u.id WHERE m.request_id=? ORDER BY m.distance''',(item['id'],))]
        inbox = [dict(r) for r in db().execute('''SELECT m.id,m.status,m.distance,r.id request_id,r.blood_group,r.units,r.hospital,r.city,r.status request_status,
              o.status whatsapp_status FROM matches m JOIN requests r ON r.id=m.request_id
              LEFT JOIN outbox o ON o.match_id=m.id WHERE m.donor_id=? ORDER BY m.id DESC''',(uid,))]
        notes = [dict(r) for r in db().execute('SELECT id,message,created_at,read FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 30',(uid,))]
        return jsonify(requests=own,inbox=inbox,notifications=notes)

    @app.post('/api/notifications/read')
    @auth
    def read_notifications():
        db().execute('UPDATE notifications SET read=1 WHERE user_id=?',(session['uid'],))
        db().commit()
        return jsonify(ok=True)

    @app.post('/api/matches/<int:mid>/respond')
    @auth
    def respond(mid):
        d = data()
        # Acquire a write lock before checking status, so concurrent responses cannot overwrite one another.
        with db():
            db().execute('BEGIN IMMEDIATE')
            match = db().execute('SELECT m.*,r.status request_status,r.user_id owner FROM matches m JOIN requests r ON r.id=m.request_id WHERE m.id=? AND m.donor_id=?', (mid,session['uid'])).fetchone()
            if not match:
                return fail('Match not found.',404)
            if match['status'] != 'pending' or match['request_status'] != 'open':
                return fail('This request is no longer awaiting your response.',409)
            action = d.get('action')
            if action == 'decline':
                state = 'declined'
            elif action == 'accept':
                donor = db().execute('SELECT * FROM donors WHERE user_id=?',(session['uid'],)).fetchone()
                last = d.get('last_donation') or None
                if d.get('never_donated') is not True and not last:
                    return fail('Provide your last donation date or confirm you have never donated.')
                if last and d.get('never_donated') is True:
                    return fail('Choose either a donation date or never donated.')
                if last:
                    days = (date.today()-date.fromisoformat(last)).days
                    if days < MIN_DAYS:
                        return fail(f'This prototype requires at least {MIN_DAYS} days since donation. Ask a licensed blood centre about eligibility.')
                if donor['last_donation'] and (date.today()-date.fromisoformat(donor['last_donation'])).days < MIN_DAYS:
                    return fail('Your saved donation date is too recent. Contact the blood centre before volunteering.')
                if not donor['available']:
                    return fail('Your donor profile is unavailable. Update it before accepting.')
                if d.get('well_today') is not True or d.get('clinical_consent') is not True:
                    return fail('Confirm that you feel well and agree to clinical screening at a licensed blood centre.')
                state = 'accepted'
                db().execute('UPDATE donors SET last_donation=? WHERE user_id=?',(last,session['uid']))
            else:
                return fail('Choose accept or decline.')
            db().execute('UPDATE matches SET status=? WHERE id=?',(state,mid))
            notify(match['owner'],f'A volunteer {state} request #{match["request_id"]}. Acceptance is provisional; arrange screening through the named hospital/blood centre.')
            # Cancel queued external notifications after a response.
            db().execute("UPDATE outbox SET status='cancelled',detail='Donor has responded.',updated_at=? WHERE match_id=? AND status='queued'",(now(),mid))
        return jsonify(ok=True,status=state)

    @app.post('/api/requests/<int:rid>/close')
    @auth
    def close_request(rid):
        with db():
            cur=db().execute("UPDATE requests SET status='closed' WHERE id=? AND user_id=? AND status='open'",(rid,session['uid']))
            if not cur.rowcount:
                return fail('Open request not found.',404)
            db().execute("UPDATE outbox SET status='cancelled',detail='Request closed.',updated_at=? WHERE status='queued' AND match_id IN (SELECT id FROM matches WHERE request_id=?)",(now(),rid))
        return jsonify(ok=True)

    @app.cli.command('send-whatsapp')
    def send_whatsapp():
        """Send queued opt-in notifications once. Ambiguous failures require manual reconciliation."""
        if os.getenv('WHATSAPP_MODE') != 'live':
            click.echo('Dry-run mode: no messages sent. In-app notifications are available.')
            return
        token = os.getenv('WHATSAPP_TOKEN')
        phone_id = os.getenv('WHATSAPP_PHONE_NUMBER_ID','')
        version = os.getenv('WHATSAPP_API_VERSION','v23.0')
        template = os.getenv('WHATSAPP_TEMPLATE','')
        if not token or not phone_id.isdigit() or not re.fullmatch(r'v\d+\.\d+',version) or not re.fullmatch(r'[a-z0-9_]+',template):
            raise click.ClickException('Configure the Meta token, numeric sender ID, API version and approved template name.')
        rows=db().execute("""SELECT o.id,d.phone,m.request_id FROM outbox o
            JOIN matches m ON m.id=o.match_id JOIN donors d ON d.user_id=m.donor_id JOIN requests r ON r.id=m.request_id
            WHERE o.status='queued' AND d.whatsapp_consent=1 AND d.phone_verified=1 AND d.available=1
            AND m.status='pending' AND r.status='open'""").fetchall()
        for row in rows:
            # Claim before network call: never silently retry uncertain deliveries.
            cur=db().execute("UPDATE outbox SET status='sending',updated_at=? WHERE id=? AND status='queued'",(now(),row['id']))
            db().commit()
            if not cur.rowcount:
                continue
            body={'messaging_product':'whatsapp','to':row['phone'].lstrip('+'),'type':'template',
                  'template':{'name':template,'language':{'code':os.getenv('WHATSAPP_TEMPLATE_LANGUAGE','en')},
                              'components':[{'type':'body','parameters':[{'type':'text','text':str(row['request_id'])}]}]}}
            req=urllib.request.Request(f'https://graph.facebook.com/{version}/{phone_id}/messages',data=json.dumps(body).encode(),
                headers={'Authorization':f'Bearer {token}','Content-Type':'application/json'},method='POST')
            try:
                with urllib.request.urlopen(req,timeout=15) as response:
                    result=json.load(response)
                state,detail='submitted', 'Meta accepted the API request; delivery is not confirmed.'
                if not result.get('messages'):
                    state,detail='unknown','Unexpected API response; reconcile before retrying.'
            except Exception:
                # Provider bodies can include sensitive data. Do not log them or the recipient.
                state,detail='unknown','API request failed or timed out; reconcile in Meta before retrying.'
            db().execute('UPDATE outbox SET status=?,detail=?,updated_at=? WHERE id=?',(state,detail,now(),row['id']))
            db().commit()
            click.echo(f'Outbox {row["id"]}: {state}')

    return app


app = create_app()
if __name__ == '__main__':
    app.run(host='0.0.0.0',port=int(os.getenv('PORT','5000')),debug=False)
