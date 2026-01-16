from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import sqlite3
from datetime import datetime
from twilio.rest import Client
import os
import razorpay

# ---------------- CONFIG ----------------

RAZORPAY_KEY_ID = os.environ.get("rzp_live_S4Sq8zIR6ztzan")
RAZORPAY_KEY_SECRET = os.environ.get("PeSSCiHUbHMLudERgDiNdE9q")

TWILIO_SID = os.environ.get("TWILIO_SID")
TWILIO_TOKEN = os.environ.get("TWILIO_TOKEN")
WHATSAPP_FROM = "whatsapp:+14155238886"   # Twilio sandbox
WHATSAPP_TO = os.environ.get("+919713079285")

# Razorpay client
razor_client = None
if RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET:
    razor_client = razorpay.Client(
        auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET)
    )

# ---------------- APP ----------------

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def home():
    return FileResponse("static/index.html")

# ---------------- DATABASE ----------------

conn = sqlite3.connect("database.db", check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone TEXT,
    address TEXT,
    items TEXT,
    pickup_date TEXT,
    pickup_slot TEXT,
    status TEXT,
    created_at TEXT,
    payment_id TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    price INTEGER,
    active INTEGER
)
""")

cur.execute("""
INSERT OR IGNORE INTO settings (key, value)
VALUES ('laundry_name', 'Urban Laundry')
""")

conn.commit()

# ---------------- WHATSAPP ----------------

def send_whatsapp(order):
    if not TWILIO_SID or not TWILIO_TOKEN or not WHATSAPP_TO:
        print("WhatsApp not configured")
        return

    try:
        client = Client(TWILIO_SID, TWILIO_TOKEN)

        items_text = ""
        for i in order["items"].values():
            items_text += f'{i["name"]} x{i["qty"]}\n'

        payment = order.get("payment_id", "COD")

        message = f"""
🧺 New Laundry Order

Items:
{items_text}

Pickup:
{order["pickup_date"]} | {order["pickup_slot"]}

Address:
{order["address"]}

Payment:
{"UPI Paid" if payment != "COD" else "Cash on Delivery"}
"""

        client.messages.create(
            body=message,
            from_=WHATSAPP_FROM,
            to=WHATSAPP_TO
        )

        print("WhatsApp sent")

    except Exception as e:
        print("WhatsApp error:", e)

# ---------------- PAYMENTS ----------------

@app.post("/create_payment")
def create_payment(data: dict):

    if not razor_client:
        return {"error": "Payment not configured"}

    try:
        amount = int(data["amount"]) * 100

        order = razor_client.order.create({
            "amount": amount,
            "currency": "INR",
            "payment_capture": 1
        })

        return order

    except Exception as e:
        return {"error": str(e)}

# ---------------- ORDERS ----------------

@app.post("/place_order")
def place_order(order: dict):

    print("ORDER RECEIVED:", order)

    payment_id = order.get("payment_id", "COD")

    cur.execute("""
        INSERT INTO orders
        (phone, address, items, pickup_date, pickup_slot,
         status, created_at, payment_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        order["phone"],
        order["address"],
        str(order["items"]),
        order["pickup_date"],
        order["pickup_slot"],
        "PLACED",
        datetime.now().isoformat(),
        payment_id
    ))

    conn.commit()

    send_whatsapp(order)

    return {"message": "Order placed successfully"}

@app.get("/orders")
def get_orders():
    cur.execute("SELECT * FROM orders ORDER BY id DESC")
    return cur.fetchall()

@app.post("/update_status")
def update_status(data: dict):
    cur.execute(
        "UPDATE orders SET status=? WHERE id=?",
        (data["status"], data["id"])
    )
    conn.commit()
    return {"message": "Status updated"}

# ---------------- SETTINGS ----------------

@app.get("/settings")
def get_settings():
    cur.execute("SELECT value FROM settings WHERE key='laundry_name'")
    laundry_name = cur.fetchone()[0]

    cur.execute("SELECT id, name, price FROM items WHERE active=1")
    items = cur.fetchall()

    return {
        "laundry_name": laundry_name,
        "items": items
    }

@app.post("/settings/laundry_name")
def update_laundry_name(data: dict):
    cur.execute(
        "UPDATE settings SET value=? WHERE key='laundry_name'",
        (data["laundry_name"],)
    )
    conn.commit()
    return {"message": "Laundry name updated"}

@app.post("/items/add")
def add_item(data: dict):
    cur.execute(
        "INSERT INTO items (name, price, active)
         VALUES (?, ?, 1)",
        (data["name"], data["price"])
    )
    conn.commit()
    return {"message": "Item added"}

@app.post("/items/delete")
def delete_item(data: dict):
    cur.execute(
        "UPDATE items SET active=0 WHERE id=?",
        (data["id"],)
    )
    conn.commit()
    return {"message": "Item removed"}

