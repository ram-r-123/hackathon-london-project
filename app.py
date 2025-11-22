import requests

BOT_TOKEN = "your_bot_token"
CHAT_ID = "your_chat_id"

def send_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": text})