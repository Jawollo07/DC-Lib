#!/bin/bash

echo "📚 Media Library Bot - Installation"
echo "===================================="

# Prüfe ob Python 3.11+ installiert ist
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 ist nicht installiert. Bitte installiere Python 3.11 oder höher."
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
echo "✅ Python $PYTHON_VERSION gefunden"

# Erstelle virtuelle Umgebung
echo "🐍 Erstelle virtuelle Umgebung..."
python3 -m venv venv
source venv/bin/activate

# Installiere Abhängigkeiten
echo "📦 Installiere Abhängigkeiten..."
pip install --upgrade pip
pip install -r requirements.txt

# Erstelle .env Datei falls nicht vorhanden
if [ ! -f .env ]; then
    echo "⚙️ Erstelle .env Vorlage..."
    cp .env.example .env
    echo "📝 Bitte bearbeite die .env Datei mit deinen API-Schlüsseln!"
fi

# Erstelle bot_config.json falls nicht vorhanden
if [ ! -f bot_config.json ]; then
    echo "⚙️ Erstelle Standard-Konfiguration..."
    python -c "
from config import config_manager
config_manager._save_config(config_manager.default_config)
print('✅ Standard-Konfiguration erstellt')
"
fi

# Erstelle Log-Verzeichnis
mkdir -p logs

echo ""
echo "🎉 Installation abgeschlossen!"
echo ""
echo "Nächste Schritte:"
echo "1. Bearbeite die .env Datei mit deinen API-Schlüsseln"
echo "2. Starte den Bot mit: python main.py --setup"
echo "3. Oder validiere die Konfiguration: python main.py --validate"
echo ""
echo "📚 Dokumentation: Siehe README.md"