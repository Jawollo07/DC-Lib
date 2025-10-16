#!/bin/bash

cd /home/container

# Auto-Update wenn aktiviert und Git-Repository vorhanden
if [[ -d .git ]] && [[ "${AUTO_UPDATE}" == "1" ]]; then
    echo "🔄 Auto-Update aktiviert - Pulling latest changes..."
    git pull
    echo "✅ Update abgeschlossen"
fi

# Aktiviere virtuelle Umgebung falls vorhanden
if [ -d "venv" ]; then
    source venv/bin/activate
    echo "🐍 Virtuelle Umgebung aktiviert"
fi

# Installiere/Update Abhängigkeiten
echo "📦 Installiere/Update Abhängigkeiten..."
pip install --upgrade pip
pip install -r requirements.txt

# Erstelle Standard-Konfiguration falls nicht vorhanden
if [ ! -f "bot_config.json" ]; then
    echo "⚙️ Erstelle Standard-Konfiguration..."
    python -c "
import sys
sys.path.append('/home/container')
from config import config_manager
config_manager._save_config(config_manager.default_config)
print('✅ Standard-Konfiguration erstellt')
"
fi

# Erstelle .env falls nicht vorhanden (nur Vorlage)
if [ ! -f ".env" ]; then
    echo "📝 Erstelle .env Vorlage..."
    cat > .env << EOL
# Discord Bot Token (ERFORDERLICH)
DISCORD_TOKEN=dein_discord_bot_token_hier

# Optionale APIs (können später hinzugefügt werden)
# GOOGLE_BOOKS_API_KEY=dein_google_books_api_key
# TMDB_API_KEY=dein_tmdb_api_key  
# SPOTIFY_CLIENT_ID=dein_spotify_client_id
# SPOTIFY_CLIENT_SECRET=dein_spotify_client_secret
# COMICVINE_API_KEY=dein_comicvine_api_key

# Datenbank (Standardwerte für Pterodactyl)
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=pterodactyl
MYSQL_PASSWORD=
MYSQL_DB=media_library

# Bot Einstellungen
DUE_PERIOD_DAYS=14
REMIND_DAYS_BEFORE=1
DASHBOARD_PASSWORD=admin
FLASK_HOST=0.0.0.0
FLASK_PORT=5000
EOL
    echo "⚠️  Bitte bearbeite .env mit deinem Discord Token!"
fi

# Erstelle Log-Verzeichnis
mkdir -p logs

# Validiere grundlegende Konfiguration
echo "🔍 Validiere Konfiguration..."
if ! python -c "
import sys
sys.path.append('/home/container')
from config import config_manager
errors = config_manager.validate_config()
if errors:
    print('❌ Konfigurationsfehler:')
    for key, error in errors.items():
        print(f'   - {key}: {error}')
    print('📝 Bitte bearbeite die .env Datei!')
    sys.exit(1)
else:
    print('✅ Konfiguration ist valide')
"; then
    echo "❌ Konfigurationsvalidierung fehlgeschlagen"
    echo "💡 Tipp: Bearbeite die .env Datei mit deinem Discord Token"
    exit 1
fi

# Starte den Bot
echo "🚀 Starte Media Library Bot..."
exec python main.py "$@"