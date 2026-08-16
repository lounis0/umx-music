import os
import json
import uuid
import requests
from flask import Flask, jsonify, request, Response, stream_with_context
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

BOT_TOKEN = os.environ.get("TG_TOKEN", "")
CHAT_ID = os.environ.get("TG_CHAT", "")
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
    return "UMS (User Managed Storage) Backend is running!"

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400
        
    file = request.files['file']
    filename = file.filename
    title = request.form.get('title', filename)
    description = request.form.get('description', '')
    
    try:
        url = f"{TELEGRAM_API}/sendDocument"
        files = {'document': (filename, file.stream, file.mimetype)}
        data = {'chat_id': CHAT_ID, 'disable_notification': True}
        resp = requests.post(url, files=files, data=data)
        
        if resp.status_code == 200:
            result = resp.json()['result']
            file_id = result['document']['file_id']
            file_size = result['document']['file_size']
            
            db = load_db()
            new_file = {
                "id": str(uuid.uuid4())[:8],
                "name": filename,
                "title": title,
                "description": description,
                "size": file_size,
                "type": file.mimetype or "file/octet-stream",
                "tg_id": file_id,
                "date": "Just now"
            }
            db.append(new_file)
            save_db(db)
            return jsonify({"success": True, "file": new_file})
        return jsonify({"error": "Telegram upload failed"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/files', methods=['GET'])
def get_files():
    db = load_db()
    return jsonify(db[::-1])

@app.route('/api/download/<file_id>', methods=['GET'])
def download_file(file_id):
    db = load_db()
    file = next((f for f in db if f['id'] == file_id), None)
    if not file:
        return jsonify({"error": "File not found"}), 404
        
    try:
        resp = requests.get(f"{TELEGRAM_API}/getFile?file_id={file['tg_id']}")
        file_path = resp.json()['result']['file_path']
        download_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
        
        req = requests.get(download_url, stream=True)
        headers = {
            "Content-Disposition": f"attachment; filename={file['name']}",
            "Content-Type": "application/octet-stream"
        }
        return Response(stream_with_context(req.iter_content(chunk_size=8192)), headers=headers)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/delete/<file_id>', methods=['DELETE'])
def delete_file(file_id):
    db = load_db()
    db = [f for f in db if f['id'] != file_id]
    save_db(db)
    return jsonify({"success": True})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
