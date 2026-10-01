from flask import Flask, request, jsonify
from werkzeug.middleware.proxy_fix import ProxyFix
import urllib.request
import json
import os
import sys
import time
import sqlite3
import re
import html
import secrets
import datetime
import smtplib
import csv
import io
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from functools import wraps
from contextlib import contextmanager

app = Flask(__name__, static_folder='.', static_url_path='')

# 🛡️ 1. Werkzeug ProxyFix: Trust exactly 1 reverse proxy hop (Render / Cloudflare)
# Replaces request.remote_addr with the true client IP appended by the proxy,
# completely ignoring any spoofed X-Forwarded-For headers injected by the attacker.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

# 🛡️ 2. Hard Request Body Limit (2MB) - Prevents memory exhaustion DoS
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024

# 🛡️ 3. Safe Environment Loading
def load_env():
    env_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), ".env")
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ[k.strip()] = v.strip()
        except Exception as e:
            print("Failed to read .env file:", str(e), file=sys.stderr)

load_env()

ADMIN_DEFAULT_USER = os.environ.get("ADMIN_USER", "admin").strip()
ADMIN_DEFAULT_PASS = os.environ.get("ADMIN_PASS")

# If running on Render or with production database, ADMIN_PASS MUST be explicitly configured
if not ADMIN_DEFAULT_PASS:
    if os.environ.get("RENDER") or os.environ.get("DATABASE_URL"):
        print("❌ CRITICAL CONFIGURATION ERROR: ADMIN_PASS environment variable must be set in production!", file=sys.stderr)
        sys.exit(1)
    else:
        # Local development fallback
        ADMIN_DEFAULT_PASS = "aabbddaA1"
else:
    ADMIN_DEFAULT_PASS = ADMIN_DEFAULT_PASS.strip()

ADMIN_NOTIFICATION_EMAIL = os.environ.get("ADMIN_NOTIFICATION_EMAIL", "aboody.alfaloje20@gmail.com").strip()

# 🛡️ 4. Robust & Bounded Rate Limiting
RATE_LIMIT_LIMIT = 20
RATE_LIMIT_WINDOW = 60  # seconds
ip_requests = {}  # key: [timestamps]
MAX_RATE_LIMITER_KEYS = 5000

def get_client_ip():
    """
    Returns the real client IP validated by Werkzeug ProxyFix.
    Cannot be spoofed by custom client headers.
    """
    return request.remote_addr or "127.0.0.1"

def is_rate_limited(key, limit=RATE_LIMIT_LIMIT, window=RATE_LIMIT_WINDOW):
    now = time.time()
    
    # Strictly enforce memory limit: if dict has 5000+ keys, prune
    if len(ip_requests) >= MAX_RATE_LIMITER_KEYS:
        # 1. Prune expired
        expired = [k for k, ts in ip_requests.items() if not ts or now - ts[-1] > window]
        for k in expired:
            ip_requests.pop(k, None)
            
        # 2. If still at or above capacity, drop oldest 1000 keys unconditionally (FIFO eviction)
        if len(ip_requests) >= MAX_RATE_LIMITER_KEYS:
            keys_to_drop = list(ip_requests.keys())[:1000]
            for k in keys_to_drop:
                ip_requests.pop(k, None)

    if key not in ip_requests:
        ip_requests[key] = []
    ip_requests[key] = [t for t in ip_requests[key] if now - t < window]
    
    if len(ip_requests[key]) >= limit:
        return True
    
    ip_requests[key].append(now)
    return False

# 🛡️ 5. Non-ASCII Safe Constant-Time Comparison
def safe_compare(val1, val2):
    """
    Constant-time comparison protected against non-ASCII UnicodeEncodeError / exceptions.
    Prevents timing attacks while gracefully returning False for non-matching or invalid inputs.
    """
    try:
        if not isinstance(val1, str) or not isinstance(val2, str):
            return False
        return secrets.compare_digest(val1.encode('utf-8'), val2.encode('utf-8'))
    except Exception:
        return False

# 🛡️ 6. Leak-Proof Database Architecture (Connection Pooling + Context Manager)
_pg_pool = None

def get_pg_pool():
    global _pg_pool
    db_url = os.environ.get("DATABASE_URL", "").strip()
    if db_url and _pg_pool is None:
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        try:
            import psycopg2.pool
            import psycopg2.extras
            _pg_pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=20,
                dsn=db_url,
                connect_timeout=8,
                keepalives=1,
                keepalives_idle=30,
                keepalives_interval=10,
                keepalives_count=5
            )
            print("PostgreSQL Threaded Connection Pool initialized successfully.")
        except Exception as e:
            print("Failed to initialize PostgreSQL pool:", str(e), file=sys.stderr)
    return _pg_pool

def is_postgres():
    return bool(os.environ.get("DATABASE_URL", "").strip())

class PooledConnectionWrapper:
    def __init__(self, conn, pool):
        self._conn = conn
        self._pool = pool
        self._closed = False

    def close(self):
        if not self._closed:
            self._closed = True
            try:
                self._pool.putconn(self._conn)
            except Exception:
                pass

    def __getattr__(self, name):
        return getattr(self._conn, name)

def get_db():
    pool = get_pg_pool()
    if pool:
        try:
            import psycopg2.extras
            raw_conn = pool.getconn()
            wrapper = PooledConnectionWrapper(raw_conn, pool)
            return wrapper, psycopg2.extras.RealDictCursor
        except Exception as e:
            print("Error acquiring connection from pool:", str(e), file=sys.stderr)

    db_url = os.environ.get("DATABASE_URL", "").strip()
    if db_url:
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        try:
            import psycopg2
            import psycopg2.extras
            conn = psycopg2.connect(db_url)
            return conn, psycopg2.extras.RealDictCursor
        except Exception as e:
            print("PostgreSQL direct connection failed:", str(e), file=sys.stderr)
            
    db_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "leads.db")
    conn = sqlite3.connect(db_path, timeout=15)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
    except Exception:
        pass
    conn.row_factory = sqlite3.Row
    return conn, None

def get_cursor(conn, cf=None):
    if cf:
        return conn.cursor(cursor_factory=cf)
    return conn.cursor()

def adapt_query(query):
    if is_postgres():
        return query.replace("?", "%s")
    return query

@contextmanager
def db_session(readonly=False):
    """
    100% leak-proof database context manager.
    Guarantees conn.close() executes in a finally block on ALL paths (errors, returns, exceptions).
    """
    conn, cf = get_db()
    cursor = get_cursor(conn, cf)
    try:
        yield conn, cursor
        if not readonly:
            conn.commit()
    except Exception:
        if not readonly:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass

def init_db():
    try:
        with db_session() as (conn, cursor):
            id_col = "SERIAL PRIMARY KEY" if is_postgres() else "INTEGER PRIMARY KEY AUTOINCREMENT"
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS leads (
                    id {id_col},
                    name TEXT,
                    phone TEXT,
                    email TEXT,
                    business_name TEXT,
                    business_type TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS visitor_sessions (
                    id {id_col},
                    session_id TEXT UNIQUE,
                    ip TEXT,
                    user_agent TEXT,
                    device_type TEXT,
                    browser TEXT,
                    os TEXT,
                    referrer TEXT,
                    duration_seconds INTEGER DEFAULT 0,
                    scroll_depth INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS admin_tokens (
                    token TEXT PRIMARY KEY,
                    username TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP
                )
            """)
        db_type = "PostgreSQL Cloud Database" if is_postgres() else "SQLite (leads.db)"
        print(f"Database tables initialized successfully ({db_type}).")
        cleanup_old_records()
    except Exception as e:
        print("Failed to initialize database:", str(e), file=sys.stderr)

def cleanup_old_records():
    """Periodically cleans up expired tokens and sessions older than 30 days to prevent bloat"""
    try:
        with db_session() as (conn, cursor):
            cursor.execute(adapt_query("DELETE FROM admin_tokens WHERE expires_at < CURRENT_TIMESTAMP"))
            if is_postgres():
                cursor.execute("DELETE FROM visitor_sessions WHERE created_at < NOW() - INTERVAL '30 days'")
            else:
                cursor.execute("DELETE FROM visitor_sessions WHERE created_at < datetime('now', '-30 days')")
    except Exception as e:
        print("DB cleanup exception (ignored):", str(e), file=sys.stderr)

init_db()
API_KEY = os.environ.get("GEMINI_API_KEY")

@app.route('/')
def index():
    return app.send_static_file('index.html')

# 🛡️ 7. Google Vertex AI / Service Account Setup
SA_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)), "service_account.json")
creds = None
sa_data = None

if os.path.exists(SA_PATH):
    try:
        with open(SA_PATH, "r", encoding="utf-8") as f:
            sa_data = json.load(f)
    except Exception as e:
        print("Failed to read service_account.json:", str(e), file=sys.stderr)
elif os.environ.get("GCP_SERVICE_ACCOUNT"):
    try:
        sa_data = json.loads(os.environ.get("GCP_SERVICE_ACCOUNT"))
    except Exception as e:
        print("Failed to parse GCP_SERVICE_ACCOUNT env var:", str(e), file=sys.stderr)

if sa_data:
    try:
        from google.oauth2 import service_account
        import google.auth.transport.requests
        import requests
        SCOPES = ['https://www.googleapis.com/auth/cloud-platform']
        creds = service_account.Credentials.from_service_account_info(sa_data, scopes=SCOPES)
        print("Service account loaded successfully.")
    except Exception as e:
        print("Failed to initialize service account:", str(e), file=sys.stderr)

def get_sa_token():
    global creds
    if creds:
        try:
            import google.auth.transport.requests
            auth_req = google.auth.transport.requests.Request()
            if not creds.valid:
                creds.refresh(auth_req)
            return creds.token
        except Exception as e:
            print("Failed to refresh token:", str(e), file=sys.stderr)
    return None

# 🛡️ 8. Hardened AI Chat Endpoint
@app.route('/api/chat', methods=['POST'])
def chat():
    client_ip = get_client_ip()
    if is_rate_limited(f"{client_ip}:chat", limit=12, window=60):
        return jsonify({
            "error": "لقد تجاوزت حد الطلبات المسموح به للدردشة. يرجى الانتظار دقيقة قبل المحاولة مجدداً."
        }), 429

    if not request.is_json:
        return jsonify({"error": "Invalid Content-Type"}), 400

    client_payload = request.get_json(silent=True) or {}
    
    # Validate & Sanitize contents (prevent prompt inflation / DoS)
    raw_contents = client_payload.get("contents", [])
    if not isinstance(raw_contents, list):
        return jsonify({"error": "Invalid contents format"}), 400
    if len(raw_contents) > 25:
        raw_contents = raw_contents[-25:]  # Bound history length
        
    sanitized_contents = []
    for item in raw_contents:
        if not isinstance(item, dict):
            continue
        role = item.get("role", "user")
        if role not in ("user", "model"):
            role = "user"
        parts = item.get("parts", [])
        if not isinstance(parts, list):
            continue
        clean_parts = []
        for p in parts:
            if isinstance(p, dict) and "text" in p:
                clean_parts.append({"text": str(p["text"])[:3000]})
        if clean_parts:
            sanitized_contents.append({"role": role, "parts": clean_parts})
            
    if not sanitized_contents:
        return jsonify({"error": "No valid messages provided"}), 400

    # Force Clamp Tokens to prevent resource draining
    raw_max_tokens = client_payload.get("generationConfig", {}).get("maxOutputTokens", 800)
    try:
        clamped_tokens = min(max(int(raw_max_tokens), 50), 1000)
    except (ValueError, TypeError):
        clamped_tokens = 800

    gen_config = {
        "thinkingConfig": {"thinkingBudget": 0},
        "temperature": 0.7,
        "maxOutputTokens": clamped_tokens
    }

    raw_sys = client_payload.get("systemInstruction", {})
    sanitized_sys = {}
    if isinstance(raw_sys, dict) and "parts" in raw_sys and isinstance(raw_sys["parts"], list):
        sys_parts = []
        for p in raw_sys["parts"]:
            if isinstance(p, dict) and "text" in p:
                sys_parts.append({"text": str(p["text"])[:3500]})
        if sys_parts:
            sanitized_sys = {"parts": sys_parts}

    req_payload = {
        "contents": sanitized_contents,
        "systemInstruction": sanitized_sys,
        "generationConfig": gen_config
    }

    # 1. Try Vertex AI first (Service Account)
    token = get_sa_token()
    if token and sa_data:
        import requests
        project = sa_data.get("project_id", "gen-lang-client-0148309017")
        vertex_models = [
            ("gemini-3.8-flash", "global"),
            ("gemini-3.1-flash-lite", "global"),
            ("gemini-2.5-flash", "global"),
        ]
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        for model, location in vertex_models:
            try:
                if location == "global":
                    url = f"https://aiplatform.googleapis.com/v1/projects/{project}/locations/global/publishers/google/models/{model}:generateContent"
                else:
                    url = f"https://{location}-aiplatform.googleapis.com/v1/projects/{project}/locations/{location}/publishers/google/models/{model}:generateContent"
                    
                t_out = 6 if "3.8" in model else 12
                r = requests.post(url, headers=headers, json=req_payload, timeout=t_out)
                if r.status_code == 200:
                    res_json = r.json()
                    res_json["_model_used"] = f"Vertex AI: {model}"
                    return jsonify(res_json)
                else:
                    print(f"Vertex AI model {model} failed with status {r.status_code}: {r.text[:200]}", file=sys.stderr)
            except Exception as e:
                print(f"Vertex AI request exception for {model}: {str(e)}", file=sys.stderr)

    # 2. Fallback to Gemini API Key
    if API_KEY:
        models = [
            "gemini-3.8-flash",
            "gemini-3.1-flash-lite",
            "gemini-2.5-flash"
        ]
        
        for model in models:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={API_KEY}"
                req_data = json.dumps(req_payload).encode('utf-8')
                req = urllib.request.Request(
                    url, 
                    data=req_data, 
                    headers={"Content-Type": "application/json"}, 
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=12) as response:
                    res_body = response.read().decode('utf-8')
                    result = json.loads(res_body)
                    result["_model_used"] = f"Gemini API: {model}"
                    return jsonify(result)
            except Exception as e:
                print(f"Gemini API model {model} failed: {str(e)}", file=sys.stderr)
                continue
                
    return jsonify({"error": "حدث خطأ في معالجة الرد، يرجى المحاولة لاحقاً."}), 500

# 🛡️ 9. Sanitized Email & Webhook Notifications
def safe_print(*args, **kwargs):
    try:
        print(*args, **kwargs)
    except Exception:
        try:
            msg = " ".join(str(a) for a in args)
            print(msg.encode("ascii", errors="replace").decode("ascii"), **kwargs)
        except Exception:
            pass

def send_lead_email(lead_data):
    smtp_user = os.environ.get("SMTP_USER", "").strip()
    smtp_pass = os.environ.get("SMTP_PASS", "").strip()
    
    # Raw values stripped of newlines for email Subject (prevents CRLF header injection)
    raw_name = str(lead_data.get("name", "غير محدد"))[:100].replace("\r", "").replace("\n", "").strip()
    raw_phone = str(lead_data.get("phone", "غير محدد"))[:40].replace("\r", "").replace("\n", "").strip()
    
    # HTML-escaped values for the email body
    name = html.escape(raw_name)
    phone = html.escape(raw_phone)
    biz_name = html.escape(str(lead_data.get("business_name", "غير محدد"))[:100])
    biz_type = html.escape(str(lead_data.get("business_type", "استشارة عامة"))[:100])
    email = html.escape(str(lead_data.get("email", "غير محدد"))[:100])
    
    # Filter phone to digits only for WhatsApp link
    clean_phone = re.sub(r'[^0-9]', '', raw_phone)
    if clean_phone.startswith("07"):
        clean_phone = "964" + clean_phone[1:]
    
    html_body = f"""
    <!DOCTYPE html>
    <html dir="rtl" lang="ar">
    <head><meta charset="utf-8"></head>
    <body style="font-family: Arial, sans-serif; background-color: #F6F2E9; padding: 20px; color: #22392B;">
      <div style="max-width: 560px; margin: auto; background: #ffffff; border: 1px solid #C4A35A; border-radius: 16px; padding: 25px; box-shadow: 0 4px 15px rgba(0,0,0,0.05);">
        <h2 style="color: #22392B; margin-top: 0; border-bottom: 2px solid #C4A35A; padding-bottom: 12px;">🎉 طلب تسعيرة واستشارة جديدة على منصة «جاوبني»</h2>
        <p style="font-size: 15px; color: #445138;">وصلك طلب استشارة وتسعيرة مخصصة من الموقع الرسمي:</p>
        
        <table style="width: 100%; border-collapse: collapse; margin: 20px 0; font-size: 14px;">
          <tr style="background-color: #F6F2E9;">
            <td style="padding: 10px; font-weight: bold; border: 1px solid #E2D9C6; width: 35%;">الاسم الثلاثي:</td>
            <td style="padding: 10px; border: 1px solid #E2D9C6; font-weight: bold; color: #22392B;">{name}</td>
          </tr>
          <tr>
            <td style="padding: 10px; font-weight: bold; border: 1px solid #E2D9C6;">رقم الهاتف:</td>
            <td style="padding: 10px; border: 1px solid #E2D9C6;">
              <a href="tel:{clean_phone}" style="color: #22392B; font-weight: bold; text-decoration: none;">{phone}</a>
              &nbsp;|&nbsp;
              <a href="https://wa.me/{clean_phone}" style="color: #25D366; font-weight: bold; text-decoration: none;">💬 فتح بالواتساب</a>
            </td>
          </tr>
          <tr style="background-color: #F6F2E9;">
            <td style="padding: 10px; font-weight: bold; border: 1px solid #E2D9C6;">اسم المشروع / النشاط:</td>
            <td style="padding: 10px; border: 1px solid #E2D9C6; font-weight: bold; color: #22392B;">{biz_name}</td>
          </tr>
          <tr>
            <td style="padding: 10px; font-weight: bold; border: 1px solid #E2D9C6;">نوع الطلب / الاستشارة:</td>
            <td style="padding: 10px; border: 1px solid #E2D9C6;">{biz_type}</td>
          </tr>
          <tr style="background-color: #F6F2E9;">
            <td style="padding: 10px; font-weight: bold; border: 1px solid #E2D9C6;">البريد الإلكتروني:</td>
            <td style="padding: 10px; border: 1px solid #E2D9C6;">{email}</td>
          </tr>
        </table>
        
        <div style="background-color: #22392B; color: #F6F2E9; padding: 12px 18px; border-radius: 10px; text-align: center; margin-top: 20px;">
          <a href="https://wa.me/{clean_phone}" style="color: #C4A35A; text-decoration: none; font-weight: bold; font-size: 15px;">مراسلة الزبون على الواتساب فوراً 🚀</a>
        </div>
      </div>
    </body>
    </html>
    """
    
    # 1. Primary: Google Apps Script Webhook
    webhook_url = os.environ.get(
        "GOOGLE_WEBHOOK_URL",
        "https://script.google.com/macros/s/AKfycbyySbR7dOIUfLlF_xoIaxiAUCZvzUAarzA9FBDV2oS04Jb7S4f6g1un_OMeEtIYYskC/exec"
    )
    try:
        import requests
        res = requests.post(webhook_url, json=lead_data, timeout=10)
        if res.status_code == 200:
            safe_print(f"Lead email successfully dispatched via Webhook to {ADMIN_NOTIFICATION_EMAIL}")
            return
    except Exception as e:
        safe_print(f"Google Webhook attempt failed: {str(e)}, trying direct SMTP fallback...", file=sys.stderr)

    # 2. Secondary: SMTP Fallback
    if smtp_user and smtp_pass:
        msg = MIMEMultipart("alternative")
        # Raw name and phone in Subject (never HTML-escaped entities like &amp;)
        msg["Subject"] = f"🔥 طلب تسعيرة واستشارة جديدة: {raw_name} - {raw_phone}"
        msg["From"] = f"جاوبني <{smtp_user}>"
        msg["To"] = ADMIN_NOTIFICATION_EMAIL
        msg.attach(MIMEText(html_body, "html", "utf-8"))
        
        sent = False
        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as server:
                server.login(smtp_user, smtp_pass)
                server.sendmail(smtp_user, ADMIN_NOTIFICATION_EMAIL, msg.as_string())
            safe_print(f"Email notification successfully sent via SSL (465) to {ADMIN_NOTIFICATION_EMAIL}")
            sent = True
        except Exception as e:
            safe_print(f"SSL (465) attempt failed: {str(e)}, trying TLS (587)...", file=sys.stderr)
            
        if not sent:
            try:
                server = smtplib.SMTP("smtp.gmail.com", 587, timeout=10)
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.sendmail(smtp_user, ADMIN_NOTIFICATION_EMAIL, msg.as_string())
                server.quit()
                safe_print(f"Email notification successfully sent via TLS (587) to {ADMIN_NOTIFICATION_EMAIL}")
                sent = True
            except Exception as e:
                safe_print(f"Failed to send email notification on both 465 and 587: {str(e)}", file=sys.stderr)

# 🛡️ 10. Hardened Leads Creation API
@app.route('/api/leads', methods=['POST'])
def save_lead():
    client_ip = get_client_ip()
    if is_rate_limited(f"{client_ip}:lead", limit=5, window=60):
        return jsonify({"error": "تم تسجيل عدة محاولات في وقت قصير، يرجى الانتظار دقيقة قبل إعادة المحاولة."}), 429

    if not request.is_json:
        return jsonify({"error": "Invalid Content-Type"}), 400

    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()[:100]
    phone = str(data.get("phone", "")).strip()[:40]
    email = str(data.get("email", "")).strip()[:100]
    business_name = str(data.get("business_name", "")).strip()[:100]
    business_type = str(data.get("business_type", "")).strip()[:100]
    
    if not name or (not phone and not email):
        return jsonify({"error": "الرجاء إدخال الاسم الثلاثي ورقم الهاتف للتواصل."}), 400
        
    digits = re.sub(r'[^0-9]', '', phone)
    if phone and len(digits) < 8:
        return jsonify({"error": "يرجى إدخال رقم هاتف صحيح."}), 400
        
    try:
        with db_session() as (conn, cursor):
            cursor.execute(adapt_query("""
                INSERT INTO leads (name, phone, email, business_name, business_type)
                VALUES (?, ?, ?, ?, ?)
            """), (name, phone, email, business_name, business_type))
            
        print("Lead saved successfully.")
        send_lead_email({
            "name": name,
            "phone": phone,
            "email": email,
            "business_name": business_name,
            "business_type": business_type
        })
        return jsonify({"success": True, "message": "تم استلام وتثبيت حجزك بنجاح! سنتواصل معك قريباً."})
    except Exception as e:
        print("Failed to save lead to database:", str(e), file=sys.stderr)
        return jsonify({"error": "حدث خطأ أثناء حفظ البيانات."}), 500

# 🛡️ 11. Hardened Analytics & Visitor Tracking
def parse_user_agent(ua_string, screen_width=None):
    ua = (ua_string or "").lower()
    
    device = "حاسوب (Desktop)"
    if "mobi" in ua or "iphone" in ua or "android" in ua and "tablet" not in ua:
        device = "موبايل (Mobile)"
    elif "ipad" in ua or "tablet" in ua or (screen_width and 768 <= screen_width <= 1024):
        device = "لوحي (Tablet)"
    elif screen_width and screen_width < 768:
        device = "موبايل (Mobile)"
        
    os_name = "أخرى"
    if "iphone" in ua or "ipad" in ua or "ios" in ua:
        os_name = "iOS"
    elif "android" in ua:
        os_name = "Android"
    elif "windows" in ua:
        os_name = "Windows"
    elif "mac" in ua:
        os_name = "macOS"
    elif "linux" in ua:
        os_name = "Linux"
        
    browser = "أخرى"
    if "edg" in ua:
        browser = "Edge"
    elif "chrome" in ua and "edg" not in ua and "opr" not in ua:
        browser = "Chrome"
    elif "safari" in ua and "chrome" not in ua:
        browser = "Safari"
    elif "firefox" in ua:
        browser = "Firefox"
    elif "opr" in ua or "opera" in ua:
        browser = "Opera"
        
    return device, os_name, browser

@app.route('/api/track/visit', methods=['POST'])
def track_visit():
    client_ip = get_client_ip()
    if is_rate_limited(f"{client_ip}:track", limit=40, window=60):
        return jsonify({"error": "Rate limit exceeded"}), 429
        
    data = request.get_json(silent=True) or {}
    raw_session = str(data.get("session_id", "")).strip()
    if re.match(r'^[a-zA-Z0-9_-]{10,64}$', raw_session):
        session_id = raw_session
    else:
        session_id = secrets.token_hex(16)
        
    referrer = str(data.get("referrer", "")).strip()[:250]
    screen_width = data.get("screen_width")
    try:
        screen_width = int(screen_width) if screen_width else None
    except (ValueError, TypeError):
        screen_width = None
        
    raw_ua = request.headers.get("User-Agent", "")[:250]
    device, os_name, browser = parse_user_agent(raw_ua, screen_width)
    
    try:
        with db_session() as (conn, cursor):
            cursor.execute(adapt_query("""
                INSERT INTO visitor_sessions (session_id, ip, user_agent, device_type, browser, os, referrer, duration_seconds, scroll_depth, created_at, last_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT(session_id) DO UPDATE SET
                    last_active = CURRENT_TIMESTAMP
            """), (session_id, client_ip, raw_ua, device[:40], browser[:40], os_name[:40], referrer))
            
        return jsonify({"success": True, "session_id": session_id})
    except Exception as e:
        print("Track visit error:", str(e), file=sys.stderr)
        return jsonify({"error": "Failed to track visit"}), 500

@app.route('/api/track/ping', methods=['POST'])
def track_ping():
    client_ip = get_client_ip()
    if is_rate_limited(f"{client_ip}:ping", limit=60, window=60):
        return jsonify({"error": "Rate limit exceeded"}), 429
        
    data = request.get_json(silent=True) or {}
    session_id = str(data.get("session_id", "")).strip()
    if not re.match(r'^[a-zA-Z0-9_-]{10,64}$', session_id):
        return jsonify({"error": "Invalid session_id"}), 400
        
    try:
        duration = max(0, min(86400, int(data.get("duration_seconds", 0))))
        scroll_depth = max(0, min(100, int(data.get("scroll_depth", 0))))
    except (ValueError, TypeError):
        duration = 0
        scroll_depth = 0
    
    try:
        with db_session() as (conn, cursor):
            cursor.execute(adapt_query("""
                UPDATE visitor_sessions
                SET duration_seconds = CASE WHEN ? > duration_seconds THEN ? ELSE duration_seconds END,
                    scroll_depth = CASE WHEN ? > scroll_depth THEN ? ELSE scroll_depth END,
                    last_active = CURRENT_TIMESTAMP
                WHERE session_id = ?
            """), (duration, duration, scroll_depth, scroll_depth, session_id))
            
        return jsonify({"success": True})
    except Exception as e:
        print("Track ping error:", str(e), file=sys.stderr)
        return jsonify({"error": "Failed to update ping"}), 500

# 🛡️ 12. Hardened Admin Authentication
def get_admin_creds():
    admin_user = os.environ.get("ADMIN_USER", ADMIN_DEFAULT_USER).strip()
    admin_pass = os.environ.get("ADMIN_PASS", ADMIN_DEFAULT_PASS).strip()
    return admin_user, admin_pass

def verify_token(token):
    if not token or not isinstance(token, str) or len(token) > 128:
        return None
    try:
        with db_session(readonly=True) as (conn, cursor):
            cursor.execute(adapt_query("""
                SELECT username, expires_at FROM admin_tokens
                WHERE token = ? AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
            """), (token,))
            row = cursor.fetchone()
            if row:
                return row["username"]
    except Exception as e:
        print("Verify token error:", str(e), file=sys.stderr)
    return None

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        token = None
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1].strip()
        
        if not token:
            token = request.cookies.get("jawebni_admin_token")
            
        username = verify_token(token)
        if not username:
            return jsonify({"error": "غير مصرح لك بالوصول. يرجى تسجيل الدخول أولاً."}), 401
            
        return f(*args, **kwargs)
    return decorated_function

@app.route('/pathogenesis')
@app.route('/pathogenesis.html')
def admin_page():
    return app.send_static_file('admin.html')

@app.route('/admin')
@app.route('/admin.html')
def admin_blocked():
    return jsonify({"error": "Page not found"}), 404

@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    client_ip = get_client_ip()
    # Strict Brute-Force Defense: max 5 login attempts per 5 minutes per IP
    if is_rate_limited(f"{client_ip}:admin_login", limit=5, window=300):
        return jsonify({"error": "محاولات تسجيل دخول متكررة، يرجى الانتظار 5 دقائق قبل المحاولة مجدداً."}), 429

    if not request.is_json:
        return jsonify({"error": "Invalid Content-Type"}), 400

    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", "")).strip()
    
    admin_user, admin_pass = get_admin_creds()
    
    # Safe constant-time comparison protected against non-ASCII UnicodeEncodeError / exceptions
    if safe_compare(username, admin_user) and safe_compare(password, admin_pass):
        token = secrets.token_hex(32)
        expires_at = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
        
        try:
            with db_session() as (conn, cursor):
                cursor.execute(adapt_query("""
                    INSERT INTO admin_tokens (token, username, created_at, expires_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP, ?)
                """), (token, username, expires_at))
            
            res = jsonify({
                "success": True,
                "message": "تم تسجيل الدخول بنجاح",
                "token": token,
                "username": username
            })
            is_https = request.is_secure or request.headers.get("X-Forwarded-Proto") == "https" or bool(os.environ.get("RENDER"))
            res.set_cookie(
                "jawebni_admin_token",
                token,
                max_age=7*24*60*60,
                httponly=True,
                secure=is_https,
                samesite="Lax"
            )
            return res
        except Exception as e:
            print("Login DB error:", str(e), file=sys.stderr)
            return jsonify({"error": "حدث خطأ في السيرفر أثناء تسجيل الدخول."}), 500
    else:
        return jsonify({"error": "اسم المستخدم أو كلمة المرور غير صحيحة!"}), 401

@app.route('/api/admin/logout', methods=['POST'])
def admin_logout():
    token = request.cookies.get("jawebni_admin_token")
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1].strip()
        
    if token:
        try:
            with db_session() as (conn, cursor):
                cursor.execute(adapt_query("DELETE FROM admin_tokens WHERE token = ?"), (token,))
        except Exception as e:
            print("Logout DB error:", str(e), file=sys.stderr)
            
    res = jsonify({"success": True, "message": "تم تسجيل الخروج بنجاح."})
    res.delete_cookie("jawebni_admin_token")
    return res

@app.route('/api/admin/check-auth', methods=['GET'])
def check_auth():
    token = request.cookies.get("jawebni_admin_token")
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1].strip()
        
    username = verify_token(token)
    if username:
        return jsonify({"authenticated": True, "username": username})
    return jsonify({"authenticated": False}), 401

# 🛡️ 13. Leak-Free Protected Admin APIs
@app.route('/api/admin/stats', methods=['GET'])
@admin_required
def admin_stats():
    try:
        with db_session(readonly=True) as (conn, cursor):
            active_cond = "last_active >= NOW() - INTERVAL '3 minutes'" if is_postgres() else "last_active >= datetime('now', '-3 minutes')"
            today_cond = "DATE(created_at) = CURRENT_DATE" if is_postgres() else "DATE(created_at) = DATE('now')"
            days7_cond = "created_at >= NOW() - INTERVAL '7 days'" if is_postgres() else "created_at >= datetime('now', '-7 days')"
            days14_cond = "created_at >= NOW() - INTERVAL '14 days'" if is_postgres() else "created_at >= datetime('now', '-14 days')"
            
            cursor.execute(f"SELECT COUNT(*) as count FROM visitor_sessions WHERE {active_cond}")
            active_now = cursor.fetchone()["count"] or 0
            
            cursor.execute("SELECT COUNT(*) as total_sessions, COUNT(DISTINCT ip) as unique_ips FROM visitor_sessions")
            row = cursor.fetchone()
            total_sessions = row["total_sessions"] or 0
            unique_visitors = row["unique_ips"] or 0
            
            cursor.execute(f"SELECT COUNT(*) as count FROM visitor_sessions WHERE {today_cond}")
            visitors_today = cursor.fetchone()["count"] or 0
            
            cursor.execute(f"SELECT COUNT(*) as count FROM visitor_sessions WHERE {days7_cond}")
            visitors_7d = cursor.fetchone()["count"] or 0
            
            cursor.execute("""
                SELECT 
                    AVG(duration_seconds) as avg_duration,
                    SUM(CASE WHEN duration_seconds < 10 THEN 1 ELSE 0 END) as bounces,
                    COUNT(*) as total
                FROM visitor_sessions
            """)
            dur_row = cursor.fetchone()
            avg_duration = round(float(dur_row["avg_duration"] or 0), 1)
            bounces = dur_row["bounces"] or 0
            total_tracked = dur_row["total"] or 0
            bounce_rate = round((bounces / total_tracked * 100) if total_tracked > 0 else 0, 1)
            
            cursor.execute("""
                SELECT device_type, COUNT(*) as count
                FROM visitor_sessions
                GROUP BY device_type
            """)
            devices = {r["device_type"]: r["count"] for r in cursor.fetchall()}
            
            cursor.execute("""
                SELECT os, COUNT(*) as count
                FROM visitor_sessions
                GROUP BY os
                ORDER BY count DESC
                LIMIT 5
            """)
            os_stats = {r["os"]: r["count"] for r in cursor.fetchall()}
            
            cursor.execute(f"""
                SELECT DATE(created_at) as visit_date, COUNT(*) as count
                FROM visitor_sessions
                WHERE {days14_cond}
                GROUP BY DATE(created_at)
                ORDER BY visit_date ASC
            """)
            daily_trend = {str(r["visit_date"]): r["count"] for r in cursor.fetchall()}
            
            trend_labels = []
            trend_values = []
            today = datetime.date.today()
            for i in range(13, -1, -1):
                d = (today - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
                trend_labels.append(d)
                trend_values.append(daily_trend.get(d, 0))
                
            cursor.execute("""
                SELECT
                    SUM(CASE WHEN scroll_depth >= 0 AND scroll_depth < 25 THEN 1 ELSE 0 END) as depth_0_25,
                    SUM(CASE WHEN scroll_depth >= 25 AND scroll_depth < 50 THEN 1 ELSE 0 END) as depth_25_50,
                    SUM(CASE WHEN scroll_depth >= 50 AND scroll_depth < 75 THEN 1 ELSE 0 END) as depth_50_75,
                    SUM(CASE WHEN scroll_depth >= 75 THEN 1 ELSE 0 END) as depth_75_100
                FROM visitor_sessions
            """)
            scroll_row = cursor.fetchone()
            scroll_distribution = {
                "25% (المقدمة فقط)": scroll_row["depth_0_25"] or 0,
                "50% (المشكلة والعرض)": scroll_row["depth_25_50"] or 0,
                "75% (الأسعار والخطوات)": scroll_row["depth_50_75"] or 0,
                "100% (كامل الصفحة وحجز العرض)": scroll_row["depth_75_100"] or 0,
            }
            
            cursor.execute("SELECT COUNT(*) as count FROM leads")
            total_leads = cursor.fetchone()["count"] or 0
            
            conversion_rate = round((total_leads / total_sessions * 100) if total_sessions > 0 else 0, 2)
            
            cursor.execute("""
                SELECT id, session_id, device_type, browser, os, duration_seconds, scroll_depth, referrer, created_at, last_active
                FROM visitor_sessions
                ORDER BY id DESC
                LIMIT 20
            """)
            recent_visitors = [dict(r) for r in cursor.fetchall()]
            
            return jsonify({
                "active_now": active_now,
                "total_sessions": total_sessions,
                "unique_visitors": unique_visitors,
                "visitors_today": visitors_today,
                "visitors_7d": visitors_7d,
                "avg_duration_seconds": avg_duration,
                "bounce_rate": bounce_rate,
                "total_leads": total_leads,
                "conversion_rate": conversion_rate,
                "devices": devices,
                "os_stats": os_stats,
                "trend": {
                    "labels": trend_labels,
                    "values": trend_values
                },
                "scroll_distribution": scroll_distribution,
                "recent_visitors": recent_visitors
            })
    except Exception as e:
        print("Admin stats error:", str(e), file=sys.stderr)
        return jsonify({"error": "حدث خطأ أثناء تحميل الإحصائيات."}), 500

@app.route('/api/admin/leads', methods=['GET'])
@admin_required
def admin_get_leads():
    try:
        with db_session(readonly=True) as (conn, cursor):
            cursor.execute("SELECT id, name, phone, email, business_name, business_type, created_at FROM leads ORDER BY id DESC")
            leads = [dict(r) for r in cursor.fetchall()]
            return jsonify({"leads": leads})
    except Exception as e:
        print("Admin get leads error:", str(e), file=sys.stderr)
        return jsonify({"error": "حدث خطأ أثناء جلب قائمة العملاء."}), 500

@app.route('/api/admin/leads/<int:lead_id>', methods=['DELETE'])
@admin_required
def admin_delete_lead(lead_id):
    try:
        with db_session() as (conn, cursor):
            cursor.execute(adapt_query("DELETE FROM leads WHERE id = ?"), (lead_id,))
        return jsonify({"success": True, "message": "تم حذف الحجز بنجاح."})
    except Exception as e:
        print("Admin delete lead error:", str(e), file=sys.stderr)
        return jsonify({"error": "حدث خطأ أثناء حذف الحجز."}), 500

@app.route('/api/admin/export-leads', methods=['GET'])
@admin_required
def export_leads_csv():
    try:
        with db_session(readonly=True) as (conn, cursor):
            cursor.execute("SELECT id, name, phone, email, business_name, business_type, created_at FROM leads ORDER BY id DESC")
            rows = cursor.fetchall()
            
        output = io.StringIO()
        output.write('\ufeff')
        writer = csv.writer(output)
        writer.writerow(["المعرف (ID)", "الاسم الثلاثي", "رقم الهاتف", "البريد الإلكتروني", "اسم النشاط / الشركة", "نوع الباقة / الطلب", "تاريخ وتوقيت الحجز"])
        
        for r in rows:
            writer.writerow([
                r["id"],
                r["name"],
                r["phone"],
                r["email"] or "غير محدد",
                r["business_name"] or "غير محدد",
                r["business_type"] or "استشارة عامة",
                str(r["created_at"])
            ])
            
        response = app.response_class(
            output.getvalue(),
            mimetype='text/csv; charset=utf-8',
            headers={'Content-Disposition': 'attachment; filename=jawebni_leads.csv'}
        )
        return response
    except Exception as e:
        print("Export CSV error:", str(e), file=sys.stderr)
        return jsonify({"error": "فشل تصدير البيانات."}), 500

# 🛡️ 14. Security Headers & Selective Caching Policy
@app.after_request
def add_security_headers(response):
    # Dynamic APIs and admin dashboards get no-store
    if request.path.startswith('/api/') or request.path in ('/admin.html', '/pathogenesis', '/pathogenesis.html'):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    else:
        # Static files (CSS, JS, fonts, images) are cached properly
        response.headers["Cache-Control"] = "public, max-age=3600"
    
    # 🛡️ OWASP Hardened Security Headers
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com data:; "
        "img-src 'self' data: https:; "
        "connect-src 'self'; "
        "frame-ancestors 'self'; "
        "object-src 'none'; "
        "base-uri 'self';"
    )
    response.headers["Server"] = "Web-Server"
    response.headers.pop("X-Powered-By", None)
    return response

if __name__ == "__main__":
    dir_path = os.path.dirname(os.path.realpath(__file__))
    if dir_path:
        os.chdir(dir_path)
    
    port = int(os.environ.get("PORT", 8000))
    print(f"Starting Flask Server on http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
