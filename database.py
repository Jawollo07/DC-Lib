import aiomysql
import aiohttp
import base64
import json
from datetime import date, timedelta
from typing import Optional, Dict, Any, List
from config import config, logger

class Database:
    """Datenbank-Verwaltungsklasse"""
    
    def __init__(self):
        self.pool: Optional[aiomysql.Pool] = None
    
    async def create_pool(self) -> None:
        """Erstellt einen Datenbank-Verbindungspool"""
        try:
            self.pool = await aiomysql.create_pool(
                host=config.MYSQL_HOST,
                port=config.MYSQL_PORT,
                user=config.MYSQL_USER,
                password=config.MYSQL_PASSWORD,
                db=config.MYSQL_DB,
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
    """Datenbank-Operationen für Erinnerungen"""
    
    def __init__(self, db: Database):
        self.db = db
    
    async def get_due_media(self, reminder_date: str, media_type: str = None):
        """Holt fällige Medien für Erinnerungen"""
        async with self.db.pool.acquire() as conn:
            async with conn.cursor() as cur:
                if media_type:
                    await cur.execute("""
                        SELECT user_id, title, due_date, media_type FROM media_items
                        WHERE reminded = FALSE AND due_date <= %s AND media_type = %s
                    """, (reminder_date, media_type))
                else:
                    await cur.execute("""
                        SELECT user_id, title, due_date, media_type FROM media_items
                        WHERE reminded = FALSE AND due_date <= %s
                    """, (reminder_date,))
                return await cur.fetchall()
    
    async def mark_media_reminded(self, user_id: int, title: str, media_type: str):
        """Markiert ein Medium als erinnert"""
        async with self.db.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "UPDATE media_items SET reminded = TRUE WHERE user_id = %s AND title = %s AND media_type = %s",
                    (user_id, title, media_type)
                )

class APIHandler:
    """Handler für alle externen APIs"""
    
    def __init__(self):
        self.spotify_token = None
        self.igdb_token = None
        self.genre_cache = None
    
    # Bücher APIs
    async def fetch_book_by_isbn(self, isbn: str) -> Optional[Dict[str, Any]]:
        """Holt Buchinformationen von der Google Books API"""
        clean_isbn = isbn.strip().replace("-", "")
        url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{clean_isbn}"
        
        if config.GB_API_KEY:
            url += f"&key={config.GB_API_KEY}"
        
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        return None
                        
                    data = await resp.json()
                    if "items" not in data or not data["items"]:
                        return None
                        
                    item = data["items"][0]["volumeInfo"]
                    return {
                        "external_id": clean_isbn,
                        "title": item.get("title", "Unbekannter Titel"),
                        "subtitle": item.get("subtitle", ""),
                        "authors": ", ".join(item.get("authors", ["Unbekannter Autor"])),
                        "description": item.get("description", ""),
                        "cover": item.get("imageLinks", {}).get("thumbnail", ""),
                        "publisher": item.get("publisher", ""),
                        "release_date": item.get("publishedDate", ""),
                        "isbn": clean_isbn
                    }
        except Exception as e:
            logger.error(f"Fehler bei Google Books API-Anfrage für ISBN {isbn}: {e}")
            return None
    
    # Film/TV APIs
    async def search_movies(self, title: str) -> Optional[List[Dict[str, Any]]]:
        """Sucht Filme nach Titel über TMDB API"""
        if not config.TMDB_API_KEY:
            return None
            
        url = f"{config.TMDB_BASE_URL}/search/movie"
        params = {
            "api_key": config.TMDB_API_KEY,
            "query": title,
            "language": "de-DE",
            "include_adult": False
        }
        
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get(url, params=params) as resp:
                    if resp.status != 200:
                        return None
                        
                    data = await resp.json()
                    results = data.get("results", [])
                    
                    movies = []
                    for movie in results[:5]:
                        genre_names = await self._get_tmdb_genres(movie.get("genre_ids", []))
                        
                        movies.append({
                            "external_id": str(movie["id"]),
                            "title": movie.get("title", "Unbekannter Titel"),
                            "subtitle": movie.get("original_title", ""),
                            "description": movie.get("overview", ""),
                            "cover": f"{config.TMDB_IMAGE_BASE_URL}{movie.get('poster_path', '')}" if movie.get("poster_path") else "",
                            "release_date": movie.get("release_date", "Unbekannt"),
                            "rating": movie.get("vote_average", 0),
                            "genres": ", ".join(genre_names) if genre_names else "Unbekannt",
                            "duration": movie.get("runtime", 0)
                        })
                    
                    return movies
                    
        except Exception as e:
            logger.error(f"Fehler bei TMDB API-Anfrage für Titel {title}: {e}")
            return None
    
    async def search_tv_shows(self, title: str) -> Optional[List[Dict[str, Any]]]:
        """Sucht TV-Serien über TMDB API"""
        if not config.TMDB_API_KEY:
            return None
            
        url = f"{config.TMDB_BASE_URL}/search/tv"
        params = {
            "api_key": config.TMDB_API_KEY,
            "query": title,
            "language": "de-DE",
            "include_adult": False
        }
        
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get(url, params=params) as resp:
                    if resp.status != 200:
                        return None
                        
                    data = await resp.json()
                    results = data.get("results", [])
                    
                    tv_shows = []
                    for show in results[:5]:
                        genre_names = await self._get_tmdb_genres(show.get("genre_ids", []))
                        
                        tv_shows.append({
                            "external_id": str(show["id"]),
                            "title": show.get("name", "Unbekannter Titel"),
                            "subtitle": show.get("original_name", ""),
                            "description": show.get("overview", ""),
                            "cover": f"{config.TMDB_IMAGE_BASE_URL}{show.get('poster_path', '')}" if show.get("poster_path") else "",
                            "release_date": show.get("first_air_date", "Unbekannt"),
                            "rating": show.get("vote_average", 0),
                            "genres": ", ".join(genre_names) if genre_names else "Unbekannt"
                        })
                    
                    return tv_shows
                    
        except Exception as e:
            logger.error(f"Fehler bei TMDB TV API-Anfrage für Titel {title}: {e}")
            return None
    
    # Musik APIs
    async def search_music(self, query: str, search_type: str = "album") -> Optional[List[Dict[str, Any]]]:
        """Sucht Musik über Spotify API"""
        if not config.SPOTIFY_CLIENT_ID or not config.SPOTIFY_CLIENT_SECRET:
            return None
        
        if not self.spotify_token:
            await self._get_spotify_token()
        
        url = f"{config.SPOTIFY_BASE_URL}/search"
        params = {
            "q": query,
            "type": search_type,
            "limit": 5,
            "market": "DE"
        }
        
        headers = {"Authorization": f"Bearer {self.spotify_token}"}
        
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get(url, params=params, headers=headers) as resp:
                    if resp.status == 401:  # Token abgelaufen
                        await self._get_spotify_token()
                        headers["Authorization"] = f"Bearer {self.spotify_token}"
                        async with session.get(url, params=params, headers=headers) as new_resp:
                            if new_resp.status != 200:
                                return None
                            data = await new_resp.json()
                    elif resp.status != 200:
                        return None
                    else:
                        data = await resp.json()
                    
                    items = data.get(f"{search_type}s", {}).get("items", [])
                    results = []
                    
                    for item in items:
                        if search_type == "album":
                            artists = ", ".join([artist["name"] for artist in item.get("artists", [])])
                            result = {
                                "external_id": item["id"],
                                "title": item.get("name", "Unbekannter Titel"),
                                "artists": artists,
                                "cover": item["images"][0]["url"] if item.get("images") else "",
                                "release_date": item.get("release_date", ""),
                                "upc": item.get("external_ids", {}).get("upc", ""),
                                "media_type": "music_cd"
                            }
                        elif search_type == "track":
                            artists = ", ".join([artist["name"] for artist in item.get("artists", [])])
                            album = item.get("album", {})
                            result = {
                                "external_id": item["id"],
                                "title": item.get("name", "Unbekannter Titel"),
                                "artists": artists,
                                "cover": album["images"][0]["url"] if album.get("images") else "",
                                "release_date": album.get("release_date", ""),
                                "duration": item.get("duration_ms", 0) // 1000,  # in Sekunden
                                "media_type": "song"
                            }
                        
                        results.append(result)
                    
                    return results
                    
        except Exception as e:
            logger.error(f"Fehler bei Spotify API-Anfrage: {e}")
            return None
    
    async def search_musicbrainz(self, query: str, entity: str = "release") -> Optional[List[Dict[str, Any]]]:
        """Sucht Musik über MusicBrainz API (für Vinyl, CDs etc.)"""
        url = f"{config.MUSICBRAINZ_BASE_URL}/{entity}"
        params = {
            "query": query,
            "fmt": "json",
            "limit": 5
        }
        
        headers = {
            "User-Agent": "DiscordMediaBot/1.0",
            "Accept": "application/json"
        }
        
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get(url, params=params, headers=headers) as resp:
                    if resp.status != 200:
                        return None
                    
                    data = await resp.json()
                    releases = data.get("releases", [])
                    
                    results = []
                    for release in releases:
                        artists = ", ".join([artist["name"] for artist in release.get("artist-credit", []) if "name" in artist])
                        
                        result = {
                            "external_id": release["id"],
                            "title": release.get("title", "Unbekannter Titel"),
                            "artists": artists,
                            "release_date": release.get("date", ""),
                            "media_type": "vinyl" if "Vinyl" in release.get("packaging", "") else "music_cd"
                        }
                        
                        cover_url = await self._get_musicbrainz_cover(release["id"])
                        if cover_url:
                            result["cover"] = cover_url
                        
                        results.append(result)
                    
                    return results
                    
        except Exception as e:
            logger.error(f"Fehler bei MusicBrainz API-Anfrage: {e}")
            return None
    
    # Videospiele API
    async def search_video_games(self, query: str) -> Optional[List[Dict[str, Any]]]:
        """Sucht Videospiele über IGDB API"""
        if not config.IGDB_CLIENT_ID or not config.IGDB_CLIENT_SECRET:
            return None
        
        if not self.igdb_token:
            await self._get_igdb_token()
        
        url = f"{config.IGDB_BASE_URL}/games"
        headers = {
            "Client-ID": config.IGDB_CLIENT_ID,
            "Authorization": f"Bearer {self.igdb_token}",
            "Content-Type": "application/json"
        }
        
        # IGDB API verwendet eine spezielle Abfragesprache
        data = f"""
            fields name, cover.url, first_release_date, summary, genres.name, platforms.name, rating, involved_companies.company.name;
            search "{query}";
            limit 5;
            where category = 0;
        """
        
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.post(url, headers=headers, data=data) as resp:
                    if resp.status == 401:  # Token abgelaufen
                        await self._get_igdb_token()
                        headers["Authorization"] = f"Bearer {self.igdb_token}"
                        async with session.post(url, headers=headers, data=data) as new_resp:
                            if new_resp.status != 200:
                                return None
                            games_data = await new_resp.json()
                    elif resp.status != 200:
                        return None
                    else:
                        games_data = await resp.json()
                    
                    games = []
                    for game in games_data:
                        # Cover URL formatieren
                        cover_url = ""
                        if game.get("cover"):
                            cover_url = f"https:{game['cover']['url']}".replace("t_thumb", "t_cover_big")
                        
                        # Genres extrahieren
                        genres = ", ".join([genre["name"] for genre in game.get("genres", [])])
                        
                        # Plattformen extrahieren
                        platforms = ", ".join([platform["name"] for platform in game.get("platforms", [])])
                        
                        # Entwickler extrahieren
                        developers = []
                        for company in game.get("involved_companies", []):
                            if company.get("developer", False):
                                developers.append(company["company"]["name"])
                        
                        games.append({
                            "external_id": str(game["id"]),
                            "title": game.get("name", "Unbekannter Titel"),
                            "description": game.get("summary", ""),
                            "cover": cover_url,
                            "release_date": str(game.get("first_release_date", ""))[:4] if game.get("first_release_date") else "",
                            "rating": round(game.get("rating", 0), 1),
                            "genres": genres,
                            "platforms": platforms,
                            "publisher": ", ".join(developers) if developers else "Unbekannt"
                        })
                    
                    return games
                    
        except Exception as e:
            logger.error(f"Fehler bei IGDB API-Anfrage: {e}")
            return None
    
    # Brettspiele API
    async def search_board_games(self, query: str) -> Optional[List[Dict[str, Any]]]:
        """Sucht Brettspiele über Board Game Atlas API"""
        if not config.BOARDGAMEATLAS_CLIENT_ID:
            return None
        
        url = f"{config.BOARDGAMEATLAS_BASE_URL}/search"
        params = {
            "name": query,
            "client_id": config.BOARDGAMEATLAS_CLIENT_ID,
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
                        results.append({
                            "external_id": game["id"],
                            "title": game.get("name", "Unbekannter Titel"),
                            "description": game.get("description", ""),
                            "cover": game.get("image_url", ""),
                            "release_date": str(game.get("year_published", "")),
                            "rating": round(game.get("average_user_rating", 0), 1),
                            "players": f"{game.get('min_players', '?')}-{game.get('max_players', '?')}",
                            "duration": game.get("min_playtime", 0),
                            "publisher": game.get("primary_publisher", {}).get("name", "Unbekannt")
                        })
                    
                    return results
                    
        except Exception as e:
            logger.error(f"Fehler bei Board Game Atlas API-Anfrage: {e}")
            return None
    
    # Comics API
    async def search_comics(self, query: str) -> Optional[List[Dict[str, Any]]]:
        """Sucht Comics über Comic Vine API"""
        if not config.COMICVINE_API_KEY:
            return None
        
        url = f"{config.COMICVINE_BASE_URL}/search"
        params = {
            "api_key": config.COMICVINE_API_KEY,
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
    
    # Zeitschriften API (Google Books für Magazine)
    async def search_magazines(self, query: str) -> Optional[List[Dict[str, Any]]]:
        """Sucht Zeitschriften über Google Books API"""
        url = "https://www.googleapis.com/books/v1/volumes"
        params = {
            "q": f"{query} subject:magazine",
            "maxResults": 5
        }
        
        if config.GB_API_KEY:
            params["key"] = config.GB_API_KEY
        
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
    
    # Hilfsmethoden
    async def _get_spotify_token(self):
        """Holt Spotify Access Token"""
        auth_string = f"{config.SPOTIFY_CLIENT_ID}:{config.SPOTIFY_CLIENT_SECRET}"
        auth_bytes = auth_string.encode('utf-8')
        auth_base64 = base64.b64encode(auth_bytes).decode('utf-8')
        
        url = "https://accounts.spotify.com/api/token"
        headers = {
            "Authorization": f"Basic {auth_base64}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {"grant_type": "client_credentials"}
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, data=data) as resp:
                if resp.status == 200:
                    token_data = await resp.json()
                    self.spotify_token = token_data["access_token"]
                else:
                    logger.error("Fehler beim Holen des Spotify Tokens")
    
    async def _get_igdb_token(self):
        """Holt IGDB Access Token"""
        url = "https://id.twitch.tv/oauth2/token"
        data = {
            "client_id": config.IGDB_CLIENT_ID,
            "client_secret": config.IGDB_CLIENT_SECRET,
            "grant_type": "client_credentials"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data) as resp:
                if resp.status == 200:
                    token_data = await resp.json()
                    self.igdb_token = token_data["access_token"]
                else:
                    logger.error("Fehler beim Holen des IGDB Tokens")
    
    async def _get_tmdb_genres(self, genre_ids: List[int]) -> List[str]:
        """Holt Genre-Namen für TMDB Genre-IDs"""
        if not config.TMDB_API_KEY:
            return []
        
        if self.genre_cache is None:
            await self._load_tmdb_genres()
        
        return [self.genre_cache[genre_id] for genre_id in genre_ids if genre_id in self.genre_cache]
    
    async def _load_tmdb_genres(self):
        """Lädt alle verfügbaren Genres von TMDB"""
        url = f"{config.TMDB_BASE_URL}/genre/movie/list"
        params = {
            "api_key": config.TMDB_API_KEY,
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
        except:
            pass
        return None
    
    def validate_isbn(self, isbn: str) -> bool:
        """Validiert eine ISBN"""
        clean_isbn = isbn.strip().replace("-", "")
        return clean_isbn.isdigit() and len(clean_isbn) in [10, 13]

# Globale Instanzen
db = Database()
media_repo = MediaRepository(db)
reminder_repo = ReminderRepository(db)
api_handler = APIHandler()
