# bot.py
import os
import asyncio
from datetime import date, datetime, timedelta
from typing import Optional

import aiohttp
import aiomysql
import discord
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv
import subprocess

# Mit Argumenten

load_dotenv()

# ---- Config from .env ----
TOKEN = os.getenv("DISCORD_TOKEN")  # Never hardcode tokens!
GB_API_KEY = os.getenv("GOOGLE_BOOKS_API_KEY")

MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", 3306))
MYSQL_USER = os.getenv("MYSQL_USER")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
MYSQL_DB = os.getenv("MYSQL_DB", "book_db")

# Reminder settings
REMIND_DAYS_BEFORE = int(os.getenv("REMIND_DAYS_BEFORE", 1))  # notify 1 day before by default
DUE_PERIOD_DAYS = int(os.getenv("DUE_PERIOD_DAYS", 14))      # loan length

if not TOKEN:
    raise SystemExit("DISCORD_TOKEN missing in .env")

# Intents and bot
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

db_pool: Optional[aiomysql.Pool] = None

# ---------- Database Helpers ----------
async def create_pool() -> None:
    """Create a connection pool to MySQL database."""
    global db_pool
    db_pool = await aiomysql.create_pool(
        host=MYSQL_HOST, 
        port=MYSQL_PORT,
        user=MYSQL_USER, 
        password=MYSQL_PASSWORD,
        db=MYSQL_DB, 
        autocommit=True, 
        minsize=1, 
        maxsize=10,
        cursorclass=aiomysql.DictCursor
    )

async def init_db_tables() -> None:
    """Initialize database tables if they don't exist."""
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS books (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    username VARCHAR(100),
                    isbn VARCHAR(32),
                    title VARCHAR(255),
                    authors TEXT,
                    description LONGTEXT,
                    cover TEXT,
                    due_date DATE,
                    reminded BOOLEAN DEFAULT FALSE,
                    created_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE KEY uq_user_isbn (user_id, isbn)
                )
            """) 
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS rueckgabe_log (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    moderator_id BIGINT,
                    user_id BIGINT,
                    isbn VARCHAR(32),
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

# ---------- Google Books API ----------
async def fetch_book_by_isbn(isbn: str) -> Optional[dict]:
    """Fetch book details from Google Books API by ISBN."""
    url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}"
    if GB_API_KEY:
        url += f"&key={GB_API_KEY}"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=15) as response:
                if response.status != 200:
                    return None
                data = await response.json()
                
                if not data.get("items"):
                    return None
                    
                info = data["items"][0]["volumeInfo"]
                return {
                    "title": info.get("title", "Unbekannt"),
                    "authors": info.get("authors", []),
                    "description": info.get("description", ""),
                    "cover": info.get("imageLinks", {}).get("thumbnail")
                }
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        print(f"Error fetching book by ISBN {isbn}: {e}")
        return None

async def fetch_book_by_title(title: str) -> Optional[dict]:
    """Fetch book details from Google Books API by title."""
    url = f"https://www.googleapis.com/books/v1/volumes?q=intitle:{title}"
    if GB_API_KEY:
        url += f"&key={GB_API_KEY}"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=15) as response:
                if response.status != 200:
                    return None
                data = await response.json()
                
                if not data.get("items"):
                    return None
                    
                info = data["items"][0]["volumeInfo"]
                return {
                    "title": info.get("title", "Unbekannt"),
                    "authors": info.get("authors", []),
                    "description": info.get("description", ""),
                    "cover": info.get("imageLinks", {}).get("thumbnail")
                }
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        print(f"Error fetching book by title {title}: {e}")
        return None

# ---------- Utility Functions ----------
def color_for_days_left(days_left: int) -> discord.Color:
    """Return a color based on days remaining until due date."""
    if days_left < 0:
        return discord.Color.red()
    if days_left <= 3:
        return discord.Color.orange()
    return discord.Color.green()

def format_description(description: Optional[str], max_length: int = 800) -> str:
    """Format book description with length limit."""
    if not description:
        return ""
    if len(description) > max_length:
        return description[:max_length] + "..."
    return description

def make_embed_from_row(row: dict) -> discord.Embed:
    """Create a Discord embed from a database row."""
    due_date = row["due_date"]
    if isinstance(due_date, datetime):
        due_date = due_date.date()
    
    days_left = (due_date - date.today()).days if due_date else None
    color = color_for_days_left(days_left if days_left is not None else 999)
    
    embed = discord.Embed(
        title=row["title"] or "Unbekannt",
        description=format_description(row["description"]),
        color=color
    )
    
    embed.add_field(name="Autor(en)", value=row["authors"] or "Unbekannt", inline=False)
    embed.add_field(name="Fällig am", value=due_date.strftime("%d.%m.%Y") if due_date else "Unbekannt")
    embed.add_field(name="Tage übrig", value=str(days_left) if days_left is not None else "—")
    
    if row.get("cover"):
        embed.set_thumbnail(url=row["cover"])
    
    embed.set_footer(text=f"ISBN: {row['isbn']} • Ausgeliehen von {row['username']}")
    return embed

# ---------- Slash Commands ----------
@tree.command(name="borrow", description="Leihe ein Buch per ISBN aus (beispiel: /borrow isbn:123...)")
@app_commands.describe(isbn="ISBN des Buches")
async def borrow(interaction: discord.Interaction, isbn: str) -> None:
    """Borrow a book by ISBN."""
    await interaction.response.defer(ephemeral=True)
    
    # Validate ISBN format (basic check)
    isbn = isbn.strip().replace("-", "").replace(" ", "")
    if not isbn.isdigit() or len(isbn) not in (10, 13):
        await interaction.followup.send("❌ Ungültige ISBN. Bitte überprüfen Sie die eingegebene Nummer.", ephemeral=True)
        return
    
    book_info = await fetch_book_by_isbn(isbn)
    if not book_info:
        await interaction.followup.send("❌ Kein Buch mit dieser ISBN gefunden.", ephemeral=True)
        return

    due_date = date.today() + timedelta(days=DUE_PERIOD_DAYS)
    username = str(interaction.user)
    
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    INSERT INTO books 
                    (user_id, username, isbn, title, authors, description, cover, due_date)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    interaction.user.id, 
                    username, 
                    isbn, 
                    book_info["title"], 
                    ", ".join(book_info["authors"]), 
                    book_info["description"], 
                    book_info["cover"], 
                    due_date
                ))
    except aiomysql.IntegrityError:
        await interaction.followup.send("⚠️ Du hast dieses Buch bereits ausgeliehen.", ephemeral=True)
        return
    except Exception as e:
        print(f"Database error in borrow command: {e}")
        await interaction.followup.send("❌ Ein Fehler ist aufgetreten. Bitte versuchen Sie es später erneut.", ephemeral=True)
        return

    embed = discord.Embed(
        title="✅ Buch ausgeliehen", 
        description=f"**{book_info['title']}**", 
        color=discord.Color.blue()
    )
    embed.add_field(name="Autor(en)", value=", ".join(book_info["authors"]) if book_info["authors"] else "Unbekannt")
    embed.add_field(name="Fällig am", value=due_date.strftime("%d.%m.%Y"))
    
    if book_info["cover"]:
        embed.set_thumbnail(url=book_info["cover"])
    
    await interaction.followup.send(embed=embed, ephemeral=False)

@tree.command(name="returnbook", description="Gib ein Buch zurück (ISBN)")
@app_commands.describe(isbn="ISBN des zurückzugebenden Buches")
async def return_book(interaction: discord.Interaction, isbn: str) -> None:
    """Return a borrowed book."""
    await interaction.response.defer(ephemeral=True)
    
    isbn = isbn.strip().replace("-", "").replace(" ", "")
    
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                # Check if user has this book borrowed
                await cur.execute("""
                    SELECT id FROM books 
                    WHERE user_id=%s AND isbn=%s
                """, (interaction.user.id, isbn))
                
                if not await cur.fetchone():
                    await interaction.followup.send("❌ Du hast dieses Buch nicht ausgeliehen.", ephemeral=True)
                    return
                
                # Delete the book and log the return
                await cur.execute("""
                    DELETE FROM books 
                    WHERE user_id=%s AND isbn=%s
                """, (interaction.user.id, isbn))
                
                await cur.execute("""
                    INSERT INTO rueckgabe_log 
                    (moderator_id, user_id, isbn) 
                    VALUES (%s, %s, %s)
                """, (interaction.user.id, interaction.user.id, isbn))
                
        await interaction.followup.send("✅ Buch erfolgreich zurückgegeben.", ephemeral=True)
    except Exception as e:
        print(f"Error in return_book command: {e}")
        await interaction.followup.send("❌ Ein Fehler ist aufgetreten. Bitte versuchen Sie es später erneut.", ephemeral=True)

@tree.command(name="mybooks", description="Zeigt deine ausgeliehenen Bücher")
async def my_books(interaction: discord.Interaction) -> None:
    """List all books borrowed by the user."""
    await interaction.response.defer(ephemeral=True)
    
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("""
                    SELECT * FROM books 
                    WHERE user_id=%s
                """, (interaction.user.id,))
                books = await cur.fetchall()
        
        if not books:
            await interaction.followup.send("📭 Du hast aktuell keine Bücher ausgeliehen.", ephemeral=True)
            return
            
        for book in books:
            if isinstance(book["due_date"], datetime):
                book["due_date"] = book["due_date"].date()
            await interaction.followup.send(embed=make_embed_from_row(book), ephemeral=True)
    except Exception as e:
        print(f"Error in my_books command: {e}")
        await interaction.followup.send("❌ Ein Fehler ist aufgetreten. Bitte versuchen Sie es später erneut.", ephemeral=True)

@tree.command(name="listloans", description="(Admin) Liste aller Ausleihen mit Fälligkeit")
async def list_loans(interaction: discord.Interaction) -> None:
    """List all current loans (admin only)."""
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message(
            "❌ Du brauchst die Berechtigung `Server verwalten` für diesen Befehl.",
            ephemeral=True
        )
        return
    
    await interaction.response.defer(ephemeral=True)
    
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("""
                    SELECT * FROM books 
                    ORDER BY due_date ASC
                """)
                loans = await cur.fetchall()
        
        if not loans:
            await interaction.followup.send("Keine Ausleihen vorhanden.", ephemeral=True)
            return
            
        embed = discord.Embed(
            title="📚 Alle Ausleihen", 
            color=discord.Color.blurple()
        )
        
        for loan in loans:
            if isinstance(loan["due_date"], datetime):
                loan["due_date"] = loan["due_date"].date()
                
            days_left = (loan["due_date"] - date.today()).days if loan["due_date"] else None
            
            if days_left is None:
                status = "unbekannt"
            elif days_left < 0:
                status = "überfällig"
            elif days_left <= 3:
                status = "bald fällig"
            else:
                status = "ok"
                
            embed.add_field(
                name=f"{loan['title']} — {loan['username']}",
                value=(
                    f"ISBN: {loan['isbn']}\n"
                    f"Fällig: {loan['due_date']} ({days_left} Tage) — {status}"
                ),
                inline=False
            )
        
        await interaction.followup.send(embed=embed, ephemeral=False)
    except Exception as e:
        print(f"Error in list_loans command: {e}")
        await interaction.followup.send("❌ Ein Fehler ist aufgetreten. Bitte versuchen Sie es später erneut.", ephemeral=True)

# ---------- Reminder Task ----------
@tasks.loop(hours=24)
async def reminder_loop() -> None:
    """Daily task to remind users about due books."""
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("""
                    SELECT * FROM books
                    WHERE reminded = FALSE
                """)
                books = await cur.fetchall()
                
                for book in books:
                    due_date = book["due_date"]
                    if isinstance(due_date, datetime):
                        due_date = due_date.date()
                    
                    days_left = (due_date - date.today()).days if due_date else None
                    
                    if days_left is None:
                        continue
                        
                    if days_left <= REMIND_DAYS_BEFORE:
                        try:
                            user = await bot.fetch_user(book["user_id"])
                            embed = discord.Embed(
                                title="🔔 Buch-Rückgabe Erinnerung",
                                color=color_for_days_left(days_left)
                            )
                            embed.add_field(name="Titel", value=book["title"], inline=False)
                            embed.add_field(name="Fällig am", value=due_date.strftime("%d.%m.%Y"))
                            
                            if days_left < 0:
                                embed.description = "Ihr Buch ist überfällig!"
                            elif days_left == 0:
                                embed.description = "Ihr Buch ist heute fällig!"
                            else:
                                embed.description = f"Ihr Buch ist in {days_left} Tagen fällig!"
                            
                            if book.get("cover"):
                                embed.set_thumbnail(url=book["cover"])
                            
                            await user.send(embed=embed)
                            await cur.execute("""
                                UPDATE books 
                                SET reminded=TRUE 
                                WHERE id=%s
                            """, (book["id"],))
                            await conn.commit()
                            
                        except discord.Forbidden:
                            print(f"Could not send DM to user {book['user_id']} (disabled DMs)")
                        except discord.NotFound:
                            print(f"User {book['user_id']} not found")
                        except Exception as e:
                            print(f"Error sending reminder to user {book['user_id']}: {e}")
    except Exception as e:
        print(f"Error in reminder loop: {e}")

@reminder_loop.before_loop
async def before_reminder() -> None:
    """Wait for bot to be ready before starting reminder loop."""
    await bot.wait_until_ready()

# ---------- Bot Events ----------
@bot.event
async def on_ready() -> None:
    """Called when the bot is ready."""
    print(f"Bot ready as {bot.user} (ID {bot.user.id})")
    
    # Initialize database
    try:
        await create_pool()
        await init_db_tables()
        print("Database connection established.")
    except Exception as e:
        print(f"Failed to initialize database: {e}")
        raise
    
    # Start reminder task
    if not reminder_loop.is_running():
        reminder_loop.start()
    
    # Sync slash commands
    try:
        await tree.sync()
        print("Slash commands synced.")
    except Exception as e:
        print(f"Error syncing commands: {e}")
    
    print("Bot is ready and running.")

# ---------- Main Entry Point ----------
if __name__ == "__main__":
    subprocess.run(["python", "webapp.py"])
    try:
        bot.run(TOKEN)
    except KeyboardInterrupt:
        print("Bot shutting down...")
    except Exception as e:
        print(f"Fatal error: {e}")