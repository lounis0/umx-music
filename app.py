import os
from flask import Flask, jsonify, request
from flask_cors import CORS
from ytmusicapi import YTMusic
import requests

app = Flask(__name__)
CORS(app)
ytmusic = YTMusic()
stream_cache = {}

@app.route('/')
def home():
    return "UMX Backend is running!"

@app.route('/api/search')
def search():
    query = request.args.get('q')
    if not query: return jsonify([])
    results = ytmusic.search(query, filter="songs", limit=20)
    songs = []
    for item in results:
        if item.get('videoId'):
            artists = ', '.join([a['name'] for a in item.get('artists', [])])
            thumbs = item.get('thumbnails', [])
            cover = thumbs[-1]['url'] if thumbs else ''
            songs.append({
                "id": item['videoId'],
                "title": item.get('title', 'Unknown'),
                "artist": artists,
                "cover": cover
            })
    return jsonify(songs)

@app.route('/api/stream/<video_id>')
def get_stream(video_id):
    if video_id in stream_cache:
        return jsonify({"url": stream_cache[video_id]})
    
    # Use Cobalt API to bypass YouTube's copyright and bot blocks
    cobalt_instances = [
        "https://co.wuk.sh/api/json",
        "https://cobalt-api.kwiatekmiki.com/api/json",
        "https://api.cobalt.tools/api/json"
    ]
    
    payload = {
        "url": f"https://youtu.be/{video_id}",
        "isAudioOnly": True,
        "aFormat": "mp3"
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    for instance in cobalt_instances:
        try:
            res = requests.post(instance, json=payload, headers=headers, timeout=5)
            if res.status_code == 200:
                data = res.json()
                if data.get("status") == "stream" or data.get("status") == "redirect":
                    stream_url = data.get("url")
                    if stream_url:
                        stream_cache[video_id] = stream_url
                        return jsonify({"url": stream_url})
        except Exception as e:
            print(f"Cobalt instance {instance} failed: {e}")
            
    return jsonify({"error": "All sources blocked by YouTube"}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
