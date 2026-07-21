import sqlite3
import os
import sys

# Reconfigure encoding to utf-8 for safe Arabic display in Windows command prompt
if sys.platform.startswith("win"):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

db_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "leads.db")

def check_leads():
    if not os.path.exists(db_path):
        print("❌ لم يتم تسجيل أي حجوزات أو زبائن بعد! (قاعدة البيانات غير موجودة)")
        return
        
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, phone, email, business_name, business_type, created_at FROM leads ORDER BY id DESC")
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            print("📭 قاعدة البيانات فارغة. لم يقم أي زبون بالحجز بعد.")
            return
            
        print(f"\n📊 تم العثور على ({len(rows)}) عملاء محتملين (Leads):\n")
        print("=" * 80)
        for row in rows:
            print(f"🆔 المعرف: {row[0]}")
            print(f"👤 الاسم: {row[1]}")
            print(f"📞 الهاتف: {row[2]}")
            print(f"📧 البريد: {row[3]}")
            print(f"🏢 اسم الشركة/العيادة: {row[4]}")
            print(f"💼 نوع النشاط: {row[5]}")
            print(f"📅 تاريخ الحجز: {row[6]}")
            print("=" * 80)
            
    except Exception as e:
        print("❌ حدث خطأ أثناء قراءة قاعدة البيانات:", str(e))

if __name__ == "__main__":
    check_leads()
    input("\nاضغط Enter للخروج...")
