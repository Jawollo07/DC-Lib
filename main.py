import asyncio
from threading import Thread
import sys
import argparse

from config import config_manager, validate_required, logger
from database import db
from bot import DiscordBot
from web_dashboard import create_dashboard_app

def parse_arguments():
    """Parst Kommandozeilen-Argumente"""
    parser = argparse.ArgumentParser(description='Media Library Bot')
    parser.add_argument('--setup', action='store_true', help='Startet den Setup-Modus')
    parser.add_argument('--validate', action='store_true', help='Validiert die Konfiguration')
    parser.add_argument('--config', type=str, help='Pfad zur Konfigurationsdatei')
    parser.add_argument('--create-config', action='store_true', help='Erstellt eine Standard-Konfiguration')
    
    return parser.parse_args()

async def setup_mode():
    """Setup-Modus für erste Einrichtung"""
    print("🎯 Media Library Bot - Setup Modus")
    print("=" * 50)
    
    config = config_manager.get_all()
    
    print("\n📋 Aktuelle Konfiguration:")
    print(f"• Discord Token: {'✅ Gesetzt' if config['discord']['token'] else '❌ Fehlt'}")
    print(f"• Datenbank: {config['database']['user']}@{config['database']['host']}")
    print(f"• APIs: {sum(1 for api in config['apis'].values() if api.get('enabled'))} aktiviert")
    
    errors = config_manager.validate_config()
    if errors:
        print(f"\n❌ Konfigurationsfehler: {len(errors)}")
        for key, error in errors.items():
            print(f"  - {key}: {error}")
        
        print("\n🔧 Bitte korrigiere die Fehler in der bot_config.json Datei")
        print("   oder verwende '/setup' im Discord nach dem Start.")
    else:
        print("\n✅ Konfiguration ist valide!")
    
    print("\n🚀 Starte Bot...")

async def main():
    """Hauptfunktion"""
    args = parse_arguments()
    
    try:
        # Handle Kommandozeilen-Argumente
        if args.config:
            config_manager.config_file = args.config
            print(f"📁 Verwende Konfiguration: {args.config}")
        
        if args.create_config:
            config_manager._save_config(config_manager.default_config)
            print("✅ Standard-Konfiguration erstellt: bot_config.json")
            return
        
        if args.validate:
            errors = config_manager.validate_config()
            if errors:
                print("❌ Konfigurationsfehler:")
                for key, error in errors.items():
                    print(f"  - {key}: {error}")
                sys.exit(1)
            else:
                print("✅ Konfiguration ist valide!")
                return
        
        if args.setup:
            await setup_mode()
        
        # Validiere Konfiguration
        validate_required()
        
        # Datenbank initialisieren
        await db.create_pool()
        await db.init_tables()
        
        # Bot erstellen
        bot = DiscordBot()
        
        # Web-Dashboard starten falls aktiviert
        if config_manager.get('web_dashboard.enabled', True):
            from web_dashboard import create_dashboard_app
            flask_app = create_dashboard_app(bot.bot)
            
            Thread(target=lambda: flask_app.run(
                host=config_manager.get('web_dashboard.host', '0.0.0.0'),
                port=config_manager.get('web_dashboard.port', 5000),
                debug=False,
                use_reloader=False
            ), daemon=True).start()
            
            logger.info(f"🌐 Web-Dashboard gestartet auf {config_manager.get('web_dashboard.host')}:{config_manager.get('web_dashboard.port')}")
        
        # Bot starten
        await bot.start()
        
    except Exception as e:
        logger.error(f"❌ Fehler beim Starten des Bots: {e}")
        raise
    finally:
        # Aufräumen
        await db.close_pool()

if __name__ == "__main__":
    asyncio.run(main())
