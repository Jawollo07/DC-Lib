import os
import json
import logging
from typing import Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

# Logging einrichten
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ConfigManager:
    """Konfigurations-Manager für alle Einstellungen"""
    
    def __init__(self):
        self.config_file = "bot_config.json"
        self.default_config = self._get_default_config()
        self.current_config = self._load_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Gibt die Standard-Konfiguration zurück"""
        return {
            "discord": {
                "token": os.getenv("DISCORD_TOKEN", ""),
                "admin_roles": ["Admin", "Moderator"],
                "allowed_channels": [],
                "command_prefix": "!",
                "auto_sync_commands": True
            },
            "apis": {
                "google_books": {
                    "enabled": True,
                    "api_key": os.getenv("GOOGLE_BOOKS_API_KEY", "")
                },
                "tmdb": {
                    "enabled": True,
                    "api_key": os.getenv("TMDB_API_KEY", "")
                },
                "spotify": {
                    "enabled": True,
                    "client_id": os.getenv("SPOTIFY_CLIENT_ID", ""),
                    "client_secret": os.getenv("SPOTIFY_CLIENT_SECRET", "")
                },
                "igdb": {
                    "enabled": True,
                    "client_id": os.getenv("IGDB_CLIENT_ID", ""),
                    "client_secret": os.getenv("IGDB_CLIENT_SECRET", "")
                },
                "boardgamegeek": {
                    "enabled": True,
                    "api_key": ""  # BoardGameGeek benötigt keinen API Key
                },
                "comic_vine": {
                    "enabled": True,
                    "api_key": os.getenv("COMICVINE_API_KEY", "")
                },
                "open_library": {
                    "enabled": True,
                    "api_key": ""  # Open Library benötigt keinen API Key
                }
            },
            "media_settings": {
                "due_period_days": 14,
                "remind_days_before": 1,
                "max_loans_per_user": 10,
                "allow_extensions": True,
                "max_extension_days": 7
            },
            "notifications": {
                "enable_dm_reminders": True,
                "enable_channel_reminders": False,
                "reminder_channel_id": None,
                "daily_reminder_time": "09:00",
                "weekly_report": True,
                "weekly_report_day": "monday",
                "weekly_report_time": "10:00"
            },
            "web_dashboard": {
                "enabled": True,
                "host": "0.0.0.0",
                "port": 5000,
                "password": os.getenv("DASHBOARD_PASSWORD", "admin"),
                "enable_api": True
            },
            "database": {
                "host": os.getenv("MYSQL_HOST", "localhost"),
                "port": int(os.getenv("MYSQL_PORT", "3306")),
                "user": os.getenv("MYSQL_USER", ""),
                "password": os.getenv("MYSQL_PASSWORD", ""),
                "database": os.getenv("MYSQL_DB", "media_library")
            },
            "logging": {
                "level": "INFO",
                "enable_file_logging": True,
                "log_file": "bot.log",
                "enable_discord_logging": False,
                "log_channel_id": None
            }
        }
    
    def _load_config(self) -> Dict[str, Any]:
        """Lädt die Konfiguration aus der Datei"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)
                    # Merge mit Default-Konfiguration für neue Einstellungen
                    return self._merge_configs(self.default_config, loaded_config)
            else:
                # Erstelle Standard-Konfiguration
                self._save_config(self.default_config)
                return self.default_config.copy()
        except Exception as e:
            logger.error(f"Fehler beim Laden der Konfiguration: {e}")
            return self.default_config.copy()
    
    def _merge_configs(self, default: Dict[str, Any], user: Dict[str, Any]) -> Dict[str, Any]:
        """Führt Standard- und Benutzerkonfiguration zusammen"""
        merged = default.copy()
        
        def recursive_merge(base, update):
            for key, value in update.items():
                if isinstance(value, dict) and key in base and isinstance(base[key], dict):
                    recursive_merge(base[key], value)
                else:
                    base[key] = value
        
        recursive_merge(merged, user)
        return merged
    
    def _save_config(self, config: Dict[str, Any]) -> bool:
        """Speichert die Konfiguration in eine Datei"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"Fehler beim Speichern der Konfiguration: {e}")
            return False
    
    def get(self, path: str, default: Any = None) -> Any:
        """Holt einen Konfigurationswert mit Pfad-Syntax"""
        keys = path.split('.')
        current = self.current_config
        
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
        
        return current
    
    def set(self, path: str, value: Any) -> bool:
        """Setzt einen Konfigurationswert mit Pfad-Syntax"""
        keys = path.split('.')
        current = self.current_config
        
        # Navigiere zum übergeordneten Objekt
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        
        # Setze den Wert
        current[keys[-1]] = value
        
        # Speichere die Konfiguration
        return self._save_config(self.current_config)
    
    def get_all(self) -> Dict[str, Any]:
        """Gibt die gesamte Konfiguration zurück"""
        return self.current_config.copy()
    
    def reset_section(self, section: str) -> bool:
        """Setzt einen Konfigurationsabschnitt auf Standardwerte zurück"""
        if section in self.default_config:
            self.current_config[section] = self.default_config[section].copy()
            return self._save_config(self.current_config)
        return False
    
    def validate_config(self) -> Dict[str, str]:
        """Validiert die Konfiguration und gibt Fehler zurück"""
        errors = {}
        
        # Discord Token
        if not self.get('discord.token'):
            errors['discord.token'] = "Discord Token ist erforderlich"
        
        # Datenbank-Einstellungen
        if not self.get('database.user'):
            errors['database.user'] = "Datenbank Benutzer ist erforderlich"
        
        if not self.get('database.password'):
            errors['database.password'] = "Datenbank Passwort ist erforderlich"
        
        return errors

# Globale Konfigurations-Instanz
config_manager = ConfigManager()

# Bequemlichkeits-Funktionen
def get_config(path: str, default: Any = None) -> Any:
    return config_manager.get(path, default)

def set_config(path: str, value: Any) -> bool:
    return config_manager.set(path, value)

def validate_required():
    errors = config_manager.validate_config()
    if errors:
        error_msg = "\n".join([f"{key}: {value}" for key, value in errors.items()])
        raise SystemExit(f"Konfigurationsfehler:\n{error_msg}")

# Medienarten-Konfiguration (statisch)
MEDIA_TYPES = {
    'book': {'name': '📚 Buch', 'color': '#3498db', 'enabled': True},
    'movie': {'name': '🎬 Film', 'color': '#9b59b6', 'enabled': True}, 
    'tv_show': {'name': '📺 TV-Serie', 'color': '#8e44ad', 'enabled': True},
    'music_cd': {'name': '💿 Musik-CD', 'color': '#27ae60', 'enabled': True},
    'audiobook': {'name': '🎧 Hörbuch', 'color': '#16a085', 'enabled': True},
    'video_game': {'name': '🎮 Videospiel', 'color': '#e74c3c', 'enabled': True},
    'board_game': {'name': '♟️ Brettspiel', 'color': '#d35400', 'enabled': True},
    'comic': {'name': '🦸 Comic', 'color': '#c0392b', 'enabled': True},
    'magazine': {'name': '📰 Zeitschrift', 'color': '#7f8c8d', 'enabled': True},
    'vinyl': {'name': '💿 Vinyl', 'color': '#27ae60', 'enabled': True},
    'dvd': {'name': '📀 DVD', 'color': '#2980b9', 'enabled': True},
    'bluray': {'name': '💿 Blu-ray', 'color': '#2980b9', 'enabled': True}
}