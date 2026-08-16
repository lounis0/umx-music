import os
from flask import Flask, jsonify, request
from flask_cors import CORS
from ytmusicapi import YTMusic
import yt_dlp

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
    
    # Updated to use 'tv' and 'ios' clients to bypass YouTube's cloud bot protection
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['tv', 'ios', 'android', 'web']
            }
        }
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
            
            # Safely extract the stream URL from the formats list
            stream_url = info.get('url')
            if not stream_url and 'formats' in info:
                best_audio = None
                for f in info['formats']:
                    if f.get('acodec') != 'none' and f.get('vcodec') == 'none':
                        if best_audio is None or f.get('abr', 0) > best_audio.get('abr', 0):
                            best_audio = f
                if best_audio:
                    stream_url = best_audio['url']
                elif info['formats']:
                    stream_url = info['formats'][-1]['url']
            
            if stream_url:
                stream_cache[video_id] = stream_url
                return jsonify({"url": stream_url})
            else:
                return jsonify({"error": "Could not extract audio URL"}), 500
                    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
