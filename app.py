import os
import json
import uuid
import requests
from flask import Flask, jsonify, request, Response, stream_with_context
from flask_cors import CORS

app = Flask(__name__)
CORS(app) # Allows localhost and any URL to connect

# Telegram Credentials from Environment Variables
BOT_TOKEN = os.environ.get("TG_TOKEN", "fallback_token_here")
CHAT_ID = os.environ.get("TG_CHAT", "fallback_chat_id_here")
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

DB_FILE = "files.json"

def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r') as f:
            return json.load(f)
    return []

def save_db(db):
    with open(DB_FILE, 'w') as f:
        json.dump(db, f)

@app.route('/')
def home():
    return "UMX Drive Backend is running! Storage is unlimited."

# 1. UPLOAD FILE TO TELEGRAM
@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400
        
    file = request.files['file']
    filename = file.filename
    
    try:
        # Send file invisibly to Telegram
        url = f"{TELEGRAM_API}/sendDocument"
        files = {'document': (filename, file.stream, file.mimetype)}
        data = {'chat_id': CHAT_ID, 'disable_notification': True}
        resp = requests.post(url, files=files, data=data)
        
        if resp.status_code == 200:
            # Extract the file_id Telegram uses to store the file
            file_id = resp.json()['result']['document']['file_id']
            file_size = resp.json()['result']['document']['file_size']
            
            db = load_db()
            new_file = {
                "id": str(uuid.uuid4())[:8],
                "name": filename,
                "size": file_size,
                "tg_id": file_id,
                "date": "Just now"
            }
            db.append(new_file)
            save_db(db)
            return jsonify({"success": True, "file": new_file})
        return jsonify({"error": "Telegram upload failed"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# 2. GET LIST OF ALL FILES
@app.route('/api/files', methods=['GET'])
def get_files():
    db = load_db()
    return jsonify(db[::-1]) # Return newest first

# 3. DOWNLOAD / SHARE FILE
@app.route('/api/download/<file_id>', methods=['GET'])
def download_file(file_id):
    db = load_db()
    file = next((f for f in db if f['id'] == file_id), None)
    if not file:
        return jsonify({"error": "File not found"}), 404
        
    try:
        # Ask Telegram for the file path
        resp = requests.get(f"{TELEGRAM_API}/getFile?file_id={file['tg_id']}")
        file_path = resp.json()['result']['file_path']
        
        # Stream the file directly from Telegram to the browser
        download_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
        req = requests.get(download_url, stream=True)
        
        headers = {
            "Content-Disposition": f"attachment; filename={file['name']}",
            "Content-Type": "application/octet-stream"
        }
        
        return Response(stream_with_context(req.iter_content(chunk_size=8192)), headers=headers)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# 4. DELETE FILE
@app.route('/api/delete/<file_id>', methods=['DELETE'])
def delete_file(file_id):
    db = load_db()
    db = [f for f in db if f['id'] != file_id]
    save_db(db)
    return jsonify({"success": True})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
