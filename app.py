import os
import signal
import time
import logging
import base64
import json
import threading
from dotenv import load_dotenv
from flask import Flask, render_template
from flask_socketio import SocketIO, emit
from websocket import create_connection
from flask_cors import CORS

# Initialize CORS


# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

# Load environment variables from a .env file
load_dotenv()

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app)

# Define a quit flag for clean shutdown
quitFlag = False

def signal_handler(sig, frame):
    """Handle Ctrl+C and initiate graceful shutdown."""
    logging.info('Received Ctrl+C! Initiating shutdown...')
    global quitFlag
    quitFlag = True

# Set up signal handling
signal.signal(signal.SIGINT, signal_handler)

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('audio_data')
def handle_audio_data(data):
    """Handle incoming audio data from the client and send it to OpenAI API."""
    logging.info(f'Received audio data of length: {len(data)} bytes')

    # Start a thread to process the audio data and get a response from OpenAI
    threading.Thread(target=send_to_openai, args=(data,)).start()

def send_to_openai(audio_data):
    """Send audio data to OpenAI Realtime API and relay responses."""
    api_key = os.getenv('OPENAI_API_KEY')
    ws_url = 'wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01'

    if not api_key:
        logging.error('OPENAI_API_KEY not found in environment variables!')
        return

    # Connect to OpenAI Realtime API with the required headers
    headers = [
        f'Authorization: Bearer {api_key}',
        'OpenAI-Beta: realtime=v1'
    ]
    ws = create_connection(ws_url, header=headers)
    logging.info('Connected to OpenAI Realtime API.')

    # Send initial request to start the conversation
    ws.send(json.dumps({
        'type': 'response.create',
        'response': {
            'modalities': ['audio', 'text'],
            'instructions': 'Please assist the user.'
        }
    }))

    # Send the audio data to the OpenAI API
    encoded_audio = base64.b64encode(audio_data).decode('utf-8')
    ws.send(json.dumps({'type': 'input_audio_buffer.append', 'audio': encoded_audio}))

    try:
        while True:
            # Wait for responses from OpenAI
            response = ws.recv()
            message = json.loads(response)

            # Handle different message types from OpenAI
            event_type = message.get('type')
            logging.info(f'Received message type: {event_type}')

            if event_type == 'response.audio.delta':
                audio_content = base64.b64decode(message['delta'])
                logging.info(f'Relaying {len(audio_content)} bytes of audio data to clients.')
                
                # Emit the audio content in the context of the SocketIO thread
                socketio.emit('audio_response', audio_content)
                print("audio_content" )

            elif event_type == 'response.audio.done':
                logging.info('AI finished speaking.')
                break

    except Exception as e:
        logging.error(f'Error communicating with OpenAI: {e}')
    
    finally:
        ws.close()
        logging.info('OpenAI Realtime API connection closed.')



def main():
    try:
        socketio.run(app, debug=True)  # Start the Flask app with SocketIO

    except Exception as e:
        logging.error(f'Error in main loop: {e}')

    finally:
        logging.info('Exiting main.')

if __name__ == '__main__':
    main()
