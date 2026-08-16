import os
from flask import Flask, jsonify, request
from flask_cors import CORS
from ytmusicapi import YTMusic
import yt_dlp
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
    
    # 1. Try yt-dlp first (in case it isn't blocked)
    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'web']
                }
            }
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
            stream_url = info.get('url')
            if not stream_url and 'formats' in info:
                for f in info['formats']:
                    if f.get('acodec') != 'none' and f.get('vcodec') == 'none':
                        stream_url = f['url']
                        break
            if stream_url:
                stream_cache[video_id] = stream_url
                return jsonify({"url": stream_url})
    except Exception as e:
        print(f"yt-dlp failed for {video_id}: {e}")
    
    # 2. Fallback to Piped API (Bypasses YouTube cloud blocks)
    piped_instances = [
        "https://pipedapi.kavin.rocks",
        "https://pipedapi.adminforge.de",
        "https://api.piped.yt"
    ]
    
    for instance in piped_instances:
        try:
            res = requests.get(f"{instance}/streams/{video_id}", timeout=5)
            if res.status_code == 200:
                data = res.json()
                if data.get('audioStreams'):
                    best_audio = data['audioStreams'][0]
                    for stream in data['audioStreams']:
                        if stream.get('quality') == '256' or stream.get('quality', '0') > best_audio.get('quality', '0'):
                            best_audio = stream
                    stream_url = best_audio.get('url')
                    if stream_url:
                        stream_cache[video_id] = stream_url
                        return jsonify({"url": stream_url})
        except Exception as e:
            print(f"Piped instance {instance} failed: {e}")
            
    return jsonify({"error": "Could not extract audio URL from any source"}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
