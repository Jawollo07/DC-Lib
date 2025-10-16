#!/bin/bash

# Media Library Bot Start-Skript
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Aktiviere virtuelle Umgebung
if [ -d "venv" ]; then
    source venv/bin/activate
    echo "🐍 Virtuelle Umgebung aktiviert"
else
    echo "⚠️  Keine virtuelle Umgebung gefunden. Verwende System-Python."
fi

# Prüfe ob .env existiert
if [ ! -f ".env" ]; then
    echo "❌ .env Datei nicht gefunden. Bitte kopiere .env.example zu .env und konfiguriere sie."
    exit 1
fi

# Starte den Bot
echo "🚀 Starte Media Library Bot..."
python main.py "$@"