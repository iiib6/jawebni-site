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

# SQLite database setup
def init_db():
    db_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "leads.db")
    try:
        conn = sqlite3.connect(db_path)
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
        conn.commit()
        conn.close()
        print("Database initialized successfully.")
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

def send_lead_email(lead_data):
    smtp_user = os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("SMTP_PASS")
    
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
    
    if smtp_user and smtp_pass:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"🔥 حجز جديد في جاوبني: {name} - {phone}"
            msg["From"] = f"جاوبني <{smtp_user}>"
            msg["To"] = ADMIN_NOTIFICATION_EMAIL
            
            part = MIMEText(html, "html", "utf-8")
            msg.attach(part)
            
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(smtp_user, smtp_pass)
                server.sendmail(smtp_user, ADMIN_NOTIFICATION_EMAIL, msg.as_string())
            print(f"Email notification successfully sent to {ADMIN_NOTIFICATION_EMAIL}")
        except Exception as e:
            print(f"Failed to send email notification: {str(e)}", file=sys.stderr)
    else:
        print(f"[Lead Recorded]: {name} | {phone} | {biz_name} | Destination: {ADMIN_NOTIFICATION_EMAIL}")

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

