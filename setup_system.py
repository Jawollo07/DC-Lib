import discord
from discord import app_commands
import asyncio
from typing import Dict, Any, List, Optional
from config import config_manager, get_config, set_config, validate_required, logger

class SetupSystem:
    """Setup-System für die Bot-Konfiguration"""
    
    def __init__(self, tree: app_commands.CommandTree):
        self.tree = tree
        self.setup_sessions = {}  # {user_id: setup_data}
        self._register_commands()
    
    def _register_commands(self):
        """Registriert die Setup-Commands"""
        
        @self.tree.command(name="setup", description="Startet den Bot-Setup")
        @app_commands.default_permissions(administrator=True)
        async def setup(interaction: discord.Interaction):
            await self._start_setup(interaction)
        
        @self.tree.command(name="config", description="Zeigt oder ändert Bot-Einstellungen")
        @app_commands.default_permissions(administrator=True)
        @app_commands.describe(
            action="Aktion: show, set oder reset",
            key="Konfigurationsschlüssel (z.B. discord.token)",
            value="Neuer Wert für den Schlüssel"
        )
        async def config(interaction: discord.Interaction, action: str = "show", key: str = None, value: str = None):
            await self._handle_config(interaction, action, key, value)
        
        @self.tree.command(name="config_wizard", description="Interaktiver Konfigurations-Assistent")
        @app_commands.default_permissions(administrator=True)
        async def config_wizard(interaction: discord.Interaction):
            await self._start_config_wizard(interaction)
    
    async def _start_setup(self, interaction: discord.Interaction):
        """Startet den interaktiven Setup-Prozess"""
        await interaction.response.defer(ephemeral=True)
        
        if interaction.user.id in self.setup_sessions:
            await interaction.followup.send("❌ Du hast bereits einen aktiven Setup-Prozess.", ephemeral=True)
            return
        
        self.setup_sessions[interaction.user.id] = {
            'step': 0,
            'config': {},
            'channel': interaction.channel_id
        }
        
        embed = self._create_setup_embed(
            title="🎯 **Bot Setup gestartet**",
            description=(
                "Ich werde dich durch die Einrichtung des Bots führen.\n\n"
                "**Bereitgestellte Schritte:**\n"
                "1. 📋 Grundkonfiguration\n"
                "2. 🔐 API-Schlüssel\n"
                "3. ⚙️ Medien-Einstellungen\n"
                "4. 🔔 Benachrichtigungen\n"
                "5. 💾 Datenbank\n"
                "6. ✅ Abschluss\n\n"
                "Reagiere mit ✅ um fortzufahren oder ❌ um abzubrechen."
            )
        )
        
        message = await interaction.followup.send(embed=embed, ephemeral=false)
        
        try:
            await message.add_reaction('✅')
            await message.add_reaction('❌')
        except discord.errors.Forbidden:
            logger.warning("Konnte Reaktionen nicht hinzufügen")
    
    async def _handle_config(self, interaction: discord.Interaction, action: str, key: str = None, value: str = None):
        """Behandelt Config-Commands mit erweiterter Validierung"""
        await interaction.response.defer(ephemeral=True)
        
        action = action.lower()
        if action == "show":
            if key:
                config_value = get_config(key)
                embed = discord.Embed(
                    title="⚙️ Konfigurationswert",
                    description=f"**{key}**: `{config_value}`",
                    color=discord.Color.blue()
                )
            else:
                embed = self._create_config_embed()
            await interaction.followup.send(embed=embed, ephemeral=True)
        
        elif action == "set" and key and value:
            try:
                parsed_value = self._parse_value(value)
                if set_config(key, parsed_value):
                    embed = discord.Embed(
                        title="✅ Konfiguration aktualisiert",
                        description=f"**{key}** wurde auf `{parsed_value}` gesetzt.",
                        color=discord.Color.green()
                    )
                else:
                    embed = discord.Embed(
                        title="❌ Fehler",
                        description="Konnte Konfiguration nicht speichern.",
                        color=discord.Color.red()
                    )
            except Exception as e:
                embed = discord.Embed(
                    title="❌ Fehler",
                    description=f"Ungültiger Wert: {str(e)}",
                    color=discord.Color.red()
                )
            await interaction.followup.send(embed=embed, ephemeral=True)
        
        elif action == "reset" and key:
            if config_manager.reset_section(key):
                embed = discord.Embed(
                    title="✅ Konfiguration zurückgesetzt",
                    description=f"Abschnitt **{key}** wurde auf Standardwerte zurückgesetzt.",
                    color=discord.Color.green()
                )
            else:
                embed = discord.Embed(
                    title="❌ Fehler",
                    description=f"Konnte Abschnitt {key} nicht zurücksetzen.",
                    color=discord.Color.red()
                )
            await interaction.followup.send(embed=embed, ephemeral=True)
        
        else:
            embed = discord.Embed(
                title="❌ Ungültige Aktion",
                description="Verwendung: `/config <show|set|reset> [key] [value]`",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
    
    async def _start_config_wizard(self, interaction: discord.Interaction):
        """Startet den interaktiven Konfigurations-Assistenten"""
        await interaction.response.defer(ephemeral=True)
        
        embed = discord.Embed(
            title="🧙 Konfigurations-Assistent",
            description="Wähle einen Konfigurationsbereich aus:",
            color=discord.Color.purple()
        )
        
        areas = [
            ("general", "📋 Allgemein (Discord, Prefix, etc.)"),
            ("apis", "🔐 APIs (Google Books, TMDB, etc.)"),
            ("media", "⚙️ Medien-Einstellungen"),
            ("notifications", "🔔 Benachrichtigungen"),
            ("database", "💾 Datenbank"),
            ("dashboard", "📊 Web-Dashboard")
        ]
        
        for area_id, area_name in areas:
            embed.add_field(name=area_name, value=f"Verwende `/config_wizard {area_id}`", inline=True)
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    def _create_setup_embed(self, title: str, description: str) -> discord.Embed:
        """Erstellt ein Setup-Embed"""
        return discord.Embed(
            title=title,
            description=description,
            color=discord.Color.gold()
        )
    
    def _create_config_embed(self) -> discord.Embed:
        """Erstellt ein Embed mit der gesamten Konfiguration"""
        config = config_manager.get_all()
        
        embed = discord.Embed(
            title="⚙️ Bot-Konfiguration",
            color=discord.Color.blue()
        )
        
        important_settings = {
            'Discord': [
                ('Token', 'discord.token', bool(config['discord']['token'])),
                ('Prefix', 'discord.command_prefix', config['discord']['command_prefix']),
                ('Admin-Rollen', 'discord.admin_roles', len(config['discord']['admin_roles']))
            ],
            'APIs': [
                ('Google Books', 'apis.google_books.enabled', config['apis']['google_books']['enabled']),
                ('TMDB', 'apis.tmdb.enabled', config['apis']['tmdb']['enabled']),
                ('Spotify', 'apis.spotify.enabled', config['apis']['spotify']['enabled'])
            ],
            'Medien': [
                ('Ausleihdauer', 'media_settings.due_period_days', f"{config['media_settings']['due_period_days']} Tage"),
                ('Max. Ausleihen', 'media_settings.max_loans_per_user', config['media_settings']['max_loans_per_user'])
            ]
        }
        
        for category, settings in important_settings.items():
            value_text = "\n".join(
                f"**{name}:** {'✅' if isinstance(value, bool) and value else '❌' if isinstance(value, bool) else value}"
                for name, path, value in settings
            )
            embed.add_field(name=category, value=value_text, inline=True)
        
        errors = config_manager.validate_config()
        if errors:
            error_text = "\n".join([f"• {error}" for error in errors.values()])
            embed.add_field(
                name="❌ Konfigurationsfehler",
                value=error_text,
                inline=False
            )
        
        embed.set_footer(text="Verwende /config_wizard für detaillierte Einstellungen")
        return embed
    
    def _parse_value(self, value: str):
        """Parset einen String-Wert in den entsprechenden Typ"""
        value = value.strip()
        
        if value.lower() in ['true', 'yes', 'ja', '1', 'enable']:
            return True
        elif value.lower() in ['false', 'no', 'nein', '0', 'disable']:
            return False
        elif value.isdigit():
            return int(value)
        try:
            return float(value)
        except ValueError:
            pass
        if ',' in value:
            return [item.strip() for item in value.split(',')]
        return value

class ConfigValidation:
    """Konfigurations-Validierung"""
    
    @staticmethod
    async def validate_database_config(interaction: discord.Interaction) -> bool:
        """Validiert die Datenbank-Konfiguration durch Testverbindung"""
        from database import db
        try:
            async with db.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT 1")
                return True
        except Exception as e:
            await interaction.followup.send(f"❌ Datenbank-Fehler: {str(e)}", ephemeral=True)
            logger.error(f"Datenbank-Validierungsfehler: {e}")
            return False
    
    @staticmethod
    async def validate_apis_config(interaction: discord.Interaction) -> Dict[str, bool]:
        """Validiert die API-Konfigurationen"""
        results = {}
        config = config_manager.get_all()
        
        for api_name, api_config in config['apis'].items():
            if api_config.get('enabled', False):
                if 'api_key' in api_config and not api_config['api_key']:
                    results[api_name] = False
                elif api_name == 'spotify' and (not api_config.get('client_id') or not api_config.get('client_secret')):
                    results[api_name] = False
                else:
                    results[api_name] = True
            else:
                results[api_name] = False
        
        return results
