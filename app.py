from flask import Flask, request, jsonify, redirect, session, url_for
from flask_cors import CORS
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import requests
from bs4 import BeautifulSoup
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
import time
import re

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'your-secret-key-here')
CORS(app)

# Spotify Configuration
SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')
SPOTIFY_REDIRECT_URI = os.getenv('SPOTIFY_REDIRECT_URI', 'http://localhost:5000/callback')

class BillboardScraper:
    def __init__(self):
        self.base_url = 'https://www.billboard.com/charts/hot-100'
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
    
    def get_chart(self, date=None):
        """Scrape Billboard Hot 100 for given date"""
        try:
            url = f"{self.base_url}/{date}" if date else self.base_url
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            songs = []
            
            # Try multiple selectors for different Billboard layouts
            selectors = [
                'li ul li h3',  # Old layout
                'h3.c-title',   # New layout
                '.chart-list__item h3',  # Alternative layout
                '.o-chart-results-list__item h3'  # Another layout
            ]
            
            song_elements = []
            for selector in selectors:
                song_elements = soup.select(selector)
                if song_elements:
                    break
            
            if not song_elements:
                # Fallback: look for any h3 elements
                song_elements = soup.find_all('h3')
            
            for i, element in enumerate(song_elements[:100]):  # Limit to 100
                title = element.get_text().strip()
                if title and len(title) > 1:  # Basic validation
                    # Try to find artist info (usually in nearby elements)
                    artist = "Unknown Artist"
                    parent = element.parent
                    if parent:
                        # Look for artist in sibling elements
                        siblings = parent.find_all(['p', 'span', 'div'])
                        for sibling in siblings:
                            text = sibling.get_text().strip()
                            if text and text != title and len(text) < 100:
                                artist = text
                                break
                    
                    songs.append({
                        'position': i + 1,
                        'title': title,
                        'artist': artist
                    })
            
            return songs[:100]  # Ensure we return max 100
            
        except Exception as e:
            print(f"Error scraping Billboard: {e}")
            return []

class SpotifyService:
    def __init__(self):
        self.sp = None
    
    def get_auth_url(self):
        """Get Spotify authorization URL"""
        sp_oauth = SpotifyOAuth(
            client_id=SPOTIFY_CLIENT_ID,
            client_secret=SPOTIFY_CLIENT_SECRET,
            redirect_uri=SPOTIFY_REDIRECT_URI,
            scope='playlist-modify-public playlist-modify-private playlist-read-private',
            show_dialog=True
        )
        return sp_oauth.get_authorize_url()
    
    def authenticate(self, code):
        """Complete Spotify authentication"""
        try:
            sp_oauth = SpotifyOAuth(
                client_id=SPOTIFY_CLIENT_ID,
                client_secret=SPOTIFY_CLIENT_SECRET,
                redirect_uri=SPOTIFY_REDIRECT_URI,
                scope='playlist-modify-public playlist-modify-private playlist-read-private'
            )
            token_info = sp_oauth.get_access_token(code)
            self.sp = spotipy.Spotify(auth=token_info['access_token'])
            return token_info
        except Exception as e:
            print(f"Authentication error: {e}")
            return None
    
    def search_track(self, title, artist):
        """Search for track on Spotify"""
        if not self.sp:
            return None
        
        try:
            # Clean the search terms
            title = re.sub(r'[^\w\s]', '', title)
            artist = re.sub(r'[^\w\s]', '', artist)
            
            # Multiple search strategies
            queries = [
                f'track:"{title}" artist:"{artist}"',
                f'"{title}" "{artist}"',
                f'{title} {artist}',
                f'track:{title} artist:{artist}'
            ]
            
            for query in queries:
                results = self.sp.search(q=query, type='track', limit=5)
                if results['tracks']['items']:
                    # Return the first result
                    track = results['tracks']['items'][0]
                    return {
                        'uri': track['uri'],
                        'name': track['name'],
                        'artist': track['artists'][0]['name'],
                        'popularity': track['popularity']
                    }
            
            return None
            
        except Exception as e:
            print(f"Error searching for {title} by {artist}: {e}")
            return None
    
    def create_playlist(self, name, description="", public=True):
        """Create Spotify playlist"""
        if not self.sp:
            return None
        
        try:
            user_id = self.sp.current_user()['id']
            playlist = self.sp.user_playlist_create(
                user=user_id,
                name=name,
                description=description,
                public=public
            )
            return playlist
        except Exception as e:
            print(f"Error creating playlist: {e}")
            return None
    
    def add_tracks_to_playlist(self, playlist_id, track_uris):
        """Add tracks to playlist"""
        if not self.sp:
            return False
        
        try:
            # Add tracks in chunks of 100
            chunk_size = 100
            for i in range(0, len(track_uris), chunk_size):
                chunk = track_uris[i:i + chunk_size]
                self.sp.playlist_add_items(playlist_id, chunk)
            return True
        except Exception as e:
            print(f"Error adding tracks: {e}")
            return False

# Initialize services
billboard_scraper = BillboardScraper()
spotify_service = SpotifyService()

@app.route('/')
def index():
    return jsonify({
        "message": "Spotify Billboard Bridge API",
        "endpoints": {
            "auth": "/auth",
            "callback": "/callback",
            "charts": "/api/charts",
            "create_playlist": "/api/create_playlist",
            "status": "/api/status"
        }
    })

@app.route('/auth')
def auth():
    """Initiate Spotify authentication"""
    auth_url = spotify_service.get_auth_url()
    return redirect(auth_url)

@app.route('/callback')
def callback():
    """Handle Spotify authentication callback"""
    code = request.args.get('code')
    if code:
        token_info = spotify_service.authenticate(code)
        if token_info:
            session['token_info'] = token_info
            return jsonify({"status": "success", "message": "Authentication successful"})
    
    return jsonify({"status": "error", "message": "Authentication failed"}), 400

@app.route('/api/charts')
def get_charts():
    """Get Billboard chart for specific date"""
    date = request.args.get('date')  # Format: YYYY-MM-DD
    
    if date:
        # Validate date format
        try:
            datetime.strptime(date, '%Y-%m-%d')
        except ValueError:
            return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400
    
    songs = billboard_scraper.get_chart(date)
    
    if not songs:
        return jsonify({"error": "Failed to fetch chart data"}), 500
    
    return jsonify({
        "date": date or "current",
        "total_songs": len(songs),
        "songs": songs
    })

@app.route('/api/create_playlist', methods=['POST'])
def create_playlist():
    """Create Spotify playlist from Billboard chart"""
    if 'token_info' not in session:
        return jsonify({"error": "Not authenticated with Spotify"}), 401
    
    data = request.get_json()
    date = data.get('date')
    playlist_name = data.get('playlist_name')
    public = data.get('public', True)
    
    # Get Billboard chart
    songs = billboard_scraper.get_chart(date)
    if not songs:
        return jsonify({"error": "Failed to fetch Billboard chart"}), 500
    
    # Create playlist name if not provided
    if not playlist_name:
        chart_date = date if date else datetime.now().strftime("%Y-%m-%d")
        playlist_name = f"Billboard Hot 100 - {chart_date}"
    
    # Search for tracks on Spotify
    found_tracks = []
    missing_tracks = []
    track_uris = []
    
    for song in songs:
        track_info = spotify_service.search_track(song['title'], song['artist'])
        if track_info:
            track_uris.append(track_info['uri'])
            found_tracks.append({
                **song,
                'spotify_name': track_info['name'],
                'spotify_artist': track_info['artist']
            })
        else:
            missing_tracks.append(song)
        
        # Small delay to avoid rate limiting
        time.sleep(0.1)
    
    # Create Spotify playlist
    description = f"Billboard Hot 100 chart from {date or 'current week'}. Created with Spotify Billboard Bridge."
    playlist = spotify_service.create_playlist(playlist_name, description, public)
    
    if not playlist:
        return jsonify({"error": "Failed to create Spotify playlist"}), 500
    
    # Add tracks to playlist
    success = False
    if track_uris:
        success = spotify_service.add_tracks_to_playlist(playlist['id'], track_uris)
    
    return jsonify({
        "status": "success" if success else "partial_success",
        "playlist": {
            "id": playlist['id'],
            "name": playlist['name'],
            "url": playlist['external_urls']['spotify']
        },
        "stats": {
            "total_songs": len(songs),
            "found": len(found_tracks),
            "missing": len(missing_tracks)
        },
        "found_tracks": found_tracks,
        "missing_tracks": missing_tracks
    })

@app.route('/api/status')
def status():
    """Check authentication status"""
    authenticated = 'token_info' in session
    user_info = None
    
    if authenticated and spotify_service.sp:
        try:
            user_info = spotify_service.sp.current_user()
        except:
            authenticated = False
    
    return jsonify({
        "authenticated": authenticated,
        "user": user_info
    })

@app.route('/api/search_track')
def search_track():
    """Search for a specific track"""
    if 'token_info' not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    title = request.args.get('title')
    artist = request.args.get('artist')
    
    if not title or not artist:
        return jsonify({"error": "Title and artist required"}), 400
    
    track_info = spotify_service.search_track(title, artist)
    
    if track_info:
        return jsonify({"status": "found", "track": track_info})
    else:
        return jsonify({"status": "not_found"})

if __name__ == '__main__':
    print("Starting Spotify Billboard Bridge API...")
    print("Make sure to set your environment variables:")
    print("- SPOTIFY_CLIENT_ID")
    print("- SPOTIFY_CLIENT_SECRET")
    print("- SPOTIFY_REDIRECT_URI (optional, defaults to http://localhost:5000/callback)")
    print("- FLASK_SECRET_KEY (optional)")
    
    app.run(debug=True, host='0.0.0.0', port=5000)