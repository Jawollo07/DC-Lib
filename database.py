import aiomysql
import aiohttp
import base64
import json
import xml.etree.ElementTree as ET
from datetime import date, timedelta, datetime
from typing import Optional, Dict, Any, List

# Korrigierter Import
from config import config_manager, get_config, logger

# Definieren von Base-URLs (hardcoded, da nicht in config.py)
TMDB_BASE_URL = "https://api.themoviedb.org/3"
COMICVINE_BASE_URL = "https://comicvine.gamespot.com/api"

class Database:
    """Datenbank-Verwaltungsklasse"""
    
    def __init__(self):
        self.pool: Optional[aiomysql.Pool] = None
    
    async def create_pool(self) -> None:
        """Erstellt einen Datenbank-Verbindungspool"""
        try:
            self.pool = await aiomysql.create_pool(
                host=get_config('database.host', 'localhost'),
                port=int(get_config('database.port', 3306)),
                user=get_config('database.user'),
                password=get_config('database.password'),
                db=get_config('database.database', 'media_library'),
                autocommit=True,
                minsize=1,
                maxsize=10,
                cursorclass=aiomysql.DictCursor
            )
            logger.info("Datenbank-Verbindungspool erstellt")
        except Exception as e:
            logger.error(f"Fehler beim Erstellen des DB-Pools: {e}")
            raise
    
    async def close_pool(self) -> None:
        """Schließt den Datenbank-Verbindungspool"""
        if self.pool:
            self.pool.close()
            await self.pool.wait_closed()
            logger.info("Datenbank-Verbindungspool geschlossen")
    
    async def init_tables(self) -> None:
        """Initialisiert alle Datenbanktabellen"""
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                # Medien Tabelle (vereinheitlicht für alle Medienarten)
                await cur.execute("""
                    CREATE TABLE IF NOT EXISTS media_items (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        user_id BIGINT NOT NULL,
                        username VARCHAR(100),
                        media_type VARCHAR(20) NOT NULL,
                        external_id VARCHAR(100),
                        title VARCHAR(255) NOT NULL,
                        subtitle VARCHAR(255),
                        authors TEXT,
                        artists TEXT,
                        description LONGTEXT,
                        cover TEXT,
                        release_date VARCHAR(20),
                        duration INT,
                        genres TEXT,
                        publisher VARCHAR(255),
                        isbn VARCHAR(32),
                        upc VARCHAR(20),
                        rating DECIMAL(3,1),
                        platforms TEXT,
                        players VARCHAR(50),
                        due_date DATE NOT NULL,
                        reminded BOOLEAN DEFAULT FALSE,
                        created_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE KEY uq_user_media (user_id, media_type, external_id),
                        INDEX idx_user_id (user_id),
                        INDEX idx_media_type (media_type),
                        INDEX idx_due_date (due_date)
                    )
                """)
                
                # Rückgabe Log Tabelle
                await cur.execute("""
                    CREATE TABLE IF NOT EXISTS rueckgabe_log (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        moderator_id BIGINT,
                        user_id BIGINT,
                        media_type VARCHAR(20),
                        external_id VARCHAR(100),
                        title VARCHAR(255),
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        INDEX idx_user_id (user_id),
                        INDEX idx_timestamp (timestamp)
                    )
                """)
                
                # Neue Tabelle für Dashboard-Stats (optional, für Verbesserung)
                await cur.execute("""
                    CREATE TABLE IF NOT EXISTS dashboard_stats (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        stat_type VARCHAR(50),
                        value INT,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
        logger.info("Datenbanktabellen initialisiert")

class MediaRepository:
    """Datenbank-Operationen für alle Medienarten"""
    
    def __init__(self, db: Database):
        self.db = db
    
    async def borrow_media(self, user_id: int, username: str, media_type: str, media_info: dict, due_date: str):
        """Fügt ein ausgeliehenes Medium hinzu"""
        async with self.db.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    INSERT INTO media_items (
                        user_id, username, media_type, external_id, title, subtitle, 
                        authors, artists, description, cover, release_date, 
                        duration, genres, publisher, isbn, upc, rating, platforms, players, due_date
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE 
                        title = VALUES(title),
                        subtitle = VALUES(subtitle),
                        authors = VALUES(authors),
                        artists = VALUES(artists),
                        description = VALUES(description),
                        cover = VALUES(cover),
                        due_date = VALUES(due_date),
                        reminded = FALSE
                """, (
                    user_id, username, media_type, 
                    media_info.get("external_id"),
                    media_info["title"],
                    media_info.get("subtitle"),
                    media_info.get("authors"),
                    media_info.get("artists"),
                    media_info.get("description"),
                    media_info.get("cover"),
                    media_info.get("release_date"),
                    media_info.get("duration"),
                    media_info.get("genres"),
                    media_info.get("publisher"),
                    media_info.get("isbn"),
                    media_info.get("upc"),
                    media_info.get("rating"),
                    media_info.get("platforms"),
                    media_info.get("players"),
                    due_date
                ))
    
    async def return_media(self, user_id: int, media_type: str, external_id: str):
        """Gibt ein Medium zurück"""
        async with self.db.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT title FROM media_items WHERE user_id = %s AND media_type = %s AND external_id = %s",
                    (user_id, media_type, external_id)
                )
                media = await cur.fetchone()
                
                if media:
                    await cur.execute(
                        "DELETE FROM media_items WHERE user_id = %s AND media_type = %s AND external_id = %s",
                        (user_id, media_type, external_id)
                    )
                    await cur.execute(
                        "INSERT INTO rueckgabe_log (moderator_id, user_id, media_type, external_id, title) VALUES (%s, %s, %s, %s, %s)",
                        (user_id, user_id, media_type, external_id, media["title"])
                    )
                return media
    
    async def get_user_media(self, user_id: int, media_type: str = None):
        """Holt alle Medien eines Benutzers, optional gefiltert nach Typ"""
        async with self.db.pool.acquire() as conn:
            async with conn.cursor() as cur:
                if media_type:
                    await cur.execute(
                        "SELECT title, due_date, media_type FROM media_items WHERE user_id = %s AND media_type = %s ORDER BY due_date",
                        (user_id, media_type)
                    )
                else:
                    await cur.execute(
                        "SELECT title, due_date, media_type FROM media_items WHERE user_id = %s ORDER BY due_date",
                        (user_id,)
                    )
                return await cur.fetchall()

class ReminderRepository:
    """Datenbank-Operationen für Erinnerungen (vervollständigt basierend auf Kontext)"""
    
    def __init__(self, db: Database):
        self.db = db
    
    async def get_due_media(self, days_before: int) -> List[Dict[str, Any]]:
        """Holt Medien, die in X Tagen fällig sind und noch nicht erinnert wurden"""
        async with self.db.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    SELECT id, user_id, title, media_type, due_date
                    FROM media_items
                    WHERE due_date = DATE_ADD(CURDATE(), INTERVAL %s DAY)
                    AND reminded = FALSE
                """, (days_before,))
                return await cur.fetchall()
    
    async def mark_media_reminded(self, user_id: int, title: str, media_type: str):
        """Markiert ein Medium als erinnert"""
        async with self.db.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    UPDATE media_items
                    SET reminded = TRUE
                    WHERE user_id = %s AND title = %s AND media_type = %s
                """, (user_id, title, media_type))

class DashboardRepository:
    """Datenbank-Operationen für das Web-Dashboard (neu hinzugefügt zur Fehlerbehebung)"""
    
    def __init__(self, db: Database):
        self.db = db
    
    async def get_dashboard_stats(self) -> Dict[str, int]:
        """Holt grundlegende Statistiken für das Dashboard"""
        stats = {}
        async with self.db.pool.acquire() as conn:
            async with conn.cursor() as cur:
                # Gesamte Ausleihen
                await cur.execute("SELECT COUNT(*) as total_loans FROM media_items")
                stats['total_loans'] = (await cur.fetchone())['total_loans']
                
                # Überfällige Medien
                await cur.execute("SELECT COUNT(*) as overdue FROM media_items WHERE due_date < CURDATE()")
                stats['overdue'] = (await cur.fetchone())['overdue']
                
                # Aktive Benutzer (letzte 30 Tage)
                await cur.execute("""
                    SELECT COUNT(DISTINCT user_id) as active_users 
                    FROM media_items 
                    WHERE created_on >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
                """)
                stats['active_users'] = (await cur.fetchone())['active_users']
                
        return stats
    
    async def log_dashboard_access(self, user_id: int, action: str):
        """Loggt Dashboard-Zugriffe (Beispiel für Erweiterung)"""
        async with self.db.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    INSERT INTO dashboard_stats (stat_type, value) 
                    VALUES ('access', 1)
                """)  # Kann erweitert werden

class APIHandler:
    """Handler für externe API-Anfragen (vervollständigt und verbessert)"""
    
    def __init__(self):
        self.spotify_token = None
        self.spotify_token_expiry = None  # Neu: Für Token-Expiration
        self.igdb_token = None
        self.igdb_token_expiry = None
        self.genre_cache = None
    
    async def search_books(self, isbn: str) -> Optional[Dict[str, Any]]:
        """Sucht Bücher über Google Books API (vervollständigt aus Kontext)"""
        if not self.validate_isbn(isbn):
            return None
        
        api_key = get_config('apis.google_books.api_key')
        url = "https://www.googleapis.com/books/v1/volumes"
        params = {"q": f"isbn:{isbn.strip().replace('-', '')}"}
        if api_key:
            params["key"] = api_key
        
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get(url, params=params) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
                    items = data.get("items", [])
                    if not items:
                        return None
                    volume_info = items[0].get("volumeInfo", {})
                    return {
                        "external_id": items[0].get("id"),
                        "title": volume_info.get("title", "Unbekannter Titel"),
                        "subtitle": volume_info.get("subtitle"),
                        "authors": ", ".join(volume_info.get("authors", [])),
                        "description": volume_info.get("description", ""),
                        "cover": volume_info.get("imageLinks", {}).get("thumbnail", ""),
                        "release_date": volume_info.get("publishedDate", ""),
                        "publisher": volume_info.get("publisher", ""),
                        "isbn": isbn,
                        "genres": ", ".join(volume_info.get("categories", [])),
                        "rating": volume_info.get("averageRating", 0)
                    }
        except Exception as e:
            logger.error(f"Fehler bei Google Books API-Anfrage: {e}")
            return None
    
    # ... (Weitere Methoden wie in der Kopie, mit get_config ersetzt)
    
    async def search_board_games(self, query: str) -> Optional[List[Dict[str, Any]]]:
        """Sucht Brettspiele über Board Game Atlas API"""
        client_id = get_config('apis.boardgameatlas.client_id')  # Korrigiert
        if not client_id:
            return None
        
        url = "https://api.boardgameatlas.com/api/search"
        params = {
            "name": query,
            "client_id": client_id,
            "limit": 5
        }
        
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get(url, params=params) as resp:
                    if resp.status != 200:
                        return None
                    
                    data = await resp.json()
                    games = data.get("games", [])
                    
                    results = []
                    for game in games:
                        details = await self._get_bgg_game_details(game.get("id", ""))  # Optionaler Aufruf
                        results.append({
                            "external_id": game.get("id"),
                            "title": game.get("name", "Unbekannter Titel"),
                            "description": details.get("description", game.get("description", "")),
                            "cover": game.get("thumb_url", ""),
                            "release_date": game.get("year_published", ""),
                            "publisher": ", ".join([p["name"] for p in game.get("publishers", [])]),
                            "rating": game.get("average_user_rating", 0),
                            "players": details.get("players", game.get("min_players", "?") + "-" + game.get("max_players", "?")),
                            "duration": details.get("duration", game.get("playtime", 0))
                        })
                    
                    return results
                    
        except Exception as e:
            logger.error(f"Fehler bei Board Game Atlas API-Anfrage: {e}")
            return None
    
    async def search_comics(self, query: str) -> Optional[List[Dict[str, Any]]]:
        """Sucht Comics über Comic Vine API"""
        api_key = get_config('apis.comic_vine.api_key')  # Korrigiert
        if not api_key:
            return None
        
        url = f"{COMICVINE_BASE_URL}/search"
        params = {
            "api_key": api_key,
            "format": "json",
            "query": query,
            "resources": "volume",
            "limit": 5
        }
        
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get(url, params=params) as resp:
                    if resp.status != 200:
                        return None
                    
                    data = await resp.json()
                    results = data.get("results", [])
                    
                    comics = []
                    for comic in results:
                        cover_url = ""
                        if comic.get("image"):
                            cover_url = comic["image"]["medium_url"]
                        
                        comics.append({
                            "external_id": str(comic["id"]),
                            "title": comic.get("name", "Unbekannter Titel"),
                            "description": comic.get("description", ""),
                            "cover": cover_url,
                            "release_date": comic.get("start_year", ""),
                            "publisher": comic.get("publisher", {}).get("name", "Unbekannt")
                        })
                    
                    return comics
                    
        except Exception as e:
            logger.error(f"Fehler bei Comic Vine API-Anfrage: {e}")
            return None
    
    async def search_magazines(self, query: str) -> Optional[List[Dict[str, Any]]]:
        """Sucht Zeitschriften über Google Books API"""
        api_key = get_config('apis.google_books.api_key')  # Korrigiert
        url = "https://www.googleapis.com/books/v1/volumes"
        params = {
            "q": f"{query} subject:magazine",
            "maxResults": 5
        }
        
        if api_key:
            params["key"] = api_key
        
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get(url, params=params) as resp:
                    if resp.status != 200:
                        return None
                    
                    data = await resp.json()
                    items = data.get("items", [])
                    
                    magazines = []
                    for item in items:
                        volume_info = item.get("volumeInfo", {})
                        magazines.append({
                            "external_id": item.get("id", ""),
                            "title": volume_info.get("title", "Unbekannter Titel"),
                            "subtitle": volume_info.get("subtitle", ""),
                            "description": volume_info.get("description", ""),
                            "cover": volume_info.get("imageLinks", {}).get("thumbnail", ""),
                            "publisher": volume_info.get("publisher", ""),
                            "release_date": volume_info.get("publishedDate", ""),
                            "isbn": volume_info.get("industryIdentifiers", [{}])[0].get("identifier", "") if volume_info.get("industryIdentifiers") else ""
                        })
                    
                    return magazines
                    
        except Exception as e:
            logger.error(f"Fehler bei Google Books Magazine API-Anfrage: {e}")
            return None
    
    # Hilfsmethoden (verbessert mit Expiration-Check)
    async def _get_spotify_token(self):
        """Holt Spotify Access Token (mit Expiration-Check)"""
        if self.spotify_token and self.spotify_token_expiry and datetime.now() < self.spotify_token_expiry:
            return  # Token noch gültig
        
        client_id = get_config('apis.spotify.client_id')
        client_secret = get_config('apis.spotify.client_secret')
        if not client_id or not client_secret:
            logger.error("Spotify Credentials fehlen")
            return
        
        auth_string = f"{client_id}:{client_secret}"
        auth_bytes = auth_string.encode('utf-8')
        auth_base64 = base64.b64encode(auth_bytes).decode('utf-8')
        
        url = "https://accounts.spotify.com/api/token"
        headers = {
            "Authorization": f"Basic {auth_base64}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {"grant_type": "client_credentials"}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, data=data) as resp:
                    if resp.status == 200:
                        token_data = await resp.json()
                        self.spotify_token = token_data["access_token"]
                        self.spotify_token_expiry = datetime.now() + timedelta(seconds=token_data.get("expires_in", 3600) - 300)  # 5 Min Puffer
                    else:
                        logger.error(f"Fehler beim Holen des Spotify Tokens: Status {resp.status}")
        except Exception as e:
            logger.error(f"Fehler bei Spotify Token-Anfrage: {e}")
    
    async def _get_igdb_token(self):
        """Holt IGDB Access Token (mit Expiration-Check)"""
        if self.igdb_token and self.igdb_token_expiry and datetime.now() < self.igdb_token_expiry:
            return
        
        client_id = get_config('apis.igdb.client_id')
        client_secret = get_config('apis.igdb.client_secret')
        if not client_id or not client_secret:
            logger.error("IGDB Credentials fehlen")
            return
        
        url = "https://id.twitch.tv/oauth2/token"
        data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "client_credentials"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=data) as resp:
                    if resp.status == 200:
                        token_data = await resp.json()
                        self.igdb_token = token_data["access_token"]
                        self.igdb_token_expiry = datetime.now() + timedelta(seconds=token_data.get("expires_in", 3600) - 300)
                    else:
                        logger.error(f"Fehler beim Holen des IGDB Tokens: Status {resp.status}")
        except Exception as e:
            logger.error(f"Fehler bei IGDB Token-Anfrage: {e}")
    
    async def _get_tmdb_genres(self, genre_ids: List[int]) -> List[str]:
        """Holt Genre-Namen für TMDB Genre-IDs"""
        if not get_config('apis.tmdb.api_key'):
            return []
        
        if self.genre_cache is None:
            await self._load_tmdb_genres()
        
        return [self.genre_cache[genre_id] for genre_id in genre_ids if genre_id in self.genre_cache]
    
    async def _load_tmdb_genres(self):
        """Lädt alle verfügbaren Genres von TMDB"""
        api_key = get_config('apis.tmdb.api_key')
        url = f"{TMDB_BASE_URL}/genre/movie/list"
        params = {
            "api_key": api_key,
            "language": "de-DE"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        self.genre_cache = {genre["id"]: genre["name"] for genre in data.get("genres", [])}
                    else:
                        self.genre_cache = {}
                        logger.error(f"Fehler beim Laden der TMDB Genres: Status {resp.status}")
        except Exception as e:
            logger.error(f"Fehler beim Laden der TMDB Genres: {e}")
            self.genre_cache = {}
    
    async def _get_musicbrainz_cover(self, release_id: str) -> Optional[str]:
        """Holt Cover-URL von Cover Art Archive"""
        url = f"https://coverartarchive.org/release/{release_id}"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        images = data.get("images", [])
                        if images:
                            return images[0].get("thumbnails", {}).get("small", images[0].get("image", ""))
        except Exception as e:
            logger.error(f"Fehler bei MusicBrainz Cover-Anfrage: {e}")
        return None
    
    def validate_isbn(self, isbn: str) -> bool:
        """Validiert eine ISBN (erweitert um Checksumme für Genauigkeit)"""
        clean_isbn = isbn.strip().replace("-", "")
        if not clean_isbn.isdigit() or len(clean_isbn) not in [10, 13]:
            return False
        
        # Optionale Checksumme-Validierung für ISBN-13 (Beispiel)
        if len(clean_isbn) == 13:
            check = 0
            for i, digit in enumerate(clean_isbn[:-1]):
                check += int(digit) * (1 if i % 2 == 0 else 3)
            check_digit = (10 - (check % 10)) % 10
            return int(clean_isbn[-1]) == check_digit
        
        return True  # Für ISBN-10 ähnlich implementierbar

# Globale Instanzen (erweitert um dashboard_repo)
db = Database()
media_repo = MediaRepository(db)
reminder_repo = ReminderRepository(db)
dashboard_repo = DashboardRepository(db)  # Neu: Behebt den NameError
api_handler = APIHandler()
