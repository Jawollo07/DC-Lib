import asyncio
from threading import Thread
import sys
import argparse
from typing import Optional

from config import config_manager, validate_required, logger
from database import db
from bot import DiscordBot
from web_dashboard import create_dashboard_app

def parse_arguments() -> argparse.Namespace:
    """Parst Kommandozeilen-Argumente"""
    parser = argparse.ArgumentParser(description='Media Library Bot')
    parser.add_argument('--setup', action='store_true', help='Startet den Setup-Modus')
    parser.add_argument('--validate', action='store_true', help='Validiert die Konfiguration')
    parser.add_argument('--config', type=str, help='Pfad zur Konfigurationsdatei')
    parser.add_argument('--create-config', action='store_true', help='Erstellt eine Standard-Konfiguration')
    
    return parser.parse_args()

async def setup_mode():
    """Setup-Modus für die erste Einrichtung"""
    logger.info("🎯 Media Library Bot - Setup Modus")
    
    config = config_manager.get_all()
    
    logger.info("\n📋 Aktuelle Konfiguration:")
    logger.info(f"• Discord Token: {'✅ Gesetzt' if config['discord']['token'] else '❌ Fehlt'}")
    logger.info(f"• Datenbank: {config['database']['user']}@{config['database']['host']}")
    logger.info(f"• APIs: {sum(1 for api in config['apis'].values() if api.get('enabled'))} aktiviert")
    
    errors = config_manager.validate_config()
    if errors:
        logger.error(f"\n❌ Konfigurationsfehler: {len(errors)}")
        for key, error in errors.items():
            logger.error(f"  - {key}: {error}")
        logger.info("\n🔧 Bitte korrigiere die Fehler in der bot_config.json Datei")
    else:
        logger.info("\n✅ Konfiguration ist valide!")
    
    logger.info("\n🚀 Starte Bot...")

async def main():
    """Hauptfunktion des Bots"""
    args = parse_arguments()
    
    try:
        if args.config:
            config_manager.config_file = args.config
            logger.info(f"📁 Verwende Konfiguration: {args.config}")
        
        if args.create_config:
            config_manager._save_config(config_manager.default_config)
            logger.info("✅ Standard-Konfiguration erstellt: bot_config.json")
            return
        
        if args.validate:
            errors = config_manager.validate_config()
            if errors:
                logger.error("❌ Konfigurationsfehler:")
                for key, error in errors.items():
                    logger.error(f"  - {key}: {error}")
                sys.exit(1)
            else:
                logger.info("✅ Konfiguration ist valide!")
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
        
        # Web-Dashboard asynchron starten
        if config_manager.get('web_dashboard.enabled', True):
            flask_app = create_dashboard_app(bot.bot)
            
            def run_flask():
                flask_app.run(
                    host=config_manager.get('web_dashboard.host', '0.0.0.0'),
                    port=config_manager.get('web_dashboard.port', 5000),
                    debug=False,
                    use_reloader=False
                )
            
            Thread(target=run_flask, daemon=True).start()
            logger.info(f"🌐 Web-Dashboard gestartet auf {config_manager.get('web_dashboard.host')}:{config_manager.get('web_dashboard.port')}")
        
        # Bot starten
        await bot.start()
        
    except Exception as e:
        logger.error(f"❌ Fehler beim Starten des Bots: {e}")
        raise
    finally:
        await db.close_pool()

if __name__ == "__main__":
    asyncio.run(main())
