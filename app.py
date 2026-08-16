import os
import json
import uuid
import requests
from flask import Flask, jsonify, request, Response, stream_with_context
from flask_cors import CORS
import time

app = Flask(__name__)
CORS(app)

BOT_TOKEN = os.environ.get("TG_TOKEN", "missing_token")
CHAT_ID = os.environ.get("TG_CHAT", "missing_chat")
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
DB_FILE = "files.json"

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r') as f:
                return json.load(f)
        except:
            return []
    return []

def save_db(db):
    with open(DB_FILE, 'w') as f:
        json.dump(db, f)

# Auto-fetch ALL previous files from the Telegram Bot's chat history on startup
def sync_telegram_history():
    print("Syncing all previous files from Telegram history...")
    db = load_db()
    existing_ids = {f['tg_id'] for f in db}
    
    offset = 0
    while True:
        try:
            res = requests.get(f"{TELEGRAM_API}/getUpdates?offset={offset}&limit=100")
            if res.status_code != 200:
                break
                
            updates = res.json().get('result', [])
            if not updates:
                break
                
            new_files_added = False
            for update in updates:
                offset = update['update_id'] + 1
                msg = update.get('message')
                if msg and 'document' in msg:
                    doc = msg['document']
                    if doc['file_id'] not in existing_ids:
                        db.append({
                            "id": str(uuid.uuid4())[:8],
                            "name": doc['file_name'],
                            "title": doc['file_name'],
                            "description": "Imported from Telegram history",
                            "size": doc['file_size'],
                            "type": doc.get('mime_type', "file/octet-stream"),
                            "tg_id": doc['file_id'],
                            "date": "Previous"
                        })
                        existing_ids.add(doc['file_id'])
                        new_files_added = True
                        
            if new_files_added:
                save_db(db)
                print(f"Imported {len(db)} total files so far...")
                
        except Exception as e:
            print(f"Sync error: {e}")
            break
            
    save_db(db)
    print(f"Sync complete! Total files in database: {len(db)}")

@app.route('/')
def home():
    return "UMS Backend is running! Previous files synced."

@app.route('/api/files', methods=['GET'])
def get_files():
    db = load_db()
    return jsonify(db[::-1])

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
        resp = requests.post(url, files=files, data=data, timeout=120)
        
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
        return jsonify({"error": "Telegram upload failed", "details": resp.text}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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
    port = int(os.environ.get("PORT", 8000))
    
    # Run sync in the background
    import threading
    threading.Thread(target=sync_telegram_history, daemon=True).start()
    
    app.run(host='0.0.0.0', port=port, debug=False)
