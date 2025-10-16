import discord
from discord import app_commands
from discord.ext import tasks
from datetime import date, timedelta, datetime
import asyncio
from typing import List, Dict, Any, Optional

from config import config_manager, get_config, validate_required, logger, MEDIA_TYPES
from database import db, media_repo, reminder_repo, dashboard_repo, api_handler
from setup_system import SetupSystem, ConfigValidation

class MediaCommands:
    """Handler für alle Medien-bezogenen Befehle"""

    def __init__(self, tree: app_commands.CommandTree):
        self.tree = tree
        self._register_commands()

    def _register_commands(self):
        """Registriert alle Medien-bezogenen Slash-Commands"""

        @self.tree.command(name="borrow_book", description="Ein Buch ausleihen")
        @app_commands.describe(isbn="ISBN des Buches")
        async def borrow_book(interaction: discord.Interaction, isbn: str):
            await self._borrow_media(interaction, "book", isbn=isbn)

        @self.tree.command(name="return_book", description="Buch zurückgeben")
        @app_commands.describe(isbn="ISBN des Buches")
        async def return_book(interaction: discord.Interaction, isbn: str):
            await self._return_media(interaction, "book", isbn.strip().replace("-", ""))

        @self.tree.command(name="borrow_movie", description="Einen Film ausleihen")
        @app_commands.describe(title="Titel des Films")
        async def borrow_movie(interaction: discord.Interaction, title: str):
            await self._borrow_media(interaction, "movie", title=title)

        @self.tree.command(name="return_movie", description="Film zurückgeben")
        @app_commands.describe(tmdb_id="TMDB ID des Films")
        async def return_movie(interaction: discord.Interaction, tmdb_id: str):
            await self._return_media(interaction, "movie", tmdb_id)

        @self.tree.command(name="borrow_tv_show", description="Eine TV-Serie ausleihen")
        @app_commands.describe(title="Titel der TV-Serie")
        async def borrow_tv_show(interaction: discord.Interaction, title: str):
            await self._borrow_media(interaction, "tv_show", title=title)

        @self.tree.command(name="return_tv_show", description="TV-Serie zurückgeben")
        @app_commands.describe(tmdb_id="TMDB ID der TV-Serie")
        async def return_tv_show(interaction: discord.Interaction, tmdb_id: str):
            await self._return_media(interaction, "tv_show", tmdb_id)

        @self.tree.command(name="borrow_music", description="Musik ausleihen (CD, Vinyl, Lied)")
        @app_commands.describe(
            query="Titel des Albums oder Künstlers",
            media_type="Art der Musik"
        )
        @app_commands.choices(media_type=[
            app_commands.Choice(name="Musik-CD", value="music_cd"),
            app_commands.Choice(name="Vinyl", value="vinyl"),
            app_commands.Choice(name="Lied", value="song")
        ])
        async def borrow_music(interaction: discord.Interaction, query: str, media_type: str):
            await self._borrow_media(interaction, media_type, query=query)

        @self.tree.command(name="return_music", description="Musik zurückgeben")
        @app_commands.describe(
            media_type="Art der Musik",
            external_id="ID des Mediums"
        )
        @app_commands.choices(media_type=[
            app_commands.Choice(name="Musik-CD", value="music_cd"),
            app_commands.Choice(name="Vinyl", value="vinyl"),
            app_commands.Choice(name="Lied", value="song")
        ])
        async def return_music(interaction: discord.Interaction, media_type: str, external_id: str):
            await self._return_media(interaction, media_type, external_id)

        @self.tree.command(name="borrow_video_game", description="Ein Videospiel ausleihen")
        @app_commands.describe(title="Titel des Videospiels")
        async def borrow_video_game(interaction: discord.Interaction, title: str):
            await self._borrow_media(interaction, "video_game", title=title)

        @self.tree.command(name="return_video_game", description="Videospiel zurückgeben")
        @app_commands.describe(igdb_id="IGDB ID des Videospiels")
        async def return_video_game(interaction: discord.Interaction, igdb_id: str):
            await self._return_media(interaction, "video_game", igdb_id)

        @self.tree.command(name="borrow_board_game", description="Ein Brettspiel ausleihen")
        @app_commands.describe(title="Titel des Brettspiels")
        async def borrow_board_game(interaction: discord.Interaction, title: str):
            await self._borrow_media(interaction, "board_game", title=title)

        @self.tree.command(name="return_board_game", description="Brettspiel zurückgeben")
        @app_commands.describe(bga_id="Board Game Atlas ID des Brettspiels")
        async def return_board_game(interaction: discord.Interaction, bga_id: str):
            await self._return_media(interaction, "board_game", bga_id)

        @self.tree.command(name="borrow_comic", description="Ein Comic ausleihen")
        @app_commands.describe(title="Titel des Comics")
        async def borrow_comic(interaction: discord.Interaction, title: str):
            await self._borrow_media(interaction, "comic", title=title)

        @self.tree.command(name="return_comic", description="Comic zurückgeben")
        @app_commands.describe(cv_id="Comic Vine ID des Comics")
        async def return_comic(interaction: discord.Interaction, cv_id: str):
            await self._return_media(interaction, "comic", cv_id)

        @self.tree.command(name="borrow_magazine", description="Eine Zeitschrift ausleihen")
        @app_commands.describe(title="Titel der Zeitschrift")
        async def borrow_magazine(interaction: discord.Interaction, title: str):
            await self._borrow_media(interaction, "magazine", title=title)

        @self.tree.command(name="return_magazine", description="Zeitschrift zurückgeben")
        @app_commands.describe(gb_id="Google Books ID der Zeitschrift")
        async def return_magazine(interaction: discord.Interaction, gb_id: str):
            await self._return_media(interaction, "magazine", gb_id)

        @self.tree.command(name="my_loans", description="Zeigt deine aktuellen Ausleihen")
        async def my_loans(interaction: discord.Interaction):
            await self._show_user_loans(interaction)

    async def _borrow_media(self, interaction: discord.Interaction, media_type: str, **kwargs):
        """Allgemeine Methode zum Ausleihen von Medien mit API-Integration"""
        await interaction.response.defer(ephemeral=True)

        if media_type not in MEDIA_TYPES or not MEDIA_TYPES[media_type]['enabled']:
            await interaction.followup.send(
                f"❌ Medientyp {media_type} wird nicht unterstützt oder ist deaktiviert.",
                ephemeral=True
            )
            return

        user_id = interaction.user.id
        username = interaction.user.name

        # Prüfe maximale Ausleihen
        current_loans = await media_repo.get_user_media(user_id)
        max_loans = get_config('media_settings.max_loans_per_user', 10)
        if len(current_loans) >= max_loans:
            await interaction.followup.send(
                f"❌ Du hast das Maximum von {max_loans} Ausleihen erreicht.",
                ephemeral=True
            )
            return

        # API-Suche basierend auf Medientyp
        media_info = None
        if media_type == "book" and kwargs.get("isbn"):
            if not api_handler.validate_isbn(kwargs["isbn"]):
                await interaction.followup.send("❌ Ungültige ISBN.", ephemeral=True)
                return
            results = await api_handler.search_books(kwargs["isbn"])
            media_info = results[0] if results else None
        else:
            query = kwargs.get("title") or kwargs.get("query")
            if not query:
                await interaction.followup.send("❌ Bitte gib einen Titel oder eine Abfrage ein.", ephemeral=True)
                return
            if media_type in ["movie", "tv_show"]:
                results = await api_handler.search_movies(query)
            elif media_type in ["music_cd", "vinyl", "song"]:
                results = await api_handler.search_music(query)
            elif media_type == "video_game":
                results = await api_handler.search_video_games(query)
            elif media_type == "board_game":
                results = await api_handler.search_board_games(query)
            elif media_type == "comic":
                results = await api_handler.search_comics(query)
            elif media_type == "magazine":
                results = await api_handler.search_magazines(query)
            else:
                results = None
            media_info = results[0] if results else None

        if not media_info:
            await interaction.followup.send("❌ Keine Medien gefunden.", ephemeral=True)
            return

        # Ausleihdauer berechnen
        due_date = (date.today() + timedelta(days=get_config('media_settings.due_period_days', 14))).isoformat()
        await media_repo.borrow_media(user_id, username, media_type, media_info, due_date)

        # Erfolgreiches Embed
        embed = discord.Embed(
            title=f"{MEDIA_TYPES[media_type]['name']} ausgeliehen",
            description=f"**{media_info['title']}** wurde erfolgreich ausgeliehen.\nFällig: {due_date}",
            color=discord.Color.from_str(MEDIA_TYPES[media_type]['color'])
        )
        if media_info.get('cover'):
            embed.set_thumbnail(url=media_info['cover'])
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def _return_media(self, interaction: discord.Interaction, media_type: str, external_id: str):
        """Allgemeine Methode zum Zurückgeben von Medien"""
        await interaction.response.defer(ephemeral=True)

        if media_type not in MEDIA_TYPES or not MEDIA_TYPES[media_type]['enabled']:
            await interaction.followup.send(
                f"❌ Medientyp {media_type} wird nicht unterstützt oder ist deaktiviert.",
                ephemeral=True
            )
            return

        user_id = interaction.user.id
        await media_repo.return_media(user_id, media_type, external_id)

        embed = discord.Embed(
            title=f"{MEDIA_TYPES[media_type]['name']} zurückgegeben",
            description="Das Medium wurde erfolgreich zurückgegeben.",
            color=discord.Color.from_str(MEDIA_TYPES[media_type]['color'])
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def _show_user_loans(self, interaction: discord.Interaction):
        """Zeigt die aktuellen Ausleihen eines Nutzers an"""
        await interaction.response.defer(ephemeral=True)

        user_id = interaction.user.id
        loans = await media_repo.get_user_media(user_id)

        if not loans:
            await interaction.followup.send("✅ Du hast aktuell keine ausgeliehenen Medien.", ephemeral=True)
            return

        embed = discord.Embed(
            title="📚 Deine Ausleihen",
            color=discord.Color.blue()
        )
        for loan in loans[:10]:  # Begrenze auf 10 Einträge
            embed.add_field(
                name=f"{MEDIA_TYPES[loan['media_type']]['name']}: {loan['title']}",
                value=f"Fällig: {loan['due_date']}\n"
                      f"{'⚠️ Überfällig' if loan['due_date'] < date.today().isoformat() else ''}",
                inline=False
            )
        if len(loans) > 10:
            embed.set_footer(text=f"... und {len(loans) - 10} weitere")
        await interaction.followup.send(embed=embed, ephemeral=True)

class AdminCommands:
    """Handler für Admin-bezogene Befehle"""

    def __init__(self, tree: app_commands.CommandTree, bot: discord.Client):
        self.tree = tree
        self.bot = bot
        self._register_commands()

    def _register_commands(self):
        """Registriert Admin-Commands"""

        @self.tree.command(name="stats", description="Zeigt Bot-Statistiken an")
        @app_commands.default_permissions(administrator=True)
        async def stats(interaction: discord.Interaction):
            await self._show_stats(interaction)

        @self.tree.command(name="overdue", description="Zeigt überfällige Medien an")
        @app_commands.default_permissions(administrator=True)
        async def overdue(interaction: discord.Interaction):
            await self._show_overdue(interaction)

        @self.tree.command(name="force_return", description="Medium eines Nutzers zwangsweise zurückgeben")
        @app_commands.default_permissions(administrator=True)
        @app_commands.describe(
            user="Der Nutzer",
            media_type="Medientyp",
            external_id="Externe ID des Mediums"
        )
        @app_commands.choices(media_type=[
            app_commands.Choice(name=v['name'], value=k) for k, v in MEDIA_TYPES.items() if v['enabled']
        ])
        async def force_return(interaction: discord.Interaction, user: discord.User, media_type: str, external_id: str):
            await self._force_return(interaction, user, media_type, external_id)

    async def _show_stats(self, interaction: discord.Interaction):
        """Zeigt Bot-Statistiken an"""
        await interaction.response.defer(ephemeral=True)

        total_loans = await dashboard_repo.get_total_loans()
        overdue_count = await dashboard_repo.get_overdue_count()
        media_stats = await dashboard_repo.get_media_stats()

        embed = discord.Embed(
            title="📊 Bot-Statistiken",
            color=discord.Color.blue()
        )
        embed.add_field(name="Gesamte Ausleihen", value=str(total_loans), inline=True)
        embed.add_field(name="Überfällige Medien", value=str(overdue_count), inline=True)
        embed.add_field(
            name="Medienarten",
            value="\n".join(f"{MEDIA_TYPES[k]['name']}: {v}" for k, v in media_stats.items()),
            inline=False
        )
        embed.set_footer(text=f"Bot läuft seit {discord.utils.format_dt(self.bot.start_time, 'R')}")
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def _show_overdue(self, interaction: discord.Interaction):
        """Zeigt überfällige Medien an"""
        await interaction.response.defer(ephemeral=True)

        overdue = await media_repo.get_overdue_media()
        if not overdue:
            await interaction.followup.send("✅ Keine überfälligen Medien.", ephemeral=True)
            return

        embed = discord.Embed(
            title="📅 Überfällige Medien",
            color=discord.Color.red()
        )
        for item in overdue[:10]:  # Begrenze auf 10 Einträge
            embed.add_field(
                name=f"{MEDIA_TYPES[item['media_type']]['name']}: {item['title']}",
                value=f"User: {item['username']}\nFällig: {item['due_date']}",
                inline=False
            )
        if len(overdue) > 10:
            embed.set_footer(text=f"... und {len(overdue) - 10} weitere")
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def _force_return(self, interaction: discord.Interaction, user: discord.User, media_type: str, external_id: str):
        """Zwingt die Rückgabe eines Mediums durch einen Admin"""
        await interaction.response.defer(ephemeral=True)

        if media_type not in MEDIA_TYPES or not MEDIA_TYPES[media_type]['enabled']:
            await interaction.followup.send(
                f"❌ Medientyp {media_type} wird nicht unterstützt oder ist deaktiviert.",
                ephemeral=True
            )
            return

        await media_repo.return_media(user.id, media_type, external_id)
        embed = discord.Embed(
            title=f"{MEDIA_TYPES[media_type]['name']} zwangsweise zurückgegeben",
            description=f"Medium für {user.mention} wurde zurückgegeben.",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

        # Benachrichtige den Nutzer
        try:
            user_embed = discord.Embed(
                title="⚠️ Medium zurückgegeben",
                description=f"Dein {MEDIA_TYPES[media_type]['name']} mit ID {external_id} wurde von einem Admin zurückgegeben.",
                color=discord.Color.red()
            )
            await user.send(embed=user_embed)
        except discord.Forbidden:
            logger.warning(f"Konnte Benachrichtigung nicht an {user.id} senden")

class ReminderTasks:
    """Tasks für automatische Erinnerungen und Berichte"""

    def __init__(self, bot: discord.Client):
        self.bot = bot
        self.remind_due_media.start()

    @tasks.loop(hours=24)
    async def remind_due_media(self):
        """Sendet Erinnerungen für fällige Medien"""
        try:
            reminders = await reminder_repo.get_due_reminders()
            if not reminders:
                logger.info("Keine fälligen Erinnerungen gefunden")
                return

            for row in reminders:
                user = self.bot.get_user(row['user_id'])
                if not user:
                    logger.warning(f"Benutzer {row['user_id']} nicht gefunden")
                    continue

                embed = discord.Embed(
                    title=f"🔔 Erinnerung: {MEDIA_TYPES[row['media_type']]['name']} fällig",
                    description=f"**{row['title']}** ist am {row['due_date']} fällig.\nBitte gib es rechtzeitig zurück!",
                    color=discord.Color.from_str(MEDIA_TYPES[row['media_type']]['color'])
                )
                if row.get('cover'):
                    embed.set_thumbnail(url=row['cover'])

                try:
                    await user.send(embed=embed)
                    await reminder_repo.mark_as_reminded(row['id'])
                    logger.info(f"Erinnerung gesendet an User {row['user_id']} für {row['media_type']} {row['title']}")
                except discord.Forbidden:
                    logger.warning(f"Konnte DM nicht an User {row['user_id']} senden")
                except Exception as e:
                    logger.error(f"Fehler beim Senden der Erinnerung an User {row['user_id']}: {e}")

        except Exception as e:
            logger.error(f"Fehler in remind_due_media Task: {e}")

    @remind_due_media.before_loop
    async def before_reminder(self):
        """Wartet bis der Bot bereit ist und richtet den Startzeitpunkt ein"""
        await self.bot.wait_until_ready()
        # Starte die Aufgabe zur konfigurierten Uhrzeit
        reminder_time = get_config('notifications.daily_reminder_time', '09:00')
        now = datetime.now()
        target_time = datetime.strptime(reminder_time, '%H:%M').replace(
            year=now.year, month=now.month, day=now.day
        )
        if now > target_time:
            target_time += timedelta(days=1)
        seconds_until = (target_time - now).total_seconds()
        await asyncio.sleep(seconds_until)

class DiscordBot:
    """Haupt-Bot-Klasse für die Media Library"""

    def __init__(self):
        self.bot = discord.Client(intents=self._setup_intents())
        self.tree = app_commands.CommandTree(self.bot)
        self.media_commands = MediaCommands(self.tree)
        self.setup_system = SetupSystem(self.tree)
        self.admin_commands = AdminCommands(self.tree, self.bot)
        self.reminder_tasks = None
        self.start_time = None
        self._register_events()

    def _setup_intents(self) -> discord.Intents:
        """Richtet die benötigten Discord Intents ein"""
        intents = discord.Intents.default()
        intents.message_content = False  # Deaktiviert, da nur Slash-Commands verwendet werden
        intents.members = True           # Für Nutzerinformationen und Admin-Befehle
        return intents

    def _register_events(self):
        """Registriert Bot-Event-Handler"""

        @self.bot.event
        async def on_ready():
            """Wird aufgerufen, wenn der Bot bereit ist"""
            try:
                self.start_time = discord.utils.utcnow()

                if get_config('discord.auto_sync_commands', True):
                    await self.tree.sync()
                    logger.info("✅ Discord Commands synchronisiert")

                self.reminder_tasks = ReminderTasks(self.bot)

                logger.info(f"✅ Bot erfolgreich eingeloggt als {self.bot.user} (ID: {self.bot.user.id})")
                logger.info(f"📊 Bot ist auf {len(self.bot.guilds)} Servern")

                errors = config_manager.validate_config()
                if errors:
                    logger.warning(f"⚠️ Konfigurationsfehler: {len(errors)} Probleme gefunden")
                    for key, error in errors.items():
                        logger.warning(f"  - {key}: {error}")
                else:
                    logger.info("✅ Konfiguration ist valide")

                api_config = get_config('apis', {})
                enabled_apis = [name for name, config in api_config.items() if config.get('enabled', False)]
                logger.info(f"🔌 Aktive APIs: {', '.join(enabled_apis) if enabled_apis else 'Keine'}")

            except Exception as e:
                logger.error(f"❌ Fehler beim Start: {e}")

        @self.bot.event
        async def on_guild_join(guild):
            """Wird aufgerufen, wenn der Bot einem Server beitritt"""
            logger.info(f"➕ Bot ist Server '{guild.name}' (ID: {guild.id}) beigetreten")

            try:
                system_channel = guild.system_channel
                if system_channel and system_channel.permissions_for(guild.me).send_messages:
                    embed = discord.Embed(
                        title="📚 Media Library Bot",
                        description=(
                            "Vielen Dank für das Hinzufügen des Media Library Bots! 🎉\n\n"
                            "**Erste Schritte:**\n"
                            "1. Verwende `/setup` für die Einrichtung\n"
                            "2. Oder `/config_wizard` für die Konfiguration\n"
                            "3. Beginne mit `/borrow_book` um Medien auszuleihen\n\n"
                            "Verwende `/help` für eine Liste aller Befehle."
                        ),
                        color=discord.Color.blue()
                    )
                    await system_channel.send(embed=embed)
            except Exception as e:
                logger.error(f"Konnte Willkommensnachricht nicht senden: {e}")

        @self.bot.event
        async def on_guild_remove(guild):
            """Wird aufgerufen, wenn der Bot einen Server verlässt"""
            logger.info(f"➖ Bot hat Server '{guild.name}' (ID: {guild.id}) verlassen")

        @self.bot.event
        async def on_command_error(interaction: discord.Interaction, error):
            """Behandelt Fehler bei Slash-Commands"""
            if isinstance(error, app_commands.errors.MissingPermissions):
                await interaction.response.send_message(
                    "❌ Du hast nicht die erforderlichen Berechtigungen für diesen Befehl.",
                    ephemeral=True
                )
            elif isinstance(error, app_commands.errors.CommandNotFound):
                await interaction.response.send_message(
                    "❌ Befehl nicht gefunden.",
                    ephemeral=True
                )
            else:
                logger.error(f"Command-Fehler: {error}")
                await interaction.response.send_message(
                    "❌ Ein Fehler ist aufgetreten. Bitte versuche es später erneut.",
                    ephemeral=True
                )

    async def start(self):
        """Startet den Bot"""
        try:
            await self.bot.start(get_config('discord.token'))
        except Exception as e:
            logger.error(f"Fehler beim Starten des Bots: {e}")
            raise
