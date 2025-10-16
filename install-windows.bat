@echo off
echo 📚 Media Library Bot - Installation
echo ====================================

:: Prüfe ob Python installiert ist
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python ist nicht installiert oder nicht im PATH.
    echo Bitte installiere Python 3.11 oder höher von https://python.org
    pause
    exit /b 1
)

:: Erstelle virtuelle Umgebung
echo 🐍 Erstelle virtuelle Umgebung...
python -m venv venv
call venv\Scripts\activate.bat

:: Installiere Abhängigkeiten
echo 📦 Installiere Abhängigkeiten...
python -m pip install --upgrade pip
pip install -r requirements.txt

:: Erstelle .env Datei falls nicht vorhanden
if not exist ".env" (
    echo ⚙️ Erstelle .env Vorlage...
    copy .env.example .env
    echo 📝 Bitte bearbeite die .env Datei mit deinen API-Schlüsseln!
)

:: Erstelle bot_config.json falls nicht vorhanden
if not exist "bot_config.json" (
    echo ⚙️ Erstelle Standard-Konfiguration...
    python -c "from config import config_manager; config_manager._save_config(config_manager.default_config); print('✅ Standard-Konfiguration erstellt')"
)

:: Erstelle Log-Verzeichnis
if not exist "logs" mkdir logs

echo.
echo 🎉 Installation abgeschlossen!
echo.
echo Nächste Schritte:
echo 1. Bearbeite die .env Datei mit deinen API-Schlüsseln
echo 2. Starte den Bot mit: python main.py --setup
echo 3. Oder validiere die Konfiguration: python main.py --validate
echo.
pause