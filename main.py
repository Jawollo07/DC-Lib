# combined_bot_web.py
import os
import asyncio
from datetime import date, timedelta
from threading import Thread
from typing import Optional

import aiohttp
import aiomysql
import discord
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv
from flask import Flask, jsonify

load_dotenv()

# ---------- Config ----------
TOKEN = os.getenv("DISCORD_TOKEN")
GB_API_KEY = os.getenv("GOOGLE_BOOKS_API_KEY")
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", 3306))
MYSQL_USER = os.getenv("MYSQL_USER")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
MYSQL_DB = os.getenv("MYSQL_DB", "book_db")
REMIND_DAYS_BEFORE = int(os.getenv("REMIND_DAYS_BEFORE", 1))
DUE_PERIOD_DAYS = int(os.getenv("DUE_PERIOD_DAYS", 14))

if not TOKEN:
    raise SystemExit("DISCORD_TOKEN missing in .env")

# ---------- Discord Bot Setup ----------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

db_pool: Optional[aiomysql.Pool] = None

# ---------- Flask Setup ----------
app = Flask(__name__)

@app.route("/status")
def status():
    return jsonify({"status": "running", "bot": "online" if bot.is_ready() else "offline"})

# ---------- Database ----------
async def create_pool() -> None:
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

# ---------- Utility Functions ----------
async def fetch_book_by_isbn(isbn: str):
    url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}&key={GB_API_KEY}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            if "items" not in data:
                return None
            item = data["items"][0]["volumeInfo"]
            return {
                "title": item.get("title"),
                "authors": ", ".join(item.get("authors", [])),
                "description": item.get("description", ""),
                "cover": item.get("imageLinks", {}).get("thumbnail")
            }

# ---------- Bot Commands ----------
@tree.command(name="borrow", description="Ein Buch ausleihen")
async def borrow(interaction: discord.Interaction, isbn: str):
    book_info = await fetch_book_by_isbn(isbn)
    if not book_info:
        await interaction.response.send_message("Buch nicht gefunden.", ephemeral=True)
        return

    due_date = date.today() + timedelta(days=DUE_PERIOD_DAYS)
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                INSERT IGNORE INTO books (user_id, username, isbn, title, authors, description, cover, due_date)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                interaction.user.id,
                str(interaction.user),
                isbn,
                book_info["title"],
                book_info["authors"],
                book_info["description"],
                book_info["cover"],
                due_date
            ))
    await interaction.response.send_message(f"{book_info['title']} ausgeliehen, Rückgabe am {due_date}.")

@tree.command(name="return_book", description="Buch zurückgeben")
async def return_book(interaction: discord.Interaction, isbn: str):
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM books WHERE user_id=%s AND isbn=%s", (interaction.user.id, isbn))
            await cur.execute("INSERT INTO rueckgabe_log (moderator_id, user_id, isbn) VALUES (%s,%s,%s)",
                              (interaction.user.id, interaction.user.id, isbn))
    await interaction.response.send_message(f"Buch {isbn} zurückgegeben.")

@tree.command(name="my_books", description="Meine ausgeliehenen Bücher anzeigen")
async def my_books(interaction: discord.Interaction):
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT title, due_date FROM books WHERE user_id=%s", (interaction.user.id,))
            rows = await cur.fetchall()
            if not rows:
                await interaction.response.send_message("Du hast keine Bücher ausgeliehen.")
                return
            msg = "\n".join([f"{r['title']} (bis {r['due_date']})" for r in rows])
            await interaction.response.send_message(msg)

# ---------- Reminder Task ----------
@tasks.loop(hours=24)
async def remind_due_books():
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                SELECT user_id, title, due_date FROM books
                WHERE reminded = FALSE AND due_date <= %s
            """, (date.today() + timedelta(days=REMIND_DAYS_BEFORE),))
            rows = await cur.fetchall()
            for row in rows:
                user = bot.get_user(row["user_id"])
                if user:
                    try:
                        await user.send(f"Erinnerung: Dein Buch '{row['title']}' ist am {row['due_date']} fällig.")
                        await cur.execute("UPDATE books SET reminded=TRUE WHERE user_id=%s AND title=%s",
                                          (row["user_id"], row["title"]))
                    except:
                        pass

@bot.event
async def on_ready():
    await tree.sync()
    remind_due_books.start()
    print(f"Bot logged in as {bot.user}!")

# ---------- Run Flask in Thread ----------
def run_flask():
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)

# ---------- Main ----------
async def main():
    await create_pool()
    await init_db_tables()
    Thread(target=run_flask).start()
    await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())