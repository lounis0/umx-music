import os
import json
import uuid
import requests
import base64
import tempfile
import asyncio
import threading
from flask import Flask, jsonify, request, Response, stream_with_context
from flask_cors import CORS
from telethon import TelegramClient
from telethon.sessions import StringSession

app = Flask(__name__)
CORS(app)

# Environment Variables
API_ID = int(os.environ.get("TELEGRAM_API_ID", 0))
API_HASH = os.environ.get("TELEGRAM_API_HASH", "")
SESSION_STR = os.environ.get("TELEGRAM_SESSION_STRING", "")
CHAT_ENTITY = os.environ.get("TELEGRAM_CHAT", "me")

GH_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GH_OWNER = os.environ.get("GITHUB_OWNER", "lounis0")
GH_REPO = os.environ.get("GITHUB_REPO", "umx-database")
GH_BRANCH = "main"

DB_FILE = "files.json"

# --- Telethon Background Thread Setup ---
telethon_loop = asyncio.new_event_loop()
telethon_thread = threading.Thread(target=telethon_loop.run_forever, daemon=True)
telethon_thread.start()

client = TelegramClient(StringSession(SESSION_STR), API_ID, API_HASH, loop=telethon_loop)

def run_async(coro):
    """Helper to run async functions in the dedicated Telethon loop with a timeout"""
    future = asyncio.run_coroutine_threadsafe(coro, telethon_loop)
    return future.result(timeout=120) # 2 minute timeout for large uploads

def ensure_connected():
    async def _task():
        if not client.is_connected():
            print("Telethon disconnected. Reconnecting...")
            await client.connect()
        if not await client.is_user_authorized():
            raise Exception("Telegram session is invalid or expired.")
    run_async(_task())

# Initialize Telegram IMMEDIATELY when Gunicorn loads (not in __main__)
print("Connecting Telethon on startup...")
try:
    ensure_connected()
    print("✅ Telethon Connected!")
    
    # Scrape history in background so it doesn't block startup
    def bg_scrape():
        try:
            db = gh_get_db()
            existing_msg_ids = {f['tg_id'] for f in db}
            new_files = []
            
            async def _scrape():
                async for msg in client.iter_messages(CHAT_ENTITY):
                    if msg.document and msg.id not in existing_msg_ids:
                        file_name = ""
                        for attr in msg.document.attributes:
                            if hasattr(attr, 'file_name') and attr.file_name:
                                file_name = attr.file_name
                                break
                        new_files.append({
                            "id": str(uuid.uuid4())[:8],
                            "name": file_name or f"file_{msg.id}",
                            "title": file_name or f"file_{msg.id}",
                            "description": "Scraped from history",
                            "size": msg.document.size,
                            "type": msg.document.mime_type or "file/octet-stream",
                            "tg_id": msg.id,
                            "date": msg.date.strftime("%Y-%m-%d %H:%M")
                        })
                        existing_msg_ids.add(msg.id)
            
            run_async(_scrape())
            if new_files:
                db.extend(new_files)
                gh_save_db(db)
                print(f"Scrape complete! Added {len(new_files)} old files.")
            else:
                print("Scrape complete. No new files found.")
        except Exception as e:
            print(f"Background Scrape Error: {e}")

    threading.Thread(target=bg_scrape, daemon=True).start()

except Exception as e:
    print(f"Startup Telethon Error: {e}")

# --- GitHub Database API ---
def gh_get_db():
    url = f"https://raw.githubusercontent.com/{GH_OWNER}/{GH_REPO}/{GH_BRANCH}/{DB_FILE}"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        print(f"GitHub Get DB Exception: {e}")
    return []

def gh_save_db(db):
    url = f"https://api.github.com/repos/{GH_OWNER}/{GH_REPO}/contents/{DB_FILE}"
    headers = {"Authorization": f"token {GH_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    
    sha = None
    try:
        get_res = requests.get(f"{url}?ref={GH_BRANCH}", headers=headers, timeout=10)
        if get_res.status_code == 200:
            sha = get_res.json().get("sha")
    except:
        pass

    payload = {
        "message": "UMS: Update database",
        "content": base64.b64encode(json.dumps(db, indent=4).encode()).decode(),
        "branch": GH_BRANCH
    }
    if sha:
        payload["sha"] = sha
        
    try:
        res = requests.put(url, headers=headers, json=payload, timeout=15)
        if res.status_code in [200, 201]:
            print("✅ Database saved to GitHub!")
        else:
            print(f"GitHub Save DB Error: {res.status_code} - {res.text}")
    except Exception as e:
        print(f"GitHub Save DB Exception: {e}")

@app.route('/')
def home():
    return "UMS Robust Backend Running!"

@app.route('/api/files')
def get_files():
    return jsonify(gh_get_db()[::-1])

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400
        
    file = request.files['file']
    filename = file.filename
    title = request.form.get('title', filename)
    description = request.form.get('description', '')
    
    temp_path = tempfile.mktemp()
    
    try:
        ensure_connected()
        file.save(temp_path)
        
        async def _upload():
            return await client.send_file(CHAT_ENTITY, temp_path, caption=f"UMS Upload: {title}")
            
        msg = run_async(_upload())
            
        if msg and msg.document:
            db = gh_get_db()
            new_file = {
                "id": str(uuid.uuid4())[:8],
                "name": filename,
                "title": title,
                "description": description,
                "size": msg.document.size,
                "type": msg.document.mime_type or "file/octet-stream",
                "tg_id": msg.id,
                "date": "Just now"
            }
            db.append(new_file)
            gh_save_db(db)
            return jsonify({"success": True, "file": new_file})
        else:
            return jsonify({"error": "Telegram did not return a valid document."}), 500
            
    except Exception as e:
        print(f"UPLOAD ERROR: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

@app.route('/api/download/<file_id>')
def download_file(file_id):
    db = gh_get_db()
    file = next((f for f in db if f['id'] == file_id), None)
    if not file:
        return jsonify({"error": "File not found"}), 404
        
    temp_path = tempfile.mktemp()
    
    try:
        ensure_connected()
        
        async def _download():
            msg = await client.get_messages(CHAT_ENTITY, ids=file['tg_id'])
            if not msg or not msg.document:
                return None
            return await client.download_media(msg, file=temp_path)
            
        run_async(_download())
        
        def stream_and_delete():
            try:
                with open(temp_path, 'rb') as f:
                    while True:
                        chunk = f.read(8192)
                        if not chunk:
                            break
                        yield chunk
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)

        headers = {
            "Content-Disposition": f"attachment; filename={file['name']}",
            "Content-Type": "application/octet-stream"
        }
        return Response(stream_with_context(stream_and_delete()), headers=headers)
        
    except Exception as e:
        print(f"DOWNLOAD ERROR: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/delete/<file_id>', methods=['DELETE'])
def delete_file(file_id):
    db = gh_get_db()
    file = next((f for f in db if f['id'] == file_id), None)
    if not file:
        return jsonify({"error": "File not found"}), 404
        
    try:
        ensure_connected()
        
        async def _delete():
            await client.delete_messages(CHAT_ENTITY, [file['tg_id']])
            
        run_async(_delete())
        
        db = [f for f in db if f['id'] != file_id]
        gh_save_db(db)
        return jsonify({"success": True})
    except Exception as e:
        print(f"DELETE ERROR: {e}")
        return jsonify({"error": str(e)}), 500

# No __main__ block needed because Gunicorn loads the app directly
