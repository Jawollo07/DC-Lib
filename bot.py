import discord
from discord import app_commands
from discord.ext import tasks
from datetime import date, timedelta
from threading import Thread
import asyncio
from typing import List, Dict, Any, Optional

from config import config_manager, get_config, validate_required, logger, MEDIA_TYPES
from database import db, media_repo, reminder_repo, dashboard_repo, api_handler
from setup_system import SetupSystem, ConfigValidation

class MediaCommands:
    """Handler für alle Medien-Commands"""
    
    def __init__(self, tree: app_commands.CommandTree):
        self.tree = tree
        self._register_commands()
    
    def _register_commands(self):
        """Registriert alle Commands"""
        
        # Buch Commands
        @self.tree.command(name="borrow_book", description="Ein Buch ausleihen")
        @app_commands.describe(isbn="ISBN des Buches")
        async def borrow_book(interaction: discord.Interaction, isbn: str):
            await self._borrow_media(interaction, "book", isbn=isbn)
        
        @self.tree.command(name="return_book", description="Buch zurückgeben")
        @app_commands.describe(isbn="ISBN des Buches")
        async def return_book(interaction: discord.Interaction, isbn: str):
            await self._return_media(interaction, "book", isbn.strip().replace("-", ""))
        
        # Film Commands
        @self.tree.command(name="borrow_movie", description="Einen Film ausleihen")
        @app_commands.describe(title="Titel des Films")
        async def borrow_movie(interaction: discord.Interaction, title: str):
            await self._borrow_media(interaction, "movie", title=title)
        
        @self.tree.command(name="return_movie", description="Film zurückgeben")
        @app_commands.describe(tmdb_id="TMDB ID des Films")
        async def return_movie(interaction: discord.Interaction, tmdb_id: str):
            await self._return_media(interaction, "movie", tmdb_id)
        
        # TV-Serien Commands
        @self.tree.command(name="borrow_tv_show", description="Eine TV-Serie ausleihen")
        @app_commands.describe(title="Titel der TV-Serie")
        async def borrow_tv_show(interaction: discord.Interaction, title: str):
            await self._borrow_media(interaction, "tv_show", title=title)
        
        @self.tree.command(name="return_tv_show", description="TV-Serie zurückgeben")
        @app_commands.describe(tmdb_id="TMDB ID der TV-Serie")
        async def return_tv_show(interaction: discord.Interaction, tmdb_id: str):
            await self._return_media(interaction, "tv_show", tmdb_id)
        
        # Musik Commands
        @self.tree.command(name="borrow_music", description="Musik ausleihen (CD, Vinyl)")
        @app_commands.describe(
            query="Titel des Albums oder Künstlers",
            media_type="Art der Musik"
        )
        @app_commands.choices(media_type=[
            app_commands.Choice(name="💿 Musik-CD", value="music_cd"),
            app_commands.Choice(name="💿 Vinyl", value="vinyl"),
            app_commands.Choice(name="🎧 Lied", value="song")
        ])
        async def borrow_music(interaction: discord.Interaction, query: str, media_type: str):
            await self._borrow_media(interaction, media_type, query=query)
        
        @self.tree.command(name="return_music", description="Musik zurückgeben")
        @app_commands.describe(
            media_type="Art der Musik",
            external_id="ID des Mediums"
        )
        @app_commands.choices(media_type=[
            app_commands.Choice(name="💿 Musik-CD", value="music_cd"),
            app_commands.Choice(name="💿 Vinyl", value="vinyl"),
            app_commands.Choice(name="🎧 Lied", value="song")
        ])
        async def return_music(interaction: discord.Interaction, media_type: str, external_id: str):
            await self._return_media(interaction, media_type, external_id)
        
        # Videospiele Commands
        @self.tree.command(name="borrow_video_game", description="Ein Videospiel ausleihen")
        @app_commands.describe(title="Titel des Videospiels")
        async def borrow_video_game(interaction: discord.Interaction, title: str):
            await self._borrow_media(interaction, "video_game", title=title)
        
        @self.tree.command(name="return_video_game", description="Videospiel zurückgeben")
        @app_commands.describe(igdb_id="IGDB ID des Videospiels")
        async def return_video_game(interaction: discord.Interaction, igdb_id: str):
            await self._return_media(interaction, "video_game", igdb_id)
        
        # Brettspiele Commands
        @self.tree.command(name="borrow_board_game", description="Ein Brettspiel ausleihen")
        @app_commands.describe(title="Titel des Brettspiels")
        async def borrow_board_game(interaction: discord.Interaction, title: str):
            await self._borrow_media(interaction, "board_game", title=title)
        
        @self.tree.command(name="return_board_game", description="Brettspiel zurückgeben")
        @app_commands.describe(bga_id="Board Game Atlas ID des Brettspiels")
        async def return_board_game(interaction: discord.Interaction, bga_id: str):
            await self._return_media(interaction, "board_game", bga_id)
        
        # Comics Commands
        @self.tree.command(name="borrow_comic", description="Ein Comic ausleihen")
        @app_commands.describe(title="Titel des Comics")
        async def borrow_comic(interaction: discord.Interaction, title: str):
            await self._borrow_media(interaction, "comic", title=title)
        
        @self.tree.command(name="return_comic", description="Comic zurückgeben")
        @app_commands.describe(cv_id="Comic Vine ID des Comics")
        async def return_comic(interaction: discord.Interaction, cv_id: str):
            await self._return_media(interaction, "comic", cv_id)
        
        # Zeitschriften Commands
        @self.tree.command(name="borrow_magazine", description="Eine Zeitschrift ausleihen")
        @app_commands.describe(title="Titel der Zeitschrift")
        async def borrow_magazine(interaction: discord.Interaction, title: str):
            await self._borrow_media(interaction, "magazine", title=title)
        
        @self.tree.command(name="return_magazine", description="Zeitschrift zurückgeben")
        @app_commands.describe(gb_id="Google Books ID der Zeitschrift")
        async def return_magazine(interaction: discord.Interaction, gb_id: str):
            await self._return_media(interaction, "magazine", gb_id)
        
        # Allgemeine Commands
        @self.tree.command(name="my_media", description="Meine ausgeliehenen Medien anzeigen")
        @app_commands.describe(media_type="Spezifischer Medientyp (optional)")
        @app_commands.choices(media_type=[
            app_commands.Choice(name="📚 Bücher", value="book"),
            app_commands.Choice(name="🎬 Filme", value="movie"),
            app_commands.Choice(name="📺 TV-Serien", value="tv_show"),
            app_commands.Choice(name="💿 Musik", value="music_cd"),
            app_commands.Choice(name="💿 Vinyl", value="vinyl"),
            app_commands.Choice(name="🎮 Videospiele", value="video_game"),
            app_commands.Choice(name="♟️ Brettspiele", value="board_game"),
            app_commands.Choice(name="🦸 Comics", value="comic"),
            app_commands.Choice(name="📰 Zeitschriften", value="magazine")
        ])
        async def my_media(interaction: discord.Interaction, media_type: str = None):
            await self._my_media(interaction, media_type)
        
        @self.tree.command(name="search_music", description="Suche nach Musik")
        @app_commands.describe(
            query="Suchbegriff (Titel, Künstler)",
            search_type="Was suchen?"
        )
        @app_commands.choices(search_type=[
            app_commands.Choice(name="🎵 Alben", value="album"),
            app_commands.Choice(name="🎧 Lieder", value="track")
        ])
        async def search_music(interaction: discord.Interaction, query: str, search_type: str = "album"):
            await self._search_music(interaction, query, search_type)
        
        @self.tree.command(name="search_video_games", description="Suche nach Videospielen")
        @app_commands.describe(query="Titel des Videospiels")
        async def search_video_games(interaction: discord.Interaction, query: str):
            await self._search_video_games(interaction, query)
        
        @self.tree.command(name="search_board_games", description="Suche nach Brettspielen")
        @app_commands.describe(query="Titel des Brettspiels")
        async def search_board_games(interaction: discord.Interaction, query: str):
            await self._search_board_games(interaction, query)
        
        @self.tree.command(name="search_comics", description="Suche nach Comics")
        @app_commands.describe(query="Titel des Comics")
        async def search_comics(interaction: discord.Interaction, query: str):
            await self._search_comics(interaction, query)
    
    async def _borrow_media(self, interaction: discord.Interaction, media_type: str, **kwargs):
        """Allgemeine Medien-Ausleihe"""
        await interaction.response.defer(ephemeral=True)
        
        # Prüfe ob Medienart aktiviert ist
        if not self._is_media_type_enabled(media_type):
            await interaction.followup.send(
                f"❌ Diese Medienart ist aktuell deaktiviert. "
                f"Ein Administrator kann sie in den Bot-Einstellungen aktivieren."
            )
            return
        
        # Prüfe Ausleihlimit
        if not await self._check_loan_limit(interaction.user.id):
            max_loans = get_config('media_settings.max_loans_per_user', 10)
            await interaction.followup.send(
                f"❌ Du hast das Maximum von {max_loans} Ausleihen erreicht. "
                f"Bitte gib zuerst einige Medien zurück."
            )
            return
        
        media_info = None
        search_results = None
        
        try:
            if media_type == "book":
                isbn = kwargs.get('isbn', '')
                if not api_handler.validate_isbn(isbn):
                    await interaction.followup.send("❌ Ungültige ISBN. Bitte gib eine gültige 10- oder 13-stellige ISBN ein.")
                    return
                
                media_info = await api_handler.fetch_book_by_isbn(isbn)
                if not media_info:
                    await interaction.followup.send("❌ Buch nicht gefunden. Bitte überprüfe die ISBN.")
                    return
            
            elif media_type == "movie":
                title = kwargs.get('title', '')
                if not self._is_api_enabled('tmdb'):
                    await interaction.followup.send("❌ TMDB API ist deaktiviert. Ein Administrator kann sie aktivieren.")
                    return
                search_results = await api_handler.search_movies(title)
            
            elif media_type == "tv_show":
                title = kwargs.get('title', '')
                if not self._is_api_enabled('tmdb'):
                    await interaction.followup.send("❌ TMDB API ist deaktiviert. Ein Administrator kann sie aktivieren.")
                    return
                search_results = await api_handler.search_tv_shows(title)
            
            elif media_type in ["music_cd", "vinyl", "song"]:
                query = kwargs.get('query', '')
                if not self._is_api_enabled('spotify'):
                    await interaction.followup.send("❌ Spotify API ist deaktiviert. Ein Administrator kann sie aktivieren.")
                    return
                
                search_type = "album" if media_type in ["music_cd", "vinyl"] else "track"
                search_results = await api_handler.search_music(query, search_type)
                
                if not search_results and media_type in ["music_cd", "vinyl"]:
                    search_results = await api_handler.search_musicbrainz(query)
            
            elif media_type == "video_game":
                title = kwargs.get('title', '')
                if not self._is_api_enabled('igdb'):
                    await interaction.followup.send("❌ IGDB API ist deaktiviert. Ein Administrator kann sie aktivieren.")
                    return
                search_results = await api_handler.search_video_games(title)
            
            elif media_type == "board_game":
                title = kwargs.get('title', '')
                if not self._is_api_enabled('board_game_atlas'):
                    await interaction.followup.send("❌ Board Game Atlas API ist deaktiviert. Ein Administrator kann sie aktivieren.")
                    return
                search_results = await api_handler.search_board_games(title)
            
            elif media_type == "comic":
                title = kwargs.get('title', '')
                if not self._is_api_enabled('comic_vine'):
                    await interaction.followup.send("❌ Comic Vine API ist deaktiviert. Ein Administrator kann sie aktivieren.")
                    return
                search_results = await api_handler.search_comics(title)
            
            elif media_type == "magazine":
                title = kwargs.get('title', '')
                if not self._is_api_enabled('google_books'):
                    await interaction.followup.send("❌ Google Books API ist deaktiviert. Ein Administrator kann sie aktivieren.")
                    return
                search_results = await api_handler.search_magazines(title)
            
            # Fehlerbehandlung für Suchergebnisse
            if search_results is not None:
                if not search_results:
                    await interaction.followup.send(f"❌ Keine {MEDIA_TYPES.get(media_type, {}).get('name', 'Medien')} gefunden. Bitte überprüfe deine Suche.")
                    return
                
                # Auswahlmenü für Suchergebnisse
                return await self._show_media_selection(interaction, search_results, media_type)
            
            # Direkte Ausleihe (für Bücher mit ISBN)
            if media_info:
                due_date = date.today() + timedelta(days=get_config('media_settings.due_period_days', 14))
                await media_repo.borrow_media(
                    interaction.user.id,
                    str(interaction.user),
                    media_type,
                    media_info,
                    due_date
                )
                
                embed = self._create_media_embed(media_info, due_date, media_type, "ausgeliehen")
                await interaction.followup.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Fehler beim Ausleihen von {media_type}: {e}")
            await interaction.followup.send("❌ Ein Fehler ist aufgetreten. Bitte versuche es später erneut.")
    
    async def _show_media_selection(self, interaction: discord.Interaction, results: List[Dict], media_type: str):
        """Zeigt Medienauswahl-Menü"""
        options = []
        for item in results[:5]:
            label = item['title']
            
            # Zusatzinformationen für Label
            if media_type in ["movie", "tv_show"] and item.get('release_date'):
                year = item['release_date'][:4] if item['release_date'] != "Unbekannt" else ''
                if year:
                    label += f" ({year})"
            elif media_type == "video_game" and item.get('release_date'):
                label += f" ({item['release_date']})"
            elif media_type == "board_game" and item.get('release_date'):
                label += f" ({item['release_date']})"
            elif media_type in ["music_cd", "vinyl"] and item.get('artists'):
                label = f"{item['artists']} - {label}"
            
            description = item.get('description', '')[:100] + "..." if len(item.get('description', '')) > 100 else item.get('description', '')
            
            options.append(
                discord.SelectOption(
                    label=label[:100],
                    value=item["external_id"],
                    description=description
                )
            )
        
        select = discord.ui.Select(placeholder=f"Wähle {MEDIA_TYPES.get(media_type, {}).get('name', 'Medium')} aus...", options=options)
        
        async def select_callback(select_interaction: discord.Interaction):
            if select_interaction.user.id != interaction.user.id:
                await select_interaction.response.send_message("❌ Du kannst diese Auswahl nicht verwenden.", ephemeral=True)
                return
            
            selected_item = next((item for item in results if item["external_id"] == select.values[0]), None)
            if not selected_item:
                await select_interaction.response.send_message("❌ Medium nicht gefunden.", ephemeral=True)
                return
            
            due_date = date.today() + timedelta(days=get_config('media_settings.due_period_days', 14))
            try:
                await media_repo.borrow_media(
                    select_interaction.user.id,
                    str(select_interaction.user),
                    media_type,
                    selected_item,
                    due_date
                )
                
                embed = self._create_media_embed(selected_item, due_date, media_type, "ausgeliehen")
                await select_interaction.response.edit_message(content=None, embed=embed, view=None)
                
            except Exception as e:
                logger.error(f"Fehler beim Ausleihen: {e}")
                await select_interaction.response.edit_message(content="❌ Ein Fehler ist aufgetreten.", view=None)
        
        select.callback = select_callback
        view = discord.ui.View()
        view.add_item(select)
        
        embed = discord.Embed(
            title=f"{MEDIA_TYPES.get(media_type, {}).get('name', 'Medium')} Auswahl",
            description=f"Gefundene {MEDIA_TYPES.get(media_type, {}).get('name', 'Medien')}:",
            color=self._get_media_color(media_type)
        )
        
        await interaction.followup.send(embed=embed, view=view)
    
    async def _return_media(self, interaction: discord.Interaction, media_type: str, external_id: str):
        """Gibt ein Medium zurück"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            media = await media_repo.return_media(interaction.user.id, media_type, external_id)
            
            if not media:
                await interaction.followup.send(f"❌ Du hast dieses {MEDIA_TYPES.get(media_type, {}).get('name', 'Medium')} nicht ausgeliehen.")
                return
                
            await interaction.followup.send(f"✅ {MEDIA_TYPES.get(media_type, {}).get('name', 'Medium')} '{media['title']}' erfolgreich zurückgegeben.")
            
        except Exception as e:
            logger.error(f"Fehler beim Zurückgeben: {e}")
            await interaction.followup.send("❌ Ein Fehler ist aufgetreten. Bitte versuche es später erneut.")
    
    async def _my_media(self, interaction: discord.Interaction, media_type: str = None):
        """Zeigt ausgeliehene Medien an"""
        await interaction.response.defer(ephemeral=True)
        
        media_items = await media_repo.get_user_media(interaction.user.id, media_type)
        
        if not media_items:
            if media_type:
                await interaction.followup.send(f"📭 Du hast aktuell keine {MEDIA_TYPES.get(media_type, {}).get('name', 'Medien')} ausgeliehen.")
            else:
                await interaction.followup.send("📭 Du hast aktuell keine Medien ausgeliehen.")
            return
        
        embed = discord.Embed(
            title="📚 Meine ausgeliehenen Medien",
            color=discord.Color.blue()
        )
        
        for i, item in enumerate(media_items, 1):
            media_type_emoji = MEDIA_TYPES.get(item['media_type'], {}).get('name', '📁').split(' ')[0]
            status = "🔴 FÄLLIG" if item["due_date"] < date.today() else "🟢 In Ordnung"
            embed.add_field(
                name=f"{i}. {media_type_emoji} {item['title']}",
                value=f"Rückgabe: {item['due_date'].strftime('%d.%m.%Y')} - {status}",
                inline=False
            )
        
        await interaction.followup.send(embed=embed)
    
    async def _search_music(self, interaction: discord.Interaction, query: str, search_type: str):
        """Suchfunktion für Musik"""
        await interaction.response.defer(ephemeral=True)
        
        if not self._is_api_enabled('spotify'):
            await interaction.followup.send("❌ Spotify API ist deaktiviert.")
            return
        
        music_results = await api_handler.search_music(query, search_type)
        if not music_results:
            await interaction.followup.send("❌ Keine Musik gefunden.")
            return
        
        embed = discord.Embed(
            title=f"🎵 Suchergebnisse für '{query}'",
            color=discord.Color.green()
        )
        
        for i, music in enumerate(music_results[:3], 1):
            value = f"**Künstler:** {music.get('artists', 'Unbekannt')}\n"
            if music.get('release_date'):
                value += f"**Erscheinungsjahr:** {music['release_date'][:4]}\n"
            if music.get('duration'):
                minutes = music['duration'] // 60
                seconds = music['duration'] % 60
                value += f"**Dauer:** {minutes}:{seconds:02d}\n"
            
            value += f"**ID:** {music['external_id']}"
            
            embed.add_field(
                name=f"{i}. {music['title']}",
                value=value,
                inline=False
            )
        
        embed.set_footer(text="Verwende /borrow_music um Musik auszuleihen")
        await interaction.followup.send(embed=embed)
    
    async def _search_video_games(self, interaction: discord.Interaction, query: str):
        """Suchfunktion für Videospiele"""
        await interaction.response.defer(ephemeral=True)
        
        if not self._is_api_enabled('igdb'):
            await interaction.followup.send("❌ IGDB API ist deaktiviert.")
            return
        
        games = await api_handler.search_video_games(query)
        if not games:
            await interaction.followup.send("❌ Keine Videospiele gefunden.")
            return
        
        embed = discord.Embed(
            title=f"🎮 Suchergebnisse für '{query}'",
            color=discord.Color.purple()
        )
        
        for i, game in enumerate(games[:3], 1):
            value = f"**Erscheinungsjahr:** {game.get('release_date', 'Unbekannt')}\n"
            value += f"**Bewertung:** ⭐ {game.get('rating', 0)}/100\n"
            if game.get('genres'):
                value += f"**Genres:** {game['genres']}\n"
            if game.get('platforms'):
                value += f"**Plattformen:** {game['platforms']}\n"
            if game.get('publisher'):
                value += f"**Entwickler:** {game['publisher']}\n"
            
            value += f"**ID:** {game['external_id']}"
            
            embed.add_field(
                name=f"{i}. {game['title']}",
                value=value,
                inline=False
            )
        
        embed.set_footer(text="Verwende /borrow_video_game um ein Spiel auszuleihen")
        await interaction.followup.send(embed=embed)
    
    async def _search_board_games(self, interaction: discord.Interaction, query: str):
        """Suchfunktion für Brettspiele"""
        await interaction.response.defer(ephemeral=True)
        
        if not self._is_api_enabled('board_game_atlas'):
            await interaction.followup.send("❌ Board Game Atlas API ist deaktiviert.")
            return
        
        games = await api_handler.search_board_games(query)
        if not games:
            await interaction.followup.send("❌ Keine Brettspiele gefunden.")
            return
        
        embed = discord.Embed(
            title=f"♟️ Suchergebnisse für '{query}'",
            color=discord.Color.orange()
        )
        
        for i, game in enumerate(games[:3], 1):
            value = f"**Erscheinungsjahr:** {game.get('release_date', 'Unbekannt')}\n"
            value += f"**Bewertung:** ⭐ {game.get('rating', 0)}/5\n"
            if game.get('players'):
                value += f"**Spieler:** {game['players']}\n"
            if game.get('duration'):
                value += f"**Spieldauer:** {game['duration']} Min.\n"
            if game.get('publisher'):
                value += f"**Verlag:** {game['publisher']}\n"
            
            value += f"**ID:** {game['external_id']}"
            
            embed.add_field(
                name=f"{i}. {game['title']}",
                value=value,
                inline=False
            )
        
        embed.set_footer(text="Verwende /borrow_board_game um ein Spiel auszuleihen")
        await interaction.followup.send(embed=embed)
    
    async def _search_comics(self, interaction: discord.Interaction, query: str):
        """Suchfunktion für Comics"""
        await interaction.response.defer(ephemeral=True)
        
        if not self._is_api_enabled('comic_vine'):
            await interaction.followup.send("❌ Comic Vine API ist deaktiviert.")
            return
        
        comics = await api_handler.search_comics(query)
        if not comics:
            await interaction.followup.send("❌ Keine Comics gefunden.")
            return
        
        embed = discord.Embed(
            title=f"🦸 Suchergebnisse für '{query}'",
            color=discord.Color.red()
        )
        
        for i, comic in enumerate(comics[:3], 1):
            value = f"**Erscheinungsjahr:** {comic.get('release_date', 'Unbekannt')}\n"
            if comic.get('publisher'):
                value += f"**Verlag:** {comic['publisher']}\n"
            
            value += f"**ID:** {comic['external_id']}"
            
            embed.add_field(
                name=f"{i}. {comic['title']}",
                value=value,
                inline=False
            )
        
        embed.set_footer(text="Verwende /borrow_comic um einen Comic auszuleihen")
        await interaction.followup.send(embed=embed)
    
    def _create_media_embed(self, media_info: dict, due_date: date, media_type: str, action: str) -> discord.Embed:
        """Erstellt ein Embed für Medien-Aktionen"""
        media_type_display = MEDIA_TYPES.get(media_type, {}).get('name', "Medium")
        emoji = media_type_display.split(' ')[0]
        
        color = self._get_media_color(media_type)
        title = f"{emoji} {media_type_display} {action}"
        
        embed = discord.Embed(title=title, description=f"**{media_info['title']}**", color=color)
        
        if media_info.get('subtitle'):
            embed.add_field(name="Untertitel", value=media_info['subtitle'], inline=False)
        
        if media_info.get('authors'):
            embed.add_field(name="Autoren", value=media_info['authors'], inline=True)
        
        if media_info.get('artists'):
            embed.add_field(name="Künstler", value=media_info['artists'], inline=True)
        
        if media_info.get('release_date'):
            embed.add_field(name="Erscheinungsjahr", value=media_info['release_date'][:4], inline=True)
        
        if media_info.get('rating') and media_info['rating'] > 0:
            embed.add_field(name="Bewertung", value=f"⭐ {media_info['rating']}/10", inline=True)
        
        if media_info.get('genres'):
            embed.add_field(name="Genres", value=media_info['genres'], inline=False)
        
        if media_info.get('platforms'):
            embed.add_field(name="Plattformen", value=media_info['platforms'], inline=True)
        
        if media_info.get('players'):
            embed.add_field(name="Spieler", value=media_info['players'], inline=True)
        
        if media_info.get('publisher'):
            embed.add_field(name="Verlag/Entwickler", value=media_info['publisher'], inline=False)
        
        if action == "ausgeliehen":
            embed.add_field(name="Rückgabedatum", value=due_date.strftime("%d.%m.%Y"), inline=True)
        
        if media_info.get('cover'):
            embed.set_thumbnail(url=media_info['cover'])
        
        return embed
    
    def _get_media_color(self, media_type: str) -> discord.Color:
        """Gibt die Farbe für den Medientyp zurück"""
        colors = {
            'book': discord.Color.blue(),
            'movie': discord.Color.purple(),
            'tv_show': discord.Color.dark_purple(),
            'music_cd': discord.Color.green(),
            'vinyl': discord.Color.dark_green(),
            'song': discord.Color.green(),
            'video_game': discord.Color.purple(),
            'board_game': discord.Color.orange(),
            'comic': discord.Color.red(),
            'magazine': discord.Color.light_grey(),
        }
        return colors.get(media_type, discord.Color.blue())
    
    def _is_media_type_enabled(self, media_type: str) -> bool:
        """Prüft ob eine Medienart aktiviert ist"""
        return MEDIA_TYPES.get(media_type, {}).get('enabled', True)
    
    def _is_api_enabled(self, api_name: str) -> bool:
        """Prüft ob eine API aktiviert ist"""
        return get_config(f'apis.{api_name}.enabled', True)
    
    async def _check_loan_limit(self, user_id: int) -> bool:
        """Prüft ob der Benutzer das Ausleihlimit erreicht hat"""
        max_loans = get_config('media_settings.max_loans_per_user', 10)
        user_media = await media_repo.get_user_media(user_id)
        return len(user_media) < max_loans

class AdminCommands:
    """Admin-Commands für Bot-Management"""
    
    def __init__(self, tree: app_commands.CommandTree, bot: discord.Client):
        self.tree = tree
        self.bot = bot
        self._register_commands()
    
    def _register_commands(self):
        """Registriert Admin-Commands"""
        
        @self.tree.command(name="bot_status", description="Zeigt Bot-Status und Statistiken")
        @app_commands.default_permissions(administrator=True)
        async def bot_status(interaction: discord.Interaction):
            await self._show_bot_status(interaction)
        
        @self.tree.command(name="reload_config", description="Lädt die Konfiguration neu")
        @app_commands.default_permissions(administrator=True)
        async def reload_config(interaction: discord.Interaction):
            await self._reload_config(interaction)
        
        @self.tree.command(name="validate_config", description="Validiert die aktuelle Konfiguration")
        @app_commands.default_permissions(administrator=True)
        async def validate_config(interaction: discord.Interaction):
            await self._validate_config(interaction)
        
        @self.tree.command(name="system_info", description="Zeigt Systeminformationen")
        @app_commands.default_permissions(administrator=True)
        async def system_info(interaction: discord.Interaction):
            await self._show_system_info(interaction)
        
        @self.tree.command(name="force_return", description="Erzwingt die Rückgabe eines Mediums")
        @app_commands.default_permissions(administrator=True)
        @app_commands.describe(
            user_id="Discord ID des Benutzers",
            media_type="Typ des Mediums",
            external_id="Externe ID des Mediums"
        )
        async def force_return(interaction: discord.Interaction, user_id: str, media_type: str, external_id: str):
            await self._force_return(interaction, user_id, media_type, external_id)
    
    async def _show_bot_status(self, interaction: discord.Interaction):
        """Zeigt Bot-Status"""
        await interaction.response.defer(ephemeral=True)
        
        # Statistiken sammeln
        stats = await dashboard_repo.get_statistics()
        api_status = await ConfigValidation.validate_apis_config(interaction)
        
        embed = discord.Embed(
            title="🤖 Bot Status",
            color=discord.Color.blue()
        )
        
        # Bot-Informationen
        embed.add_field(
            name="Bot",
            value=f"**Name:** {self.bot.user.name}\n"
                  f"**ID:** {self.bot.user.id}\n"
                  f"**Server:** {len(self.bot.guilds)}",
            inline=True
        )
        
        # System-Informationen
        embed.add_field(
            name="System",
            value=f"**Aktive Ausleihen:** {stats['total_media']}\n"
                  f"**Überfällig:** {stats['overdue_count']}\n"
                  f"**Aktive Nutzer:** {len(stats['top_users'])}",
            inline=True
        )
        
        # API-Status
        api_status_text = ""
        for api_name, status in api_status.items():
            api_status_text += f"**{api_name}:** {'✅' if status else '❌'}\n"
        
        embed.add_field(
            name="APIs",
            value=api_status_text,
            inline=True
        )
        
        # Konfigurations-Status
        errors = config_manager.validate_config()
        config_status = "✅ Valide" if not errors else f"❌ {len(errors)} Fehler"
        
        embed.add_field(
            name="Konfiguration",
            value=f"**Status:** {config_status}\n"
                  f"**Letztes Update:** {self._get_config_age()}",
            inline=True
        )
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    async def _reload_config(self, interaction: discord.Interaction):
        """Lädt die Konfiguration neu"""
        await interaction.response.defer(ephemeral=True)
        
        # Konfiguration neu laden
        old_config = config_manager.get_all()
        config_manager._load_config()  # Direkter Aufruf für Neuladung
        
        embed = discord.Embed(
            title="🔄 Konfiguration neu geladen",
            color=discord.Color.green()
        )
        
        # Prüfe auf Änderungen
        new_config = config_manager.get_all()
        changes = self._find_config_changes(old_config, new_config)
        
        if changes:
            embed.add_field(
                name="⚠️ Geänderte Einstellungen",
                value="\n".join([f"• {change}" for change in changes]),
                inline=False
            )
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    async def _validate_config(self, interaction: discord.Interaction):
        """Validiert die Konfiguration"""
        await interaction.response.defer(ephemeral=True)
        
        errors = config_manager.validate_config()
        api_status = await ConfigValidation.validate_apis_config(interaction)
        db_status = await ConfigValidation.validate_database_config(interaction)
        
        embed = discord.Embed(
            title="🔍 Konfigurations-Validierung",
            color=discord.Color.green() if not errors else discord.Color.red()
        )
        
        if not errors:
            embed.add_field(
                name="✅ Grundkonfiguration",
                value="Alle erforderlichen Einstellungen sind korrekt.",
                inline=False
            )
        else:
            error_text = "\n".join([f"• **{key}**: {error}" for key, error in errors.items()])
            embed.add_field(
                name="❌ Konfigurationsfehler",
                value=error_text,
                inline=False
            )
        
        # API-Status
        api_text = ""
        for api_name, status in api_status.items():
            api_text += f"**{api_name}:** {'✅ Aktiv' if status else '❌ Inaktiv'}\n"
        
        embed.add_field(
            name="🔐 API-Status",
            value=api_text,
            inline=True
        )
        
        # Datenbank-Status
        db_text = "✅ Verbunden" if db_status else "❌ Fehler"
        embed.add_field(
            name="💾 Datenbank",
            value=db_text,
            inline=True
        )
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    async def _show_system_info(self, interaction: discord.Interaction):
        """Zeigt Systeminformationen"""
        await interaction.response.defer(ephemeral=True)
        
        import psutil
        import platform
        
        # System-Informationen
        system_info = {
            "Python": platform.python_version(),
            "Discord.py": discord.__version__,
            "Betriebssystem": f"{platform.system()} {platform.release()}",
            "CPU Auslastung": f"{psutil.cpu_percent()}%",
            "RAM Auslastung": f"{psutil.virtual_memory().percent}%",
            "Bot Laufzeit": self._get_uptime()
        }
        
        embed = discord.Embed(
            title="💻 Systeminformationen",
            color=discord.Color.blue()
        )
        
        for key, value in system_info.items():
            embed.add_field(name=key, value=value, inline=True)
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    async def _force_return(self, interaction: discord.Interaction, user_id: str, media_type: str, external_id: str):
        """Erzwingt die Rückgabe eines Mediums"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            user_id_int = int(user_id)
            media = await media_repo.return_media(user_id_int, media_type, external_id)
            
            if not media:
                await interaction.followup.send("❌ Medium nicht gefunden oder nicht ausgeliehen.")
                return
            
            # Logge die erzwungene Rückgabe
            await media_repo.return_media(user_id_int, media_type, external_id)
            
            embed = discord.Embed(
                title="✅ Rückgabe erzwungen",
                description=f"Medium '{media['title']}' wurde von User {user_id} zurückgegeben.",
                color=discord.Color.green()
            )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except ValueError:
            await interaction.followup.send("❌ Ungültige User ID.", ephemeral=True)
        except Exception as e:
            logger.error(f"Fehler bei erzwungener Rückgabe: {e}")
            await interaction.followup.send("❌ Ein Fehler ist aufgetreten.", ephemeral=True)
    
    def _get_config_age(self) -> str:
        """Gibt das Alter der Konfigurationsdatei zurück"""
        import os
        from datetime import datetime
        
        try:
            stat = os.stat('bot_config.json')
            mod_time = datetime.fromtimestamp(stat.st_mtime)
            age = datetime.now() - mod_time
            
            if age.days > 0:
                return f"vor {age.days} Tagen"
            elif age.seconds > 3600:
                return f"vor {age.seconds // 3600} Stunden"
            else:
                return f"vor {age.seconds // 60} Minuten"
        except:
            return "Unbekannt"
    
    def _find_config_changes(self, old: Dict, new: Dict, path: str = "") -> List[str]:
        """Findet Änderungen zwischen zwei Konfigurationen"""
        changes = []
        
        for key in set(old.keys()) | set(new.keys()):
            current_path = f"{path}.{key}" if path else key
            
            if key not in old:
                changes.append(f"➕ {current_path}: {new[key]}")
            elif key not in new:
                changes.append(f"➖ {current_path} entfernt")
            elif isinstance(old[key], dict) and isinstance(new[key], dict):
                changes.extend(self._find_config_changes(old[key], new[key], current_path))
            elif old[key] != new[key]:
                changes.append(f"✏️ {current_path}: {old[key]} → {new[key]}")
        
        return changes
    
    def _get_uptime(self) -> str:
        """Gibt die Bot-Laufzeit zurück"""
        # Diese Funktion würde normalerweise den Startzeitpunkt tracken
        # Für jetzt geben wir einen Platzhalter zurück
        return "Noch nicht implementiert"

class ReminderTasks:
    """Aufgaben für Erinnerungen"""
    
    def __init__(self, bot: discord.Client):
        self.bot = bot
        self.remind_due_media.start()
    
    @tasks.loop(hours=24)
    async def remind_due_media(self):
        """Sendet Erinnerungen für fällige Medien"""
        if not self.bot.is_ready():
            return
            
        reminder_date = date.today() + timedelta(days=get_config('media_settings.remind_days_before', 1))
        
        try:
            rows = await reminder_repo.get_due_media(reminder_date)
            
            for row in rows:
                user = self.bot.get_user(row["user_id"])
                if user and get_config('notifications.enable_dm_reminders', True):
                    try:
                        media_type_display = MEDIA_TYPES.get(row['media_type'], {}).get('name', 'Medium')
                        emoji = media_type_display.split(' ')[0]
                        
                        embed = discord.Embed(
                            title=f"⏰ Erinnerung: {media_type_display}-Rückgabe",
                            description=f"Dein {media_type_display.lower()} **{row['title']}** ist am **{row['due_date'].strftime('%d.%m.%Y')}** fällig.",
                            color=discord.Color.orange()
                        )
                        
                        await user.send(embed=embed)
                        await reminder_repo.mark_media_reminded(row["user_id"], row["title"], row["media_type"])
                        logger.info(f"Erinnerung gesendet an User {row['user_id']} für {row['media_type']} {row['title']}")
                        
                    except discord.Forbidden:
                        logger.warning(f"Konnte DM nicht an User {row['user_id']} senden")
                    except Exception as e:
                        logger.error(f"Fehler beim Senden der Erinnerung an User {row['user_id']}: {e}")
        
        except Exception as e:
            logger.error(f"Fehler in remind_due_media Task: {e}")
    
    @remind_due_media.before_loop
    async def before_reminder(self):
        """Wartet bis der Bot ready ist"""
        await self.bot.wait_until_ready()

class DiscordBot:
    """Haupt-Bot Klasse mit erweitertem Management"""
    
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
        """Richtet die Discord Intents ein"""
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        return intents
    
    def _register_events(self):
        """Registriert Bot Event Handler"""
        
        @self.bot.event
        async def on_ready():
            """Wird aufgerufen wenn der Bot ready ist"""
            try:
                self.start_time = discord.utils.utcnow()
                
                if get_config('discord.auto_sync_commands', True):
                    await self.tree.sync()
                    logger.info("✅ Discord Commands synchronisiert")
                
                self.reminder_tasks = ReminderTasks(self.bot)
                
                logger.info(f"✅ Bot erfolgreich eingeloggt als {self.bot.user} (ID: {self.bot.user.id})")
                logger.info(f"📊 Bot ist auf {len(self.bot.guilds)} Servern")
                
                # Konfigurations-Status loggen
                errors = config_manager.validate_config()
                if errors:
                    logger.warning(f"⚠️ Konfigurationsfehler: {len(errors)} Probleme gefunden")
                    for key, error in errors.items():
                        logger.warning(f"  - {key}: {error}")
                else:
                    logger.info("✅ Konfiguration ist valide")
                
                # API-Status loggen
                api_config = get_config('apis', {})
                enabled_apis = [name for name, config in api_config.items() if config.get('enabled', False)]
                logger.info(f"🔌 Aktive APIs: {', '.join(enabled_apis) if enabled_apis else 'Keine'}")
                
            except Exception as e:
                logger.error(f"❌ Fehler beim Start: {e}")
        
        @self.bot.event
        async def on_guild_join(guild):
            """Wird aufgerufen wenn der Bot einem Server beitritt"""
            logger.info(f"➕ Bot ist Server '{guild.name}' (ID: {guild.id}) beigetreten")
            
            # Sende Willkommensnachricht an Standard-Kanal
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
            """Wird aufgerufen wenn der Bot einen Server verlässt"""
            logger.info(f"➖ Bot hat Server '{guild.name}' (ID: {guild.id}) verlassen")
        
        @self.bot.event
        async def on_command_error(interaction: discord.Interaction, error):
            """Behandelt Command-Fehler"""
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
                    "❌ Ein unerwarteter Fehler ist aufgetreten.",
                    ephemeral=True
                )
    
    async def start(self):
        """Startet den Bot"""
        # Validiere Konfiguration
        validate_required()
        
        # Datenbank initialisieren
        await db.create_pool()
        await db.init_tables()
        
        # Bot starten
        await self.bot.start(get_config('discord.token'))

def create_flask_app(bot_instance):
    """Einfache Flask-App für Kompatibilität"""
    from flask import Flask, jsonify
    
    app = Flask(__name__)
    
    @app.route("/status")
    def status():
        return jsonify({
            "status": "running", 
            "bot": "online" if bot_instance.is_ready() else "offline",
            "supported_media": [mt['name'] for mt in MEDIA_TYPES.values()]
        })
    
    @app.route("/health")
    def health():
        return jsonify({"status": "healthy"})
    
    return app
