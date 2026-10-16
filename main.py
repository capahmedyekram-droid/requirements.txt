import os
import sqlite3
import logging
from neonize.client import NewClient
from neonize.events import ConnectedEv, MessageEv, PairStatusEv, event

logging.basicConfig(level=logging.ERROR)

# 🔴 هنسحب الأرقام من إعدادات Railway (أو اكتبهم هنا مباشرة بين العلامتين)
BOT_PHONE_NUMBER = os.getenv("BOT_PHONE", "201000000000")
ADMIN_PHONE = os.getenv("ADMIN_PHONE", "201000000000")

# مسار الحفظ الثابت على Railway عشان الداتا متتمسحش مع الريستارت
DATA_DIR = "/app/data"
os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "store.db")
SESSION_PATH = os.path.join(DATA_DIR, "whatsapp_session.sqlite3")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS users (phone TEXT PRIMARY KEY, balance REAL DEFAULT 0.0)")
    c.execute("CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, price REAL)")
    c.execute("CREATE TABLE IF NOT EXISTS stock (id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER, account_data TEXT, is_sold INTEGER DEFAULT 0)")
    
    c.execute("SELECT COUNT(*) FROM products")
    if c.fetchone()[0] == 0:
        c.executemany("INSERT INTO products (id, name, price) VALUES (?, ?, ?)", [
            (1, "حساب Netflix 4K (شهر)", 100.0),
            (2, "اشتراك Spotify Premium", 60.0),
            (3, "تفعيل Canva Pro", 50.0)
        ])
    conn.commit()
    conn.close()

init_db()

client = NewClient(SESSION_PATH)

@client.event(ConnectedEv)
def on_connected(_: NewClient, __: ConnectedEv):
    print("\n==========================================")
    print("✅ مبروك! تم ربط بوت الواتساب على Railway وشغال 100%")
    print("==========================================\n")

@client.event(PairStatusEv)
def on_pair(_: NewClient, pair: PairStatusEv):
    print(f"✅ تم الربط بنجاح مع الرقم: {pair.ID.User}")

@client.event(MessageEv)
def on_message(client: NewClient, message: MessageEv):
    if message.Info.MessageSource.IsFromMe or message.Info.MessageSource.IsGroup:
        return

    text = (message.Message.conversation or message.Message.extendedTextMessage.text or "").strip()
    if not text:
        return

    sender_jid = message.Info.MessageSource.Sender
    user_phone = sender_jid.User

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (phone, balance) VALUES (?, 0.0)", (user_phone,))
    conn.commit()

    # --- أوامر الأدمن ---
    if user_phone == ADMIN_PHONE:
        if text.startswith("شحن "):
            parts = text.split()
            if len(parts) == 3:
                target_phone, amount = parts[1], float(parts[2])
                c.execute("INSERT OR IGNORE INTO users (phone, balance) VALUES (?, 0.0)", (target_phone,))
                c.execute("UPDATE users SET balance = balance + ? WHERE phone = ?", (amount, target_phone))
                conn.commit()
                client.send_message(sender_jid, f"✅ تم شحن {amount} ج.م للرقم {target_phone}")
                conn.close()
                return

        elif text.startswith("اضافة "):
            parts = text.split(maxsplit=2)
            if len(parts) == 3 and parts[1].isdigit():
                prod_id, acc_data = int(parts[1]), parts[2]
                c.execute("INSERT INTO stock (product_id, account_data) VALUES (?, ?)", (prod_id, acc_data))
                conn.commit()
                client.send_message(sender_jid, f"✅ تم إضافة الحساب للمنتج رقم {prod_id} في المخزون.")
                conn.close()
                return

    # --- أوامر العملاء ---
    if text in ["القائمة", "ابدا", "أبدأ", "0", "start", "السلام عليكم", "هلا"]:
        menu = (
            "🛒 *أهلاً بك في متجر الاشتراكات الرقمية*\n\n"
            "أرسل رقم الخيار المطلوب:\n"
            "*1* - 🛍️ عرض المنتجات والأسعار\n"
            "*2* - 💰 رصيدي وشحن الحساب\n"
            "*3* - 👨‍💻 الدعم الفني\n\n"
            "_(للعودة للقائمة في أي وقت أرسل 0)_"
        )
        client.send_message(sender_jid, menu)

    elif text == "1":
        c.execute('''SELECT p.id, p.name, p.price, COUNT(s.id) 
                     FROM products p LEFT JOIN stock s ON p.id = s.product_id AND s.is_sold = 0 
                     GROUP BY p.id''')
        products = c.fetchall()
        reply = "🛍️ *قائمة المنتجات (تسليم فوري):*\n\n"
        for prod_id, name, price, count in products:
            status = f"✅ متاح ({count})" if count > 0 else "❌ نفذت الكمية"
            reply += f"🔸 *{name}*\n💵 السعر: {price} ج.م | {status}\n🛒 للشراء أرسل: *شراء {prod_id}*\n\n"
        client.send_message(sender_jid, reply)

    elif text == "2":
        c.execute("SELECT balance FROM users WHERE phone = ?", (user_phone,))
        balance = c.fetchone()[0]
        reply = (
            f"💰 *محفظتك في المتجر*\n\n"
            f"📱 رقم حسابك: `{user_phone}`\n"
            f"💵 رصيدك الحالي: *{balance} ج.م*\n\n"
            "⚡ لشحن رصيدك حول المبلغ فودافون كاش أو إنستا باي وأرسل صورة التحويل هنا."
        )
        client.send_message(sender_jid, reply)

    elif text == "3":
        client.send_message(sender_jid, "👨‍💻 اترك رسالتك أو صورة إيصال التحويل هنا وهيرد عليك الأدمن فوراً.")

    elif text.startswith("شراء "):
        parts = text.split()
        if len(parts) == 2 and parts[1].isdigit():
            prod_id = int(parts[1])
            c.execute("SELECT name, price FROM products WHERE id = ?", (prod_id,))
            product = c.fetchone()
            if not product:
                client.send_message(sender_jid, "❌ رقم المنتج غير صحيح. أرسل 1 لعرض المنتجات.")
                conn.close()
                return
            
            prod_name, price = product
            c.execute("SELECT balance FROM users WHERE phone = ?", (user_phone,))
            balance = c.fetchone()[0]
            
            if balance < price:
                client.send_message(sender_jid, f"❌ رصيدك ({balance} ج.م) غير كافٍ لشراء {prod_name} (سعره {price} ج.م).\nأرسل *2* لشحن رصيدك.")
                conn.close()
                return
            
            c.execute("SELECT id, account_data FROM stock WHERE product_id = ? AND is_sold = 0 LIMIT 1", (prod_id,))
            item = c.fetchone()
            if not item:
                client.send_message(sender_jid, "❌ عذراً، هذا المنتج خلص من المخزون حالياً.")
                conn.close()
                return
            
            stock_id, acc_data = item
            c.execute("UPDATE users SET balance = balance - ? WHERE phone = ?", (price, user_phone))
            c.execute("UPDATE stock SET is_sold = 1 WHERE id = ?", (stock_id,))
            conn.commit()
            
            client.send_message(sender_jid, f"✅ *تم الشراء بنجاح!*\n\n📦 المنتج: {prod_name}\n🔐 الحساب:\n`{acc_data}`\n\n💰 رصيدك المتبقي: {balance - price} ج.م")

    conn.close()

if __name__ == "__main__":
    print("⏳ جاري تشغيل البوت...")
    # لو مفيش جلسة متسجلة قبل كده، هيطبع كود الربط
    client.PairPhone(BOT_PHONE_NUMBER, show_push_notification=True)
    event.wait()
