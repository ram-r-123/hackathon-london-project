from flask import Flask, render_template, request, jsonify
import requests
from datetime import datetime, timedelta
import sqlite3

app = Flask(__name__)

# Telegram setup (message @BotFather on Telegram, type /newbot to get these)
TELEGRAM_BOT_TOKEN = '8476030398:AAGjXQbdHrAjrFO4cC2M89S1m96XE6AFt1g'
TELEGRAM_CHAT_ID = '8229887005'  # Your personal chat ID to receive notifications

# Simple availability (9am-5pm, 1hr slots)
SLOTS = [f"{h}:00" for h in range(9, 17)]

# Init DB
conn = sqlite3.connect('database.db', check_same_thread=False)
conn.execute('''CREATE TABLE IF NOT EXISTS bookings
                (id INTEGER PRIMARY KEY, name TEXT, phone TEXT, 
                 date TEXT, time TEXT, status TEXT)''')
conn.commit()


def send_telegram(message):
    """Send a message via Telegram bot"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"  # Allows <b>bold</b> and <i>italic</i>
    }
    try:
        response = requests.post(url, json=payload)
        return response.ok
    except Exception as e:
        print(f"Telegram error: {e}")
        return False


# Example usage in a booking route:
@app.route('/book', methods=['POST'])
def book():
    data = request.json
    name = data.get('name')
    phone = data.get('phone')
    date = data.get('date')
    time = data.get('time')
    
    # Save to DB
    conn.execute('INSERT INTO bookings (name, phone, date, time, status) VALUES (?, ?, ?, ?, ?)',
                 (name, phone, date, time, 'confirmed'))
    conn.commit()
    
    # Send Telegram notification instead of SMS
    send_telegram(f"📅 <b>New Booking!</b>\n\nName: {name}\nPhone: {phone}\nDate: {date}\nTime: {time}")
    
    return jsonify({"status": "success"})