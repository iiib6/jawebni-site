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

@app.route('/api/chat', methods=['POST'])
def chat():
    # 1. Rate limiting check
    client_ip = request.remote_addr or "unknown"
    if is_rate_limited(client_ip):
        return jsonify({
            "error": "لقد تجاوزت حد الطلبات المسموح به. يرجى الانتظار دقيقة قبل المحاولة مجدداً."
        }), 429

    # 2. Check API Key configuration
    if not API_KEY:
        return jsonify({"error": "GEMINI_API_KEY is not configured in .env file."}), 500

    # 3. Parse input and call Gemini with fallback models
    client_payload = request.json or {}
    
    models = [
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite"
    ]
    
    req_payload = {
        "contents": client_payload.get("contents", []),
        "systemInstruction": client_payload.get("systemInstruction", {}),
        "generationConfig": client_payload.get("generationConfig", {
            "temperature": 0.7,
            "maxOutputTokens": 2048
        })
    }
    
    all_429 = True
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
                result["_model_used"] = model
                return jsonify(result)
                
        except Exception as e:
            last_error = e
            err_body = ""
            if hasattr(e, "read"):
                try:
                    err_body = e.read().decode('utf-8')
                except:
                    pass
            if "429" not in str(e):
                all_429 = False
            print(f"Model {model} failed:", str(e), file=sys.stderr)
            if err_body:
                print(f"Error body for {model}:", err_body, file=sys.stderr)
            continue
    
    if all_429:
        return jsonify({"error": "quota_exceeded", "message": "انتهت الحصة اليومية المجانية لمفتاح الـ API. يرجى المحاولة لاحقاً أو استبدال المفتاح."}), 429
    
    return jsonify({"error": f"جميع النماذج فشلت. آخر خطأ: {str(last_error)}", "body": err_body if 'err_body' in dir() else ""}), 500

@app.route('/api/leads', methods=['POST'])
def save_lead():
    data = request.json or {}
    name = data.get("name", "").strip()
    phone = data.get("phone", "").strip()
    email = data.get("email", "").strip()
    business_name = data.get("business_name", "").strip()
    business_type = data.get("business_type", "").strip()
    
    if not name or (not phone and not email):
        return jsonify({"error": "الرجاء إدخال الاسم ومعلومات الاتصال (الهاتف أو الإيميل)."}), 400
        
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
        print("Lead saved successfully.")
        return jsonify({"success": True, "message": "Lead saved successfully."})
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

