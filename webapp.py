import os
import requests
from flask import Flask, redirect, request, session, render_template, url_for
from datetime import datetime, date  # date für Datumsberechnungen hinzugefügt
import mysql.connector  # aiomysql durch mysql.connector ersetzt
from mysql.connector import Error  # Für Fehlerbehandlung

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "ijaiuh8rh38qhhfuaehuugfha3h")

# Discord OAuth2 Daten
DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET")
DISCORD_REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI", "http://localhost:5000/callback")
DISCORD_API_BASE = "https://discord.com/api"

# Funktion für DB-Verbindung
def get_db_connection():
    try:
        conn = mysql.connector.connect(
            host="localhost",
            user="book_db",
            password="book_db",
            database="book_db",
        )
        return conn
    except Error as e:
        print(f"Database connection failed: {e}")
        return None

@app.route("/")
def index():
    if "discord_user" in session:
        user = session["discord_user"]
        conn = get_db_connection()
        if not conn:
            return "Database error", 500
            
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM books WHERE user_id = %s", (user["id"],))
            books = cursor.fetchall()

            today = date.today()  # Aktuelles Datum
            for book in books:
                due_date = book.get("due")
                if due_date:
                    # Konvertierung verschiedener Datumstypen
                    if isinstance(due_date, datetime):
                        due_date = due_date.date()
                    elif isinstance(due_date, str):
                        due_date = datetime.strptime(due_date, "%Y-%m-%d").date()
                    
                    # Tage bis zur Fälligkeit berechnen
                    book["days_left"] = (due_date - today).days
                else:
                    book["days_left"] = None

            return render_template("dashboard.html", user=user, books=books)
        except Error as e:
            print(f"Database error: {e}")
            return "Error loading books", 500
        finally:
            cursor.close()
            conn.close()
    return render_template("index.html")

@app.route("/login")
def login():
    scope = "identify"
    discord_auth_url = (
        f"{DISCORD_API_BASE}/oauth2/authorize?client_id={DISCORD_CLIENT_ID}"
        f"&redirect_uri={DISCORD_REDIRECT_URI}"
        f"&response_type=code&scope={scope}"
    )
    return redirect(discord_auth_url)

@app.route("/callback")
def callback():
    code = request.args.get("code")
    if not code:
        return "Fehler: Kein Code erhalten", 400

    data = {
        "client_id": DISCORD_CLIENT_ID,
        "client_secret": DISCORD_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": DISCORD_REDIRECT_URI,
        "scope": "identify"
    }

    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    try:
        r = requests.post(f"{DISCORD_API_BASE}/oauth2/token", data=data, headers=headers)
        r.raise_for_status()
        token_data = r.json()
    except requests.exceptions.RequestException as e:
        return f"OAuth error: {str(e)}", 500

    # Userdaten holen
    headers = {"Authorization": f"Bearer {token_data['access_token']}"}
    try:
        r = requests.get(f"{DISCORD_API_BASE}/users/@me", headers=headers)
        r.raise_for_status()
        user_data = r.json()
    except requests.exceptions.RequestException as e:
        return f"User data error: {str(e)}", 500

    session["discord_user"] = user_data
    return redirect(url_for("index"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")
