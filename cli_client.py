#!/usr/bin/env python3
"""
CLI client for Spotify Billboard Bridge API
"""
import requests
import webbrowser
import time
import sys
from datetime import datetime

class SpotifyBillboardCLI:
    def __init__(self, base_url="http://localhost:5000"):
        self.base_url = base_url
        self.session = requests.Session()
    
    def check_server(self):
        """Check if the API server is running"""
        try:
            response = self.session.get(f"{self.base_url}/")
            return response.status_code == 200
        except:
            return False
    
    def authenticate(self):
        """Handle Spotify authentication"""
        print("🎵 Starting Spotify authentication...")
        
        # Check current auth status
        try:
            response = self.session.get(f"{self.base_url}/api/status")
            if response.json().get('authenticated'):
                user = response.json().get('user', {})
                print(f"✅ Already authenticated as {user.get('display_name', 'User')}")
                return True
        except:
            pass
        
        print("🔐 Opening browser for Spotify authentication...")
        webbrowser.open(f"{self.base_url}/auth")
        
        # Wait for authentication
        print("⏳ Waiting for authentication... (check your browser)")
        for i in range(60):  # Wait up to 60 seconds
            time.sleep(1)
            try:
                response = self.session.get(f"{self.base_url}/api/status")
                if response.json().get('authenticated'):
                    user = response.json().get('user', {})
                    print(f"✅ Successfully authenticated as {user.get('display_name', 'User')}")
                    return True
            except:
                pass
            
            if i % 10 == 0:
                print(f"⏳ Still waiting... ({60-i}s remaining)")
        
        print("❌ Authentication timeout. Please try again.")
        return False
    
    def get_chart(self, date=None):
        """Get Billboard chart"""
        url = f"{self.base_url}/api/charts"
        params = {'date': date} if date else {}
        
        try:
            response = self.session.get(url, params=params)
            return response.json()
        except Exception as e:
            print(f"❌ Error fetching chart: {e}")
            return None
    
    def create_playlist(self, date=None, playlist_name=None, public=True):
        """Create Spotify playlist from Billboard chart"""
        print(f"🎵 Creating playlist for {date or 'current'} Billboard Hot 100...")
        
        url = f"{self.base_url}/api/create_playlist"
        data = {
            'date': date,
            'playlist_name': playlist_name,
            'public': public
        }
        
        try:
            response = self.session.post(url, json=data)
            result = response.json()
            
            if response.status_code == 200:
                stats = result['stats']
                playlist = result['playlist']
                
                print(f"✅ Successfully created playlist: {playlist['name']}")
                print(f"🔗 Playlist URL: {playlist['url']}")
                print(f"📊 Stats: {stats['found']}/{stats['total_songs']} tracks found")
                
                if result['missing_tracks']:
                    print(f"\n❌ Missing tracks ({len(result['missing_tracks'])}):")
                    for track in result['missing_tracks'][:10]:
                        print(f"   • {track['title']} - {track['artist']}")
                    if len(result['missing_tracks']) > 10:
                        print(f"   ... and {len(result['missing_tracks']) - 10} more")
                
                return True
            else:
                print(f"❌ Error: {result.get('error', 'Unknown error')}")
                return False
                
        except Exception as e:
            print(f"❌ Error creating playlist: {e}")
            return False
    
    def interactive_mode(self):
        """Interactive CLI mode"""
        print("🎵 Spotify Billboard Bridge CLI")
        print("=" * 40)
        
        if not self.check_server():
            print("❌ API server not running. Please start the Flask app first:")
            print("   python app.py")
            return
        
        if not self.authenticate():
            return
        
        while True:
            print("\n" + "=" * 40)
            print("Options:")
            print("1. Create playlist from current Billboard Hot 100")
            print("2. Create playlist from specific date")
            print("3. View Billboard chart")
            print("4. Exit")
            
            choice = input("\nEnter your choice (1-4): ").strip()
            
            if choice == '1':
                name = input("Playlist name (optional): ").strip() or None
                public = input("Make playlist public? (y/N): ").strip().lower() == 'y'
                self.create_playlist(playlist_name=name, public=public)
                
            elif choice == '2':
                date = input("Enter date (YYYY-MM-DD): ").strip()
                try:
                    datetime.strptime(date, '%Y-%m-%d')
                    name = input("Playlist name (optional): ").strip() or None
                    public = input("Make playlist public? (y/N): ").strip().lower() == 'y'
                    self.create_playlist(date=date, playlist_name=name, public=public)
                except ValueError:
                    print("❌ Invalid date format. Please use YYYY-MM-DD")
                    
            elif choice == '3':
                date = input("Enter date (YYYY-MM-DD) or press Enter for current: ").strip()
                if date:
                    try:
                        datetime.strptime(date, '%Y-%m-%d')
                    except ValueError:
                        print("❌ Invalid date format. Please use YYYY-MM-DD")
                        continue
                
                chart = self.get_chart(date if date else None)
                if chart:
                    print(f"\n🎵 Billboard Hot 100 - {chart['date']}")
                    print(f"📊 Total songs: {chart['total_songs']}")
                    print("\nTop 20:")
                    for song in chart['songs'][:20]:
                        print(f"  {song['position']:2d}. {song['title']} - {song['artist']}")
                    
                    if len(chart['songs']) > 20:
                        if input("\nShow all songs? (y/N): ").strip().lower() == 'y':
                            for song in chart['songs'][20:]:
                                print(f"  {song['position']:2d}. {song['title']} - {song['artist']}")
                
            elif choice == '4':
                print("👋 Goodbye!")
                break
                
            else:
                print("❌ Invalid choice. Please enter 1-4.")

def main():
    cli = SpotifyBillboardCLI()
    
    if len(sys.argv) > 1:
        # Command line arguments
        if sys.argv[1] == 'auth':
            cli.authenticate()
        elif sys.argv[1] == 'create':
            date = sys.argv[2] if len(sys.argv) > 2 else None
            if cli.authenticate():
                cli.create_playlist(date=date)
        elif sys.argv[1] == 'chart':
            date = sys.argv[2] if len(sys.argv) > 2 else None
            chart = cli.get_chart(date)
            if chart:
                for song in chart['songs']:
                    print(f"{song['position']:2d}. {song['title']} - {song['artist']}")
        else:
            print("Usage:")
            print("  python cli_client.py          # Interactive mode")
            print("  python cli_client.py auth     # Authenticate only")
            print("  python cli_client.py create [date]  # Create playlist")
            print("  python cli_client.py chart [date]   # View chart")
    else:
        # Interactive mode
        cli.interactive_mode()

if __name__ == "__main__":
    main()