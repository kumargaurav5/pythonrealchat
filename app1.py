from flask import Flask, request, jsonify, render_template
from flask_socketio import SocketIO, emit
import os
from dotenv import load_dotenv
from websocket import WebSocketApp
import json
import base64
import threading
import logging
import time

# Load environment variables
load_dotenv()
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

if not OPENAI_API_KEY:
    raise ValueError("Missing OpenAI API key. Please set it in the .env file.")

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# Logging configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
SYSTEM_MESSAGE = "You are a helpful personal assistant."
VOICE = "alloy"

# OpenAI WebSocket connection
openai_ws = None

def on_openai_message(ws, message):
    logger.info("Response from ChatGPT: %s", message)
    print(message)
    
    # Parse the received message to extract the response text
    try:
        response = json.loads(message)
        if 'content' in response:
            socketio.emit('response', {'data': response['content']})
    except json.JSONDecodeError:
        logger.error("Failed to decode JSON from the message.")

def on_openai_error(ws, error):
    logger.error(f"OpenAI WebSocket error: {error}")

def on_openai_close(ws, close_status_code, close_msg):
    logger.info("Disconnected from OpenAI Realtime API")

def on_openai_open(ws):
    logger.info("Connected to OpenAI Realtime API")
    send_session_update(ws)

def initialize_openai_websocket():
    global openai_ws
    while True:
        try:
            openai_ws = WebSocketApp(
                "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01",
                header={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "OpenAI-Beta": "realtime=v1"
                },
                on_message=on_openai_message,
                on_error=on_openai_error,
                on_close=on_openai_close,
                on_open=on_openai_open
            )
            openai_ws.run_forever()
            break
        except Exception as e:
            logger.error(f"Failed to connect, retrying... Error: {e}")
            time.sleep(5)

def send_session_update(ws):
    session_update = {
        "type": "session.update",
        "session": {
            "voice": VOICE,
            "instructions": "You are a robotic assistant. Answer questions directly and succinctly.",
            "tools": [],
            "modalities": ["text", "audio"],
            "temperature": 0.5,
            "max_tokens": 500
        }
    }
    ws.send(json.dumps(session_update))

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    logger.info("Client connected")

@socketio.on('disconnect')
def handle_disconnect():
    logger.info("Client disconnected")

@socketio.on('audio_data')
def handle_audio_data(data):
    if openai_ws and openai_ws.sock and openai_ws.sock.connected:
        audio_append = {
            "type": "input_audio_buffer.append",
            "audio": data['audio']
        }
        openai_ws.send(json.dumps(audio_append))

if __name__ == '__main__':
    threading.Thread(target=initialize_openai_websocket, daemon=True).start()
    socketio.run(app, debug=True, port=5050)
