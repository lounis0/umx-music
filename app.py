import os
import json
import uuid
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Owner Credentials saved directly in Python
OWNER_USER = "admin"
OWNER_PASS = "umx123" # Change this to whatever you want!
VALID_TOKENS = set() # Stores active login sessions

DB_FILE = "posts.json"

# Helper to load posts from file
def load_posts():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r') as f:
            return json.load(f)
    return []

# Helper to save posts to file
def save_posts(posts):
    with open(DB_FILE, 'w') as f:
        json.dump(posts, f)

@app.route('/')
def home():
    return "UMX Blog Backend is running!"

# ======= USER ENDPOINTS =======

@app.route('/api/posts', methods=['GET'])
def get_posts():
    posts = load_posts()
    # Return newest first
    return jsonify(posts[::-1])

# ======= OWNER ENDPOINTS =======

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    if data.get('username') == OWNER_USER and data.get('password') == OWNER_PASS:
        token = str(uuid.uuid4())
        VALID_TOKENS.add(token)
        return jsonify({"token": token})
    return jsonify({"error": "Invalid credentials"}), 401

@app.route('/api/publish', methods=['POST'])
def publish():
    token = request.headers.get('Authorization')
    if token not in VALID_TOKENS:
        return jsonify({"error": "Unauthorized"}), 403
        
    data = request.json
    posts = load_posts()
    new_post = {
        "id": str(uuid.uuid4())[:8],
        "title": data.get('title', 'Untitled'),
        "content": data.get('content', ''),
        "date": data.get('date', 'Today')
    }
    posts.append(new_post)
    save_posts(posts)
    return jsonify({"success": True, "post": new_post})

@app.route('/api/stats', methods=['GET'])
def stats():
    token = request.headers.get('Authorization')
    if token not in VALID_TOKENS:
        return jsonify({"error": "Unauthorized"}), 403
        
    posts = load_posts()
    total_words = sum(len(p['content'].split()) for p in posts)
    return jsonify({"total_posts": len(posts), "total_words": total_words})

@app.route('/api/reset', methods=['DELETE'])
def reset():
    token = request.headers.get('Authorization')
    if token not in VALID_TOKENS:
        return jsonify({"error": "Unauthorized"}), 403
        
    save_posts([]) # Delete all posts
    return jsonify({"success": True, "message": "All posts deleted."})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
