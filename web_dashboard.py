from flask import Flask, request, jsonify, render_template_string, redirect, url_for, session
from functools import wraps
import asyncio
from config import config_manager, get_config, logger
from database import dashboard_repo
import hashlib

def create_dashboard_app(bot):
    """Erstellt die Flask-Anwendung für das Web-Dashboard"""
    app = Flask(__name__)
    app.secret_key = hashlib.sha256(get_config('web_dashboard.password', 'admin').encode()).hexdigest()

    # Einfache Authentifizierung
    def login_required(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'logged_in' not in session:
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return decorated_function

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        """Login-Seite für das Dashboard"""
        if request.method == 'POST':
            password = request.form.get('password')
            expected_password = get_config('web_dashboard.password', 'admin')
            if password and hashlib.sha256(password.encode()).hexdigest() == app.secret_key:
                session['logged_in'] = True
                return redirect(url_for('dashboard'))
            else:
                return render_template_string(LOGIN_TEMPLATE, error="Ungültiges Passwort")
        return render_template_string(LOGIN_TEMPLATE)

    @app.route('/')
    @login_required
    def dashboard():
        """Haupt-Dashboard-Seite - SYNCHRON gemacht"""
        try:
            # Asynchrone Funktionen synchron aufrufen
            total_loans = asyncio.run(dashboard_repo.get_total_loans())
            overdue_count = asyncio.run(dashboard_repo.get_overdue_count())
            media_stats = asyncio.run(dashboard_repo.get_media_stats())
            return render_template_string(
                DASHBOARD_TEMPLATE,
                total_loans=total_loans,
                overdue_count=overdue_count,
                media_stats=media_stats
            )
        except Exception as e:
            logger.error(f"Fehler beim Laden des Dashboards: {e}")
            return render_template_string(DASHBOARD_TEMPLATE, error=str(e))

    @app.route('/logout')
    def logout():
        """Logout-Route"""
        session.pop('logged_in', None)
        return redirect(url_for('login'))

    @app.route('/api/stats', methods=['GET'])
    @login_required
    def api_stats():
        """API-Endpunkt für Statistiken - SYNCHRON gemacht"""
        try:
            # Asynchrone Funktionen synchron aufrufen
            total_loans = asyncio.run(dashboard_repo.get_total_loans())
            overdue_count = asyncio.run(dashboard_repo.get_overdue_count())
            media_stats = asyncio.run(dashboard_repo.get_media_stats())
            return jsonify({
                'total_loans': total_loans,
                'overdue_count': overdue_count,
                'media_stats': media_stats
            })
        except Exception as e:
            logger.error(f"Fehler beim API-Statistikaufruf: {e}")
            return jsonify({'error': str(e)}), 500

    # HTML-Vorlagen
    LOGIN_TEMPLATE = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Media Library - Login</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; }
            .error { color: red; }
            .form-group { margin-bottom: 15px; }
            input[type="password"] { width: 100%; padding: 8px; }
            button { padding: 10px 20px; background-color: #3498db; color: white; border: none; cursor: pointer; }
        </style>
    </head>
    <body>
        <h1>Media Library Dashboard</h1>
        <h2>Login</h2>
        {% if error %}
            <p class="error">{{ error }}</p>
        {% endif %}
        <form method="post">
            <div class="form-group">
                <label for="password">Passwort:</label>
                <input type="password" id="password" name="password" required>
            </div>
            <button type="submit">Einloggen</button>
        </form>
    </body>
    </html>
    """

    DASHBOARD_TEMPLATE = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Media Library - Dashboard</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
            .stats { margin-top: 20px; }
            .stat-box { border: 1px solid #ccc; padding: 10px; margin-bottom: 10px; }
            .error { color: red; }
            a { color: #3498db; text-decoration: none; }
        </style>
    </head>
    <body>
        <h1>Media Library Dashboard</h1>
        <p><a href="{{ url_for('logout') }}">Ausloggen</a></p>
        {% if error %}
            <p class="error">{{ error }}</p>
        {% endif %}
        <div class="stats">
            <div class="stat-box">
                <h3>Gesamte Ausleihen</h3>
                <p>{{ total_loans }}</p>
            </div>
            <div class="stat-box">
                <h3>Überfällige Medien</h3>
                <p>{{ overdue_count }}</p>
            </div>
            <div class="stat-box">
                <h3>Medienarten</h3>
                <ul>
                {% for media_type, count in media_stats.items() %}
                    <li>{{ media_type }}: {{ count }}</li>
                {% endfor %}
                </ul>
            </div>
        </div>
    </body>
    </html>
    """

    return app