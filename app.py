from flask import Flask, render_template, request, jsonify
import requests
from datetime import datetime, timedelta
import sqlite3
import json
import re

app = Flask(__name__)

# Ollama setup
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2"  # Change to your preferred model

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


def get_db():
    """Get database connection with row factory"""
    db = sqlite3.connect('database.db', check_same_thread=False)
    db.row_factory = sqlite3.Row
    return db


def chat_with_ollama(user_message, conversation_history=""):
    """Send a message to Ollama and get AI response"""

    system_prompt = f"""You are a friendly booking assistant for SalesAPE. Help customers book appointments.

Available time slots: {', '.join(SLOTS)} (Monday-Friday)
Today's date: {datetime.now().strftime('%Y-%m-%d')}

Your job:
1. Greet customers and ask what they need
2. Collect: name, phone number, preferred date, preferred time
3. When you have ALL details, respond with ONLY this JSON (no other text):
{{"action": "book", "name": "Customer Name", "phone": "1234567890", "date": "YYYY-MM-DD", "time": "HH:MM"}}

If details are missing, ask for them naturally. Be concise and helpful."""

    prompt = f"{system_prompt}\n\nConversation so far:\n{conversation_history}\n\nCustomer: {user_message}\n\nAssistant:"

    try:
        response = requests.post(OLLAMA_URL, json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False
        }, timeout=30)

        if response.ok:
            return response.json().get("response", "Sorry, I couldn't process that. Please try again.")
        else:
            return "Sorry, the AI service is currently unavailable. Please try again later."
    except requests.exceptions.ConnectionError:
        return "Error: Cannot connect to Ollama. Make sure Ollama is running (ollama serve)."
    except Exception as e:
        return f"Error: {str(e)}"


def extract_booking_json(text):
    """Extract booking JSON from AI response"""
    # Look for JSON pattern in the response
    json_match = re.search(r'\{[^{}]*"action"\s*:\s*"book"[^{}]*\}', text)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass
    return None


@app.route('/')
def dashboard():
    """Serve the main dashboard"""
    return render_template('dashboard.html')


@app.route('/api/bookings', methods=['GET'])
def get_bookings():
    """Get today's bookings for the dashboard"""
    db = get_db()
    today = datetime.now().strftime('%Y-%m-%d')
    bookings = db.execute(
        'SELECT * FROM bookings WHERE date = ? ORDER BY time',
        (today,)
    ).fetchall()
    return jsonify([dict(b) for b in bookings])


@app.route('/api/slots', methods=['GET'])
def get_slots():
    """Get available time slots for a given date"""
    date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    db = get_db()

    # Get booked slots for the date
    booked = db.execute(
        'SELECT time FROM bookings WHERE date = ?',
        (date,)
    ).fetchall()
    booked_times = [b['time'] for b in booked]

    # Return available slots
    available = [slot for slot in SLOTS if slot not in booked_times]
    return jsonify({"date": date, "available": available, "booked": booked_times})


# Store conversation history (in production, use session or database)
conversations = {}

@app.route('/chat', methods=['POST'])
def chat():
    """Handle chat messages with Ollama AI"""
    data = request.json
    user_message = data.get('message', '').strip()
    session_id = data.get('session_id', 'default')

    if not user_message:
        return jsonify({"error": "No message provided"}), 400

    # Get or create conversation history
    if session_id not in conversations:
        conversations[session_id] = []

    history = conversations[session_id]
    history_text = "\n".join([f"{msg['role']}: {msg['content']}" for msg in history[-10:]])  # Last 10 messages

    # Get AI response
    ai_response = chat_with_ollama(user_message, history_text)

    # Update history
    history.append({"role": "Customer", "content": user_message})
    history.append({"role": "Assistant", "content": ai_response})

    # Check if AI wants to make a booking
    booking_data = extract_booking_json(ai_response)
    if booking_data:
        # Make the booking
        db = get_db()
        db.execute(
            'INSERT INTO bookings (name, phone, date, time, status) VALUES (?, ?, ?, ?, ?)',
            (booking_data['name'], booking_data['phone'], booking_data['date'],
             booking_data['time'], 'confirmed')
        )
        db.commit()

        # Send Telegram notification
        send_telegram(
            f"📅 <b>New Booking!</b>\n\n"
            f"Name: {booking_data['name']}\n"
            f"Phone: {booking_data['phone']}\n"
            f"Date: {booking_data['date']}\n"
            f"Time: {booking_data['time']}"
        )

        # Clear conversation after successful booking
        conversations[session_id] = []

        return jsonify({
            "response": f"Great! I've booked your appointment for {booking_data['date']} at {booking_data['time']}. You'll receive a confirmation shortly!",
            "booking": booking_data
        })

    return jsonify({"response": ai_response})


@app.route('/chat/reset', methods=['POST'])
def reset_chat():
    """Reset conversation history"""
    session_id = request.json.get('session_id', 'default')
    if session_id in conversations:
        del conversations[session_id]
    return jsonify({"status": "reset"})


if __name__ == '__main__':
    app.run(debug=True, port=5000)