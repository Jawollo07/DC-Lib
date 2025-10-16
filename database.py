import aiomysql
import aiohttp
import base64
import json
import xml.etree.ElementTree as ET
from datetime import date, timedelta, datetime
from typing import Optional, Dict, Any, List
from functools import lru_cache

# Korrigierter Import
from config import config_manager, get_config, logger

# Definieren von Base-URLs
TMDB_BASE_URL = "https://api.themoviedb.org/3"
COMICVINE_BASE_URL = "https://comicvine.gamespot.com/api"

class Database:
    """Datenbank-Verwaltungsklasse für Medienverwaltung"""
    
    def __init__(self):
        self.pool: Optional[aiomysql.Pool] = None
    
    async def create_pool(self) -> None:
        """Erstellt einen Datenbank-Verbindungspool mit konfigurierbaren Parametern"""
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
            logger.info("Datenbank-Verbindungspool erfolgreich erstellt")
        except Exception as e:
            logger.error(f"Fehler beim Erstellen des DB-Pools: {e}")
            raise
    
    async def close_pool(self) -> None:
        """Schließt den Datenbank-Verbindungspool sicher"""
        if self.pool:
            self.pool.close()
            await self.pool.wait_closed()
            logger.info("Datenbank-Verbindungspool geschlossen")
    
    async def init_tables(self) -> None:
        """Initialisiert alle Datenbanktabellen mit optimierten Indizes"""
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                # Medien Tabelle
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
                
                # Dashboard-Statistiken Tabelle
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
    """Datenbank-Operationen für Medienarten"""
    
    def __init__(self, db: Database):
        self.db = db
    
    async def borrow_media(self, user_id: int, username: str, media_type: str, media_info: dict, due_date: str):
        """Fügt ein ausgeliehenes Medium hinzu oder aktualisiert es"""
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
                logger.info(f"Medium ausgeliehen: {media_type} - {media_info['title']} für User {user_id}")
    
    async def return_media(self, user_id: int, media_type: str, external_id: str):
        """Gibt ein Medium zurück und loggt die Rückgabe"""
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
                    logger.info(f"Medium zurückgegeben: {media_type} - {media['title']} für User {user_id}")
                else:
                    logger.warning(f"Medium nicht gefunden: {media_type} - {external_id} für User {user_id}")
    
    async def get_user_media(self, user_id: int) -> List[Dict[str, Any]]:
        """Holt alle ausgeliehenen Medien eines Users"""
        async with self.db.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT * FROM media_items WHERE user_id = %s ORDER BY due_date ASC",
                    (user_id,)
                )
                return await cur.fetchall()
    
    async def get_overdue_media(self) -> List[Dict[str, Any]]:
        """Holt alle überfälligen Medien"""
        async with self.db.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT * FROM media_items WHERE due_date < CURDATE() ORDER BY due_date ASC"
                )
                return await cur.fetchall()
    
    async def get_due_soon_media(self, days: int = 3) -> List[Dict[str, Any]]:
        """Holt Medien, die bald fällig sind"""
        async with self.db.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT * FROM media_items WHERE due_date BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL %s DAY) AND reminded = FALSE",
                    (days,)
                )
                return await cur.fetchall()
    
    async def mark_reminded(self, item_id: int):
        """Markiert ein Item als erinnert"""
        async with self.db.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "UPDATE media_items SET reminded = TRUE WHERE id = %s",
                    (item_id,)
                )

class ReminderRepository:
    """Datenbank-Operationen für Erinnerungen"""
    
    def __init__(self, db: Database):
        self.db = db
    
    async def get_due_reminders(self) -> List[Dict[str, Any]]:
        """Holt fällige Erinnerungen basierend auf Konfiguration"""
        remind_days = get_config('media_settings.remind_days_before', 1)
        async with self.db.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    SELECT * FROM media_items 
                    WHERE DATE(due_date) = DATE_ADD(CURDATE(), INTERVAL %s DAY)
                    AND reminded = FALSE
                """, (remind_days,))
                return await cur.fetchall()
    
    async def mark_as_reminded(self, item_id: int):
        """Markiert ein Medium als erinnert"""
        async with self.db.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "UPDATE media_items SET reminded = TRUE WHERE id = %s",
                    (item_id,)
                )

class DashboardRepository:
    """Datenbank-Operationen für Dashboard-Statistiken"""
    
    def __init__(self, db: Database):
        self.db = db
    
    async def get_total_loans(self) -> int:
        """Holt die Gesamtzahl der aktuellen Ausleihen"""
        async with self.db.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT COUNT(*) as count FROM media_items")
                result = await cur.fetchone()
                return result['count']
    
    async def get_overdue_count(self) -> int:
        """Holt die Anzahl der überfälligen Medien"""
        async with self.db.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT COUNT(*) as count FROM media_items WHERE due_date < CURDATE()")
                result = await cur.fetchone()
                return result['count']
    
    async def get_media_stats(self) -> Dict[str, int]:
        """Holt Statistiken pro Medientyp"""
        async with self.db.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT media_type, COUNT(*) as count FROM media_items GROUP BY media_type")
                results = await cur.fetchall()
                return {row['media_type']: row['count'] for row in results}

class APIHandler:
    """Handler für externe API-Anfragen mit Caching"""
    
    def __init__(self):
        self.spotify_token: Optional[str] = None
        self.spotify_token_expiry: Optional[datetime] = None
        self.igdb_token: Optional[str] = None
        self.igdb_token_expiry: Optional[datetime] = None
        self.genre_cache: Optional[Dict[int, str]] = None
    
    @lru_cache(maxsize=1000)
    async def search_books(self, query: str) -> Optional[List[Dict[str, Any]]]:
        """Sucht Bücher über Google Books API mit Caching"""
        if not get_config('apis.google_books.enabled', True):
            return None
        
        url = "https://www.googleapis.com/books/v1/volumes"
        params = {
            "q": query,
            "maxResults": 5
        }
        
        api_key = get_config('apis.google_books.api_key')
        if api_key:
            params["key"] = api_key
        
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get(url, params=params) as resp:
                    if resp.status != 200:
                        logger.warning(f"Google Books API Status: {resp.status}")
                        return None
                    
                    data = await resp.json()
                    items = data.get("items", [])
                    
                    books = []
                    for item in items:
                        volume_info = item.get("volumeInfo", {})
                        authors = ", ".join(volume_info.get("authors", []))
                        genres = ", ".join(volume_info.get("categories", []))
                        books.append({
                            "external_id": item.get("id", ""),
                            "title": volume_info.get("title", "Unbekannter Titel"),
                            "subtitle": volume_info.get("subtitle", ""),
                            "authors": authors,
                            "description": volume_info.get("description", ""),
                            "cover": volume_info.get("imageLinks", {}).get("thumbnail", ""),
                            "publisher": volume_info.get("publisher", ""),
                            "release_date": volume_info.get("publishedDate", ""),
                            "isbn": volume_info.get("industryIdentifiers", [{}])[0].get("identifier", "") if volume_info.get("industryIdentifiers") else ""
                        })
                    return books
        except Exception as e:
            logger.error(f"Fehler bei Google Books API-Anfrage: {e}")
            return None
    
    async def search_movies(self, query: str) -> Optional[List[Dict[str, Any]]]:
        """Sucht Filme über TMDB API"""
        if not get_config('apis.tmdb.enabled', True):
            return None
        
        url = f"{TMDB_BASE_URL}/search/movie"
        params = {
            "api_key": get_config('apis.tmdb.api_key'),
            "query": query,
            "language": "de-DE",
            "page": 1
        }
        
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get(url, params=params) as resp:
                    if resp.status != 200:
                        logger.warning(f"TMDB API Status: {resp.status}")
                        return None
                    
                    data = await resp.json()
                    results = data.get("results", [])
                    
                    movies = []
                    for movie in results:
                        genres = await self._get_tmdb_genres(movie.get("genre_ids", []))
                        movies.append({
                            "external_id": str(movie["id"]),
                            "title": movie.get("title", "Unbekannter Titel"),
                            "description": movie.get("overview", ""),
                            "cover": f"https://image.tmdb.org/t/p/w500{movie.get('poster_path', '')}" if movie.get("poster_path") else "",
                            "release_date": movie.get("release_date", ""),
                            "genres": ", ".join(genres),
                            "rating": movie.get("vote_average")
                        })
                    return movies
        except Exception as e:
            logger.error(f"Fehler bei TMDB API-Anfrage: {e}")
            return None
    
    async def search_comics(self, query: str) -> Optional[List[Dict[str, Any]]]:
        """Sucht Comics über Comic Vine API"""
        if not get_config('apis.comic_vine.enabled', True):
            return None
        
        url = f"{COMICVINE_BASE_URL}/search"
        params = {
            "api_key": get_config('apis.comic_vine.api_key'),
            "format": "json",
            "query": query,
            "resources": "volume",
            "limit": 5
        }
        
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get(url, params=params) as resp:
                    if resp.status != 200:
                        logger.warning(f"Comic Vine API Status: {resp.status}")
                        return None
                    
                    data = await resp.json()
                    results = data.get("results", [])
                    
                    comics = []
                    for comic in results:
                        cover_url = comic.get("image", {}).get("medium_url", "")
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
        if not get_config('apis.google_books.enabled', True):
            return None
        
        url = "https://www.googleapis.com/books/v1/volumes"
        params = {
            "q": f"{query} subject:magazine",
            "maxResults": 5
        }
        
        api_key = get_config('apis.google_books.api_key')
        if api_key:
            params["key"] = api_key
        
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get(url, params=params) as resp:
                    if resp.status != 200:
                        logger.warning(f"Google Books Magazine API Status: {resp.status}")
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
    
    async def _get_spotify_token(self):
        """Holt Spotify Access Token mit Ablaufprüfung"""
        if self.spotify_token and self.spotify_token_expiry and datetime.now() < self.spotify_token_expiry:
            return
        
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
                        self.spotify_token_expiry = datetime.now() + timedelta(seconds=token_data.get("expires_in", 3600) - 300)
                    else:
                        logger.error(f"Fehler beim Holen des Spotify Tokens: Status {resp.status}")
        except Exception as e:
            logger.error(f"Fehler bei Spotify Token-Anfrage: {e}")
    
    async def _get_igdb_token(self):
        """Holt IGDB Access Token mit Ablaufprüfung"""
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
        """Holt Genre-Namen für TMDB Genre-IDs aus Cache"""
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
                        logger.error(f"Fehler beim Laden der TMDB Genres: Status {resp.status}")
                        self.genre_cache = {}
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
        """Validiert eine ISBN mit Prüfsumme"""
        clean_isbn = isbn.strip().replace("-", "")
        if not clean_isbn.isdigit() or len(clean_isbn) not in [10, 13]:
            return False
        
        if len(clean_isbn) == 13:
            check = 0
            for i, digit in enumerate(clean_isbn[:-1]):
                check += int(digit) * (1 if i % 2 == 0 else 3)
            check_digit = (10 - (check % 10)) % 10
            return int(clean_isbn[-1]) == check_digit
        
        if len(clean_isbn) == 10:
            check = 0
            for i, digit in enumerate(clean_isbn[:-1]):
                check += int(digit) * (10 - i)
            check_digit = (11 - (check % 11)) % 11
            return clean_isbn[-1] in (str(check_digit), 'X')
        
        return False

# Globale Instanzen
db = Database()
media_repo = MediaRepository(db)
reminder_repo = ReminderRepository(db)
dashboard_repo = DashboardRepository(db)
api_handler = APIHandler()
