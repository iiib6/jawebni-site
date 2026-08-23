from flask import Flask, request, jsonify
import urllib.request
import json
import os
import sys
import time
import sqlite3

app = Flask(__name__, static_folder='.', static_url_path='')

# Rate limit: 15 requests per minute per IP address
RATE_LIMIT_LIMIT = 15
RATE_LIMIT_WINDOW = 60  # seconds
ip_requests = {}  # ip: [timestamps]

def is_rate_limited(ip):
    now = time.time()
    if ip not in ip_requests:
        ip_requests[ip] = []
    ip_requests[ip] = [t for t in ip_requests[ip] if now - t < RATE_LIMIT_WINDOW]
    
    if len(ip_requests[ip]) >= RATE_LIMIT_LIMIT:
        return True
    
    ip_requests[ip].append(now)
    return False

import secrets
import datetime
from functools import wraps

ADMIN_DEFAULT_USER = "admin"
ADMIN_DEFAULT_PASS = "aabbddaA1"

# SQLite database setup
def get_db():
    db_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "leads.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                phone TEXT,
                email TEXT,
                business_name TEXT,
                business_type TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS visitor_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
        conn.commit()
        conn.close()
        print("Database tables initialized successfully (leads, visitor_sessions, admin_tokens).")
    except Exception as e:
        print("Failed to initialize database:", str(e), file=sys.stderr)

# Zero-dependency manual .env loader
def load_env():
    env_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), ".env")
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, val = line.split("=", 1)
                        os.environ[key.strip()] = val.strip()
        except Exception as e:
            print("Failed to read .env file:", str(e), file=sys.stderr)

load_env()
init_db()
API_KEY = os.environ.get("GEMINI_API_KEY")

@app.route('/')
def index():
    return app.send_static_file('index.html')

# Service Account / Vertex AI Authentication setup
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

@app.route('/api/chat', methods=['POST'])
def chat():
    # 1. Rate limiting check
    client_ip = request.remote_addr or "unknown"
    if is_rate_limited(client_ip):
        return jsonify({
            "error": "لقد تجاوزت حد الطلبات المسموح به. يرجى الانتظار دقيقة قبل المحاولة مجدداً."
        }), 429

    client_payload = request.json or {}
    
    req_payload = {
        "contents": client_payload.get("contents", []),
        "systemInstruction": client_payload.get("systemInstruction", {}),
        "generationConfig": client_payload.get("generationConfig", {
            "temperature": 0.7,
            "maxOutputTokens": 2048
        })
    }

    # 2. Try Service Account with Vertex AI first
    token = get_sa_token()
    if token and sa_data:
        import requests
        project = sa_data.get("project_id", "gen-lang-client-0148309017")
        
        # Vertex AI Model endpoints configuration
        vertex_models = [
            ("gemini-3.7-flash", "global"),
            ("gemini-3.5-flash", "global"),
            ("gemini-2.5-flash", "us-central1"),
            ("gemini-2.5-pro", "us-central1")
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
                    
                r = requests.post(url, headers=headers, json=req_payload, timeout=20)
                if r.status_code == 200:
                    res_json = r.json()
                    res_json["_model_used"] = f"Vertex AI: {model}"
                    return jsonify(res_json)
                else:
                    print(f"Vertex AI model {model} failed with status {r.status_code}: {r.text[:200]}", file=sys.stderr)
            except Exception as e:
                print(f"Vertex AI request exception for {model}: {str(e)}", file=sys.stderr)

    # 3. Fallback to Gemini API Key if available
    if API_KEY:
        models = [
            "gemini-2.5-flash",
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite"
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
                with urllib.request.urlopen(req) as response:
                    res_body = response.read().decode('utf-8')
                    result = json.loads(res_body)
                    result["_model_used"] = f"Gemini API: {model}"
                    return jsonify(result)
            except Exception as e:
                print(f"Gemini API model {model} failed: {str(e)}", file=sys.stderr)
                continue
                
    return jsonify({"error": "حدث خطأ في معالجة الرد، يرجى المحاولة لاحقاً."}), 500

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

ADMIN_NOTIFICATION_EMAIL = "aboody.alfaloje20@gmail.com"

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
    
    name = lead_data.get("name", "غير محدد")
    phone = lead_data.get("phone", "غير محدد")
    biz_name = lead_data.get("business_name", "غير محدد")
    biz_type = lead_data.get("business_type", "استشارة عامة")
    email = lead_data.get("email", "غير محدد")
    
    # Format WhatsApp URL
    clean_phone = "".join(filter(str.isdigit, phone))
    if clean_phone.startswith("07"):
        clean_phone = "964" + clean_phone[1:]
    
    html = f"""
    <!DOCTYPE html>
    <html dir="rtl" lang="ar">
    <head><meta charset="utf-8"></head>
    <body style="font-family: Arial, sans-serif; background-color: #F6F2E9; padding: 20px; color: #22392B;">
      <div style="max-width: 560px; margin: auto; background: #ffffff; border: 1px solid #C4A35A; border-radius: 16px; padding: 25px; box-shadow: 0 4px 15px rgba(0,0,0,0.05);">
        <h2 style="color: #22392B; margin-top: 0; border-bottom: 2px solid #C4A35A; padding-bottom: 12px;">🎉 حجز جديد على منصة «جاوبني»</h2>
        <p style="font-size: 15px; color: #445138;">وصلك طلب تواصل / اشتراك جديد من الموقع الرسمي:</p>
        
        <table style="width: 100%; border-collapse: collapse; margin: 20px 0; font-size: 14px;">
          <tr style="background-color: #F6F2E9;">
            <td style="padding: 10px; font-weight: bold; border: 1px solid #E2D9C6; width: 35%;">الاسم الثلاثي:</td>
            <td style="padding: 10px; border: 1px solid #E2D9C6; font-weight: bold; color: #22392B;">{name}</td>
          </tr>
          <tr>
            <td style="padding: 10px; font-weight: bold; border: 1px solid #E2D9C6;">رقم الهاتف:</td>
            <td style="padding: 10px; border: 1px solid #E2D9C6;">
              <a href="tel:{phone}" style="color: #22392B; font-weight: bold; text-decoration: none;">{phone}</a>
              &nbsp;|&nbsp;
              <a href="https://wa.me/{clean_phone}" style="color: #25D366; font-weight: bold; text-decoration: none;">💬 فتح بالواتساب</a>
            </td>
          </tr>
          <tr style="background-color: #F6F2E9;">
            <td style="padding: 10px; font-weight: bold; border: 1px solid #E2D9C6;">اسم المشروع / النشاط:</td>
            <td style="padding: 10px; border: 1px solid #E2D9C6;">{biz_name}</td>
          </tr>
          <tr>
            <td style="padding: 10px; font-weight: bold; border: 1px solid #E2D9C6;">الخطة / نوع الطلب:</td>
            <td style="padding: 10px; border: 1px solid #E2D9C6; color: #C4A35A; font-weight: bold;">{biz_type}</td>
          </tr>
        </table>
        
        <div style="background-color: #22392B; color: #F6F2E9; padding: 12px 18px; border-radius: 10px; text-align: center; margin-top: 20px;">
          <a href="https://wa.me/{clean_phone}" style="color: #C4A35A; text-decoration: none; font-weight: bold; font-size: 15px;">مراسلة الزبون على الواتساب فوراً 🚀</a>
        </div>
      </div>
    </body>
    </html>
    """
    
    # 1. Primary Method: Google Apps Script Webhook (100% reliable on Render, uses port 443)
    GOOGLE_WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbyySbR7dOIUfLlF_xoIaxiAUCZvzUAarzA9FBDV2oS04Jb7S4f6g1un_OMeEtIYYskC/exec"
    try:
        import requests
        res = requests.post(GOOGLE_WEBHOOK_URL, json=lead_data, timeout=12)
        if res.status_code == 200:
            safe_print(f"Lead email successfully dispatched via Google Apps Script Webhook to {ADMIN_NOTIFICATION_EMAIL}")
            return
    except Exception as e:
        safe_print(f"Google Webhook attempt failed: {str(e)}, trying direct SMTP fallback...", file=sys.stderr)

    # 2. Secondary Method: SMTP Fallback
    if smtp_user and smtp_pass:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"🔥 حجز جديد في جاوبني: {name} - {phone}"
        msg["From"] = f"جاوبني <{smtp_user}>"
        msg["To"] = ADMIN_NOTIFICATION_EMAIL
        
        part = MIMEText(html, "html", "utf-8")
        msg.attach(part)
        
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
    else:
        safe_print(f"[Lead Recorded]: Destination: {ADMIN_NOTIFICATION_EMAIL}")

@app.route('/api/leads', methods=['POST'])
def save_lead():
    data = request.json or {}
    name = data.get("name", "").strip()
    phone = data.get("phone", "").strip()
    email = data.get("email", "").strip()
    business_name = data.get("business_name", "").strip()
    business_type = data.get("business_type", "").strip()
    
    if not name or (not phone and not email):
        return jsonify({"error": "الرجاء إدخال الاسم الثلاثي ورقم الهاتف للتواصل."}), 400
        
    try:
        db_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "leads.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO leads (name, phone, email, business_name, business_type)
            VALUES (?, ?, ?, ?, ?)
        """, (name, phone, email, business_name, business_type))
        conn.commit()
        conn.close()
        print("Lead saved successfully in SQLite.")
        
        # Send Email notification
        send_lead_email(data)
        
        return jsonify({"success": True, "message": "تم استلام وتثبيت حجزك بنجاح! سنتواصل معك قريباً."})
    except Exception as e:
        print("Failed to save lead to database:", str(e), file=sys.stderr)
        return jsonify({"error": "حدث خطأ أثناء حفظ البيانات."}), 500

# ==========================================
# 📊 Analytics & Visitor Tracking System
# ==========================================

def parse_user_agent(ua_string, screen_width=None):
    ua = (ua_string or "").lower()
    
    # Device Detection
    device = "حاسوب (Desktop)"
    if "mobi" in ua or "iphone" in ua or "android" in ua and "tablet" not in ua:
        device = "موبايل (Mobile)"
    elif "ipad" in ua or "tablet" in ua or (screen_width and 768 <= screen_width <= 1024):
        device = "لوحي (Tablet)"
    elif screen_width and screen_width < 768:
        device = "موبايل (Mobile)"
        
    # OS Detection
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
        
    # Browser Detection
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
    data = request.json or {}
    session_id = data.get("session_id", "").strip()
    if not session_id:
        session_id = secrets.token_hex(16)
        
    referrer = data.get("referrer", "").strip()
    screen_width = data.get("screen_width")
    raw_ua = request.headers.get("User-Agent", "")
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "127.0.0.1").split(",")[0].strip()
    
    device, os_name, browser = parse_user_agent(raw_ua, screen_width)
    
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO visitor_sessions (session_id, ip, user_agent, device_type, browser, os, referrer, duration_seconds, scroll_depth, created_at, last_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(session_id) DO UPDATE SET
                last_active = CURRENT_TIMESTAMP
        """, (session_id, ip, raw_ua[:250], device, browser, os_name, referrer[:250]))
        conn.commit()
        conn.close()
        return jsonify({"success": True, "session_id": session_id})
    except Exception as e:
        print("Track visit error:", str(e), file=sys.stderr)
        return jsonify({"error": "Failed to track visit"}), 500

@app.route('/api/track/ping', methods=['POST'])
def track_ping():
    data = request.json or {}
    session_id = data.get("session_id", "").strip()
    if not session_id:
        return jsonify({"error": "Missing session_id"}), 400
        
    duration = int(data.get("duration_seconds", 0))
    scroll_depth = int(data.get("scroll_depth", 0))
    
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE visitor_sessions
            SET duration_seconds = MAX(duration_seconds, ?),
                scroll_depth = MAX(scroll_depth, ?),
                last_active = CURRENT_TIMESTAMP
            WHERE session_id = ?
        """, (duration, scroll_depth, session_id))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        print("Track ping error:", str(e), file=sys.stderr)
        return jsonify({"error": "Failed to update ping"}), 500

# ==========================================
# 🔒 Admin Authentication & Security
# ==========================================

def get_admin_creds():
    admin_user = os.environ.get("ADMIN_USER", ADMIN_DEFAULT_USER).strip()
    admin_pass = os.environ.get("ADMIN_PASS", ADMIN_DEFAULT_PASS).strip()
    return admin_user, admin_pass

def verify_token(token):
    if not token:
        return None
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT username, expires_at FROM admin_tokens
            WHERE token = ? AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
        """, (token,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return row["username"]
    except Exception as e:
        print("Verify token error:", str(e), file=sys.stderr)
    return None

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 1. Check Authorization header
        auth_header = request.headers.get("Authorization", "")
        token = None
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1].strip()
        
        # 2. Check Cookie
        if not token:
            token = request.cookies.get("jawebni_admin_token")
            
        username = verify_token(token)
        if not username:
            return jsonify({"error": "غير مصرح لك بالوصول. يرجى تسجيل الدخول أولاً."}), 401
            
        return f(*args, **kwargs)
    return decorated_function

@app.route('/admin')
@app.route('/admin.html')
def admin_page():
    return app.send_static_file('admin.html')

@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    data = request.json or {}
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    
    admin_user, admin_pass = get_admin_creds()
    
    if username == admin_user and password == admin_pass:
        token = secrets.token_hex(32)
        expires_at = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
        
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO admin_tokens (token, username, created_at, expires_at)
                VALUES (?, ?, CURRENT_TIMESTAMP, ?)
            """, (token, username, expires_at))
            conn.commit()
            conn.close()
            
            res = jsonify({
                "success": True,
                "message": "تم تسجيل الدخول بنجاح",
                "token": token,
                "username": username
            })
            # Set cookie for 7 days
            res.set_cookie(
                "jawebni_admin_token",
                token,
                max_age=7*24*60*60,
                httponly=True,
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
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM admin_tokens WHERE token = ?", (token,))
            conn.commit()
            conn.close()
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

# ==========================================
# 📈 Protected Admin Stats & Management APIs
# ==========================================

@app.route('/api/admin/stats', methods=['GET'])
@admin_required
def admin_stats():
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # 1. Active Now (last active in last 3 minutes)
        cursor.execute("""
            SELECT COUNT(*) as count FROM visitor_sessions
            WHERE last_active >= datetime('now', '-3 minutes')
        """)
        active_now = cursor.fetchone()["count"]
        
        # 2. Total Sessions & Unique Visitors
        cursor.execute("SELECT COUNT(*) as total_sessions, COUNT(DISTINCT ip) as unique_ips FROM visitor_sessions")
        row = cursor.fetchone()
        total_sessions = row["total_sessions"] or 0
        unique_visitors = row["unique_ips"] or 0
        
        # 3. Today's visitors
        cursor.execute("""
            SELECT COUNT(*) as count FROM visitor_sessions
            WHERE DATE(created_at) = DATE('now')
        """)
        visitors_today = cursor.fetchone()["count"] or 0
        
        # 4. Last 7 Days visitors
        cursor.execute("""
            SELECT COUNT(*) as count FROM visitor_sessions
            WHERE created_at >= datetime('now', '-7 days')
        """)
        visitors_7d = cursor.fetchone()["count"] or 0
        
        # 5. Average Duration & Bounce Rate
        cursor.execute("""
            SELECT 
                AVG(duration_seconds) as avg_duration,
                SUM(CASE WHEN duration_seconds < 10 THEN 1 ELSE 0 END) as bounces,
                COUNT(*) as total
            FROM visitor_sessions
        """)
        dur_row = cursor.fetchone()
        avg_duration = round(dur_row["avg_duration"] or 0, 1)
        bounces = dur_row["bounces"] or 0
        total_tracked = dur_row["total"] or 0
        bounce_rate = round((bounces / total_tracked * 100) if total_tracked > 0 else 0, 1)
        
        # 6. Device Breakdown
        cursor.execute("""
            SELECT device_type, COUNT(*) as count
            FROM visitor_sessions
            GROUP BY device_type
        """)
        device_rows = cursor.fetchall()
        devices = {r["device_type"]: r["count"] for r in device_rows}
        
        # 7. OS Breakdown
        cursor.execute("""
            SELECT os, COUNT(*) as count
            FROM visitor_sessions
            GROUP BY os
            ORDER BY count DESC
            LIMIT 5
        """)
        os_rows = cursor.fetchall()
        os_stats = {r["os"]: r["count"] for r in os_rows}
        
        # 8. Daily Visits Trend (Last 14 Days)
        cursor.execute("""
            SELECT DATE(created_at) as visit_date, COUNT(*) as count
            FROM visitor_sessions
            WHERE created_at >= datetime('now', '-14 days')
            GROUP BY DATE(created_at)
            ORDER BY visit_date ASC
        """)
        daily_rows = cursor.fetchall()
        daily_trend = {r["visit_date"]: r["count"] for r in daily_rows}
        
        # Generate complete 14-day list even with 0s
        trend_labels = []
        trend_values = []
        today = datetime.date.today()
        for i in range(13, -1, -1):
            d = (today - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
            trend_labels.append(d)
            trend_values.append(daily_trend.get(d, 0))
            
        # 9. Scroll Depth Distribution
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
        
        # 10. Leads Count & Conversion Rate
        cursor.execute("SELECT COUNT(*) as count FROM leads")
        total_leads = cursor.fetchone()["count"] or 0
        
        conversion_rate = round((total_leads / total_sessions * 100) if total_sessions > 0 else 0, 2)
        
        # 11. Recent 20 Visitor Sessions
        cursor.execute("""
            SELECT id, session_id, device_type, browser, os, duration_seconds, scroll_depth, referrer, created_at, last_active
            FROM visitor_sessions
            ORDER BY id DESC
            LIMIT 20
        """)
        recent_rows = cursor.fetchall()
        recent_visitors = [dict(r) for r in recent_rows]
        
        conn.close()
        
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
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, phone, email, business_name, business_type, created_at FROM leads ORDER BY id DESC")
        rows = cursor.fetchall()
        conn.close()
        leads = [dict(r) for r in rows]
        return jsonify({"leads": leads})
    except Exception as e:
        print("Admin get leads error:", str(e), file=sys.stderr)
        return jsonify({"error": "حدث خطأ أثناء جلب قائمة العملاء."}), 500

@app.route('/api/admin/leads/<int:lead_id>', methods=['DELETE'])
@admin_required
def admin_delete_lead(lead_id):
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "تم حذف الحجز بنجاح."})
    except Exception as e:
        print("Admin delete lead error:", str(e), file=sys.stderr)
        return jsonify({"error": "حدث خطأ أثناء حذف الحجز."}), 500

import csv
import io

@app.route('/api/admin/export-leads', methods=['GET'])
@admin_required
def export_leads_csv():
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, phone, email, business_name, business_type, created_at FROM leads ORDER BY id DESC")
        rows = cursor.fetchall()
        conn.close()
        
        output = io.StringIO()
        # UTF-8 BOM so Microsoft Excel renders Arabic correctly
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
                r["created_at"]
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

# Disable caching for all static files
@app.after_request
def add_header(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

if __name__ == "__main__":
    dir_path = os.path.dirname(os.path.realpath(__file__))
    if dir_path:
        os.chdir(dir_path)
    
    port = int(os.environ.get("PORT", 8000))
    print(f"Starting Flask Server on http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

