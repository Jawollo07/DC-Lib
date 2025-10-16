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
        async def config(
            interaction: discord.Interaction,
            action: str = "show",
            key: str = None,
            value: str = None
        ):
            await self._handle_config(interaction, action, key, value)
        
        @self.tree.command(name="config_wizard", description="Interaktiver Konfigurations-Assistent")
        @app_commands.default_permissions(administrator=True)
        async def config_wizard(interaction: discord.Interaction):
            await self._start_config_wizard(interaction)
    
    async def _start_setup(self, interaction: discord.Interaction):
        """Startet den interaktiven Setup-Prozess"""
        await interaction.response.defer(ephemeral=True)
        
        # Prüfe ob Setup bereits läuft
        if interaction.user.id in self.setup_sessions:
            await interaction.followup.send("❌ Du hast bereits einen aktiven Setup-Prozess.", ephemeral=True)
            return
        
        # Starte Setup-Session
        self.setup_sessions[interaction.user.id] = {
            'step': 0,
            'config': {},
            'channel': interaction.channel_id
        }
        
        embed = self._create_setup_embed("🎯 **Bot Setup gestartet**", 
                                       "Ich werde dich durch die Einrichtung des Bots führen.\n\n"
                                       "**Bereitgestellte Schritte:**\n"
                                       "1. 📋 Grundkonfiguration\n"
                                       "2. 🔐 API-Schlüssel\n"
                                       "3. ⚙️ Medien-Einstellungen\n"
                                       "4. 🔔 Benachrichtigungen\n"
                                       "5. 💾 Datenbank\n"
                                       "6. ✅ Abschluss\n\n"
                                       "Reagiere mit ✅ um fortzufahren oder ❌ um abzubrechen.")
        
        message = await interaction.followup.send(embed=embed, ephemeral=True)
        
        # Füge Reaktionen hinzu
        try:
            await message.add_reaction('✅')
            await message.add_reaction('❌')
        except:
            pass  # Falls Reaktionen nicht möglich sind
    
    async def _handle_config(self, interaction: discord.Interaction, action: str, key: str = None, value: str = None):
        """Behandelt Config-Commands"""
        await interaction.response.defer(ephemeral=True)
        
        if action == "show":
            if key:
                # Zeige spezifischen Wert
                config_value = get_config(key)
                embed = discord.Embed(
                    title="⚙️ Konfigurationswert",
                    description=f"**{key}**: `{config_value}`",
                    color=discord.Color.blue()
                )
            else:
                # Zeige gesamte Konfiguration
                embed = self._create_config_embed()
            
            await interaction.followup.send(embed=embed, ephemeral=True)
        
        elif action == "set" and key and value:
            # Setze Konfigurationswert
            try:
                # Versuche Wert zu parsen
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
            # Setze Konfigurationsabschnitt zurück
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
        
        embed.add_field(
            name="📋 Allgemein",
            value="Discord, Prefix, Kanäle",
            inline=True
        )
        embed.add_field(
            name="🔐 APIs",
            value="API-Schlüssel und Dienste",
            inline=True
        )
        embed.add_field(
            name="⚙️ Medien",
            value="Ausleih-Einstellungen",
            inline=True
        )
        embed.add_field(
            name="🔔 Benachrichtigungen",
            value="Erinnerungen und Reports",
            inline=True
        )
        embed.add_field(
            name="💾 Datenbank",
            value="Datenbank-Einstellungen",
            inline=True
        )
        embed.add_field(
            name="📊 Dashboard",
            value="Web-Dashboard Einstellungen",
            inline=True
        )
        
        # Erstelle Auswahl-Menü
        select = discord.ui.Select(
            placeholder="Wähle einen Konfigurationsbereich...",
            options=[
                discord.SelectOption(label="📋 Allgemein", value="general", description="Discord Einstellungen"),
                discord.SelectOption(label="🔐 APIs", value="apis", description="API-Schlüssel konfigurieren"),
                discord.SelectOption(label="⚙️ Medien", value="media", description="Ausleih-Einstellungen"),
                discord.SelectOption(label="🔔 Benachrichtigungen", value="notifications", description="Erinnerungen"),
                discord.SelectOption(label="💾 Datenbank", value="database", description="Datenbank-Einstellungen"),
                discord.SelectOption(label="📊 Dashboard", value="dashboard", description="Web-Dashboard")
            ]
        )
        
        async def select_callback(select_interaction: discord.Interaction):
            if select_interaction.user.id != interaction.user.id:
                await select_interaction.response.send_message("❌ Du kannst diese Auswahl nicht verwenden.", ephemeral=True)
                return
            
            area = select.values[0]
            await self._show_area_config(select_interaction, area)
        
        select.callback = select_callback
        view = discord.ui.View()
        view.add_item(select)
        
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)
    
    async def _show_area_config(self, interaction: discord.Interaction, area: str):
        """Zeigt Konfiguration für einen bestimmten Bereich"""
        area_configs = {
            'general': {
                'name': '📋 Allgemeine Einstellungen',
                'fields': [
                    ('discord.command_prefix', 'Befehls-Prefix', 'text'),
                    ('discord.auto_sync_commands', 'Commands automatisch syncen', 'boolean'),
                    ('discord.admin_roles', 'Admin-Rollen (kommagetrennt)', 'list')
                ]
            },
            'apis': {
                'name': '🔐 API-Einstellungen',
                'fields': [
                    ('apis.google_books.api_key', 'Google Books API Key', 'text'),
                    ('apis.tmdb.api_key', 'TMDB API Key', 'text'),
                    ('apis.spotify.client_id', 'Spotify Client ID', 'text'),
                    ('apis.spotify.client_secret', 'Spotify Client Secret', 'text'),
                    ('apis.igdb.client_id', 'IGDB Client ID', 'text'),
                    ('apis.igdb.client_secret', 'IGDB Client Secret', 'text'),
                    ('apis.board_game_atlas.client_id', 'Board Game Atlas Client ID', 'text'),
                    ('apis.comic_vine.api_key', 'Comic Vine API Key', 'text')
                ]
            },
            'media': {
                'name': '⚙️ Medien-Einstellungen',
                'fields': [
                    ('media_settings.due_period_days', 'Ausleihdauer (Tage)', 'number'),
                    ('media_settings.remind_days_before', 'Erinnerung vor Fälligkeit (Tage)', 'number'),
                    ('media_settings.max_loans_per_user', 'Max. Ausleihen pro Benutzer', 'number'),
                    ('media_settings.allow_extensions', 'Verlängerungen erlauben', 'boolean'),
                    ('media_settings.max_extension_days', 'Max. Verlängerung (Tage)', 'number')
                ]
            },
            'notifications': {
                'name': '🔔 Benachrichtigungen',
                'fields': [
                    ('notifications.enable_dm_reminders', 'DM-Erinnerungen', 'boolean'),
                    ('notifications.enable_channel_reminders', 'Kanal-Erinnerungen', 'boolean'),
                    ('notifications.daily_reminder_time', 'Tägliche Erinnerungszeit', 'text'),
                    ('notifications.weekly_report', 'Wöchentlicher Report', 'boolean'),
                    ('notifications.weekly_report_day', 'Report-Tag', 'text')
                ]
            },
            'database': {
                'name': '💾 Datenbank',
                'fields': [
                    ('database.host', 'Datenbank Host', 'text'),
                    ('database.port', 'Datenbank Port', 'number'),
                    ('database.user', 'Datenbank Benutzer', 'text'),
                    ('database.password', 'Datenbank Passwort', 'text'),
                    ('database.database', 'Datenbank Name', 'text')
                ]
            },
            'dashboard': {
                'name': '📊 Web-Dashboard',
                'fields': [
                    ('web_dashboard.enabled', 'Dashboard aktivieren', 'boolean'),
                    ('web_dashboard.host', 'Dashboard Host', 'text'),
                    ('web_dashboard.port', 'Dashboard Port', 'number'),
                    ('web_dashboard.password', 'Dashboard Passwort', 'text'),
                    ('web_dashboard.enable_api', 'API aktivieren', 'boolean')
                ]
            }
        }
        
        config_info = area_configs.get(area)
        if not config_info:
            await interaction.response.send_message("❌ Ungültiger Bereich.", ephemeral=True)
            return
        
        embed = discord.Embed(
            title=config_info['name'],
            color=discord.Color.blue()
        )
        
        for field_path, field_name, field_type in config_info['fields']:
            current_value = get_config(field_path)
            embed.add_field(
                name=field_name,
                value=f"`{current_value}`\n*Pfad: {field_path}*",
                inline=True
            )
        
        embed.set_footer(text="Verwende /config set <pfad> <wert> um Werte zu ändern")
        
        await interaction.response.edit_message(embed=embed, view=None)
    
    def _create_setup_embed(self, title: str, description: str) -> discord.Embed:
        """Erstellt ein Setup-Embed"""
        embed = discord.Embed(
            title=title,
            description=description,
            color=discord.Color.gold()
        )
        return embed
    
    def _create_config_embed(self) -> discord.Embed:
        """Erstellt ein Embed mit der gesamten Konfiguration"""
        config = config_manager.get_all()
        
        embed = discord.Embed(
            title="⚙️ Bot-Konfiguration",
            color=discord.Color.blue()
        )
        
        # Zeige nur wichtige Einstellungen an
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
            value_text = ""
            for name, path, value in settings:
                if isinstance(value, bool):
                    display_value = "✅" if value else "❌"
                else:
                    display_value = value
                value_text += f"**{name}:** {display_value}\n"
            
            embed.add_field(name=category, value=value_text, inline=True)
        
        # Validierungsfehler
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
        
        # Boolean
        if value.lower() in ['true', 'yes', 'ja', '1', 'enable']:
            return True
        elif value.lower() in ['false', 'no', 'nein', '0', 'disable']:
            return False
        
        # Number
        if value.isdigit():
            return int(value)
        
        # Float
        try:
            return float(value)
        except ValueError:
            pass
        
        # List (comma-separated)
        if ',' in value:
            return [item.strip() for item in value.split(',')]
        
        # Default: String
        return value

class ConfigValidation:
    """Konfigurations-Validierung"""
    
    @staticmethod
    async def validate_database_config(interaction: discord.Interaction) -> bool:
        """Validiert die Datenbank-Konfiguration"""
        try:
            # Hier würde die Datenbank-Verbindung getestet werden
            # Für jetzt geben wir einfach True zurück
            return True
        except Exception as e:
            await interaction.followup.send(f"❌ Datenbank-Fehler: {str(e)}", ephemeral=True)
            return False
    
    @staticmethod
    async def validate_apis_config(interaction: discord.Interaction) -> Dict[str, bool]:
        """Validiert die API-Konfigurationen"""
        results = {}
        config = config_manager.get_all()
        
        # Google Books API
        if config['apis']['google_books']['enabled'] and config['apis']['google_books']['api_key']:
            results['google_books'] = True
        else:
            results['google_books'] = False
        
        # TMDB API
        if config['apis']['tmdb']['enabled'] and config['apis']['tmdb']['api_key']:
            results['tmdb'] = True
        else:
            results['tmdb'] = False
        
        # Spotify API
        if (config['apis']['spotify']['enabled'] and 
            config['apis']['spotify']['client_id'] and 
            config['apis']['spotify']['client_secret']):
            results['spotify'] = True
        else:
            results['spotify'] = False
        
        return results
