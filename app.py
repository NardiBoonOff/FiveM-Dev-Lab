from __future__ import annotations

import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

import psutil
from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs" / "actions"
CONFIG_PATH = DATA_DIR / "config.json"
DB_PATH = DATA_DIR / "devlab.db"

app = Flask(__name__, template_folder=BASE_DIR / "web" / "templates", static_folder=BASE_DIR / "web" / "static")
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "devlab-secret-key-change-me-in-production")


def ensure_directories() -> None:
    """Create all required directories."""
    directories = [
        DATA_DIR,
        BASE_DIR / "engine",
        BASE_DIR / "servers",
        BASE_DIR / "templates",
        BASE_DIR / "backups",
        BASE_DIR / "logs",
        LOG_DIR,
        BASE_DIR / "web" / "static" / "css",
        BASE_DIR / "web" / "static" / "js",
        BASE_DIR / "web" / "static" / "img",
        BASE_DIR / "web" / "templates",
        BASE_DIR / "templates" / "esx-ox",
        BASE_DIR / "templates" / "esx-clean",
        BASE_DIR / "templates" / "empty",
    ]
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
        print(f"[DIR] {directory.relative_to(BASE_DIR)}")


def load_config() -> dict[str, Any]:
    """Load configuration from JSON file."""
    if not CONFIG_PATH.exists():
        default = {
            "app_name": "FiveM Dev Lab",
            "theme": "dark",
            "primary_color": "#00d1b2",
            "default_admin_user": "admin",
            "default_admin_password": "admin123",
            "fx_server_path": "engine/FXServer.exe",
            "servers_root": "servers",
            "templates_root": "templates",
            "backups_root": "backups",
            "webhook_url": "",
            "default_environment": "dev",
        }
        save_config(default)
        return default
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_config(config: dict[str, Any]) -> None:
    """Save configuration to JSON file."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with CONFIG_PATH.open("w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def db_connection() -> sqlite3.Connection:
    """Create and return a database connection."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Initialize the database with required tables."""
    conn = db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'admin',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS servers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            folder TEXT NOT NULL,
            environment TEXT NOT NULL DEFAULT 'dev',
            template TEXT NOT NULL DEFAULT 'esx-ox',
            status TEXT NOT NULL DEFAULT 'stopped',
            port INTEGER DEFAULT 30120,
            rcon_port INTEGER DEFAULT 30121,
            mysql_host TEXT DEFAULT '127.0.0.1',
            mysql_port INTEGER DEFAULT 3306,
            mysql_user TEXT DEFAULT 'root',
            mysql_password TEXT DEFAULT 'root',
            mysql_database TEXT DEFAULT 'fivem',
            fx_version TEXT DEFAULT 'latest',
            notes TEXT DEFAULT '',
            pid INTEGER DEFAULT 0,
            uptime INTEGER DEFAULT 0,
            configured_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            server_name TEXT,
            action TEXT NOT NULL,
            details TEXT,
            level TEXT DEFAULT 'info',
            user TEXT DEFAULT 'system',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            server_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            path TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    conn.commit()

    # Create default admin user if not exists
    user = cursor.execute("SELECT id FROM users WHERE username = ?", ("admin",)).fetchone()
    if user is None:
        config = load_config()
        cursor.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (config["default_admin_user"], generate_password_hash(config["default_admin_password"]), "admin"),
        )
        conn.commit()

    conn.close()
    print("[DB] Database initialized")


def ensure_sample_server() -> None:
    """Create a sample server if none exists."""
    conn = db_connection()
    existing = conn.execute("SELECT id FROM servers LIMIT 1").fetchone()
    if existing is not None:
        conn.close()
        return

    server_dir = BASE_DIR / "servers" / "esx-ox-dev"
    server_dir.mkdir(parents=True, exist_ok=True)
    for subdir in ["resources", "cache", "logs", "data"]:
        (server_dir / subdir).mkdir(parents=True, exist_ok=True)

    config_path = server_dir / "server.cfg"
    if not config_path.exists():
        config_path.write_text(
            "# FiveM Dev Lab Server Config\n"
            "endpoint_add_tcp \"0.0.0.0:30120\"\n"
            "endpoint_add_udp \"0.0.0.0:30120\"\n"
            "sv_hostname \"FiveM Dev Lab ESX/OX\"\n"
            "sv_maxclients 32\n"
            "set steam_webApiKey \"\"\n"
            "set sv_licenseKey \"\"\n"
            "ensure mysql-async\n"
            "ensure oxmysql\n"
            "ensure es_extended\n",
            encoding="utf-8",
        )

    devlab_json = server_dir / "devlab.json"
    if not devlab_json.exists():
        devlab_json.write_text(
            json.dumps(
                {
                    "name": "esx-ox-dev",
                    "environment": "dev",
                    "template": "esx-ox",
                    "port": 30120,
                    "rcon_port": 30121,
                    "status": "stopped",
                    "mysql_database": "esx_ox_dev",
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    conn.execute(
        """
        INSERT INTO servers (name, folder, environment, template, status, port, rcon_port, mysql_database, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "esx-ox-dev",
            "esx-ox-dev",
            "dev",
            "esx-ox",
            "stopped",
            30120,
            30121,
            "esx_ox_dev",
            "Default development environment for ESX/OX testing",
        ),
    )
    conn.commit()
    conn.close()
    print("[SAMPLE] Default server created")


def get_server_from_db(server_id: int):
    """Fetch a server from the database by ID."""
    conn = db_connection()
    data = conn.execute("SELECT * FROM servers WHERE id = ?", (server_id,)).fetchone()
    conn.close()
    return dict(data) if data else None


def get_all_servers() -> list[dict[str, Any]]:
    """Fetch all servers from the database."""
    conn = db_connection()
    rows = conn.execute("SELECT * FROM servers ORDER BY configured_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_log(server_name: str = "", action: str = "system", details: str = "", level: str = "info", user: str = "system") -> None:
    """Add an entry to the activity log."""
    try:
        conn = db_connection()
        conn.execute(
            "INSERT INTO logs (server_name, action, details, level, user) VALUES (?, ?, ?, ?, ?)",
            (server_name, action, details, level, user),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[ERROR] Failed to log: {e}")


def login_required(view):
    """Decorator to require login."""
    def wrapper(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    wrapper.__name__ = view.__name__
    return wrapper


def build_server_path(folder_name: str) -> Path:
    """Build the path to a server folder."""
    return BASE_DIR / "servers" / folder_name


def read_text_file(path: Path) -> str:
    """Safely read a text file."""
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def get_server_status(server_row: dict[str, Any]) -> str:
    """Check if a server is running."""
    pid = int(server_row.get("pid") or 0)
    if pid and psutil.pid_exists(pid):
        return "running"
    return "stopped"


def update_server_status(server_id: int, status: str, pid: int | None = None) -> None:
    """Update server status in database."""
    try:
        conn = db_connection()
        conn.execute(
            "UPDATE servers SET status = ?, pid = ? WHERE id = ?",
            (status, pid if pid is not None else 0, server_id),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[ERROR] Failed to update server status: {e}")


def gather_monitoring_for_server(server: dict[str, Any]) -> dict[str, Any]:
    """Gather monitoring data for a server."""
    pid = int(server.get("pid") or 0)
    info = {"cpu_percent": 0, "memory_mb": 0, "status": "stopped", "uptime_seconds": 0, "online_players": 0}
    if pid and psutil.pid_exists(pid):
        try:
            process = psutil.Process(pid)
            with process.oneshot():
                info["cpu_percent"] = round(process.cpu_percent(interval=None), 1)
                info["memory_mb"] = round(process.memory_info().rss / (1024 * 1024), 2)
                info["uptime_seconds"] = int(time.time() - process.create_time())
        except Exception:
            pass
        info["status"] = "running"
    return info


def demo_server_script() -> str:
    """Generate a demo server script."""
    return (
        "import os, time, sys\n"
        "from pathlib import Path\n"
        "log_path = Path(os.environ.get('DEVLAB_LOG_PATH', 'logs/server.log'))\n"
        "log_path.parent.mkdir(parents=True, exist_ok=True)\n"
        "marker = Path(os.environ.get('DEVLAB_STOP_FILE', 'stop.flag'))\n"
        "with open(log_path, 'a') as fp: fp.write(f\"[{__import__('time').strftime('%H:%M:%S')}] Server started\\n\")\n"
        "while True:\n"
        "    with log_path.open('a', encoding='utf-8') as fp:\n"
        "        fp.write(f\"[{__import__('time').strftime('%H:%M:%S')}] [INFO] Tick\\n\")\n"
        "    time.sleep(5)\n"
        "    if marker.exists():\n"
        "        marker.unlink(missing_ok=True)\n"
        "        break\n"
    )


def start_demo_server(server: dict[str, Any]) -> bool:
    """Start a demo FiveM server process."""
    try:
        folder = build_server_path(server["folder"])
        log_file = folder / "logs" / "devlab-runtime.log"
        stop_flag = folder / "logs" / "stop.flag"
        if stop_flag.exists():
            stop_flag.unlink(missing_ok=True)

        env = os.environ.copy()
        env["DEVLAB_LOG_PATH"] = str(log_file)
        env["DEVLAB_STOP_FILE"] = str(stop_flag)
        env["PYTHONUNBUFFERED"] = "1"

        process = subprocess.Popen(
            [sys.executable, "-c", demo_server_script()],
            cwd=str(folder),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=False,
            text=True,
        )

        time.sleep(0.5)
        if process.poll() is None:
            update_server_status(server["id"], "running", process.pid)
            add_log(server["name"], "start", f"Server started (PID: {process.pid})", "info", session.get("user", "system"))
            print(f"[START] {server['name']} (PID: {process.pid})")
            return True
        else:
            return False
    except Exception as e:
        print(f"[ERROR] Failed to start server: {e}")
        traceback.print_exc()
        return False


def stop_demo_server(server: dict[str, Any]) -> bool:
    """Stop a demo FiveM server process."""
    try:
        pid = int(server.get("pid") or 0)
        if not pid or not psutil.pid_exists(pid):
            update_server_status(server["id"], "stopped", 0)
            return True

        process = psutil.Process(pid)
        try:
            process.terminate()
            process.wait(timeout=5)
        except psutil.TimeoutExpired:
            process.kill()

        update_server_status(server["id"], "stopped", 0)
        add_log(server["name"], "stop", "Server stopped", "info", session.get("user", "system"))
        print(f"[STOP] {server['name']}")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to stop server: {e}")
        return False


@app.route("/login", methods=["GET", "POST"])
def login():
    """Handle login."""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        conn = db_connection()
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()
        if user and check_password_hash(user["password_hash"], password):
            session["user"] = username
            add_log("system", "login", f"User logged in", "info", username)
            return redirect(url_for("dashboard"))
        flash("Invalid credentials", "error")
    config = load_config()
    return render_template("login.html", config=config)


@app.route("/logout")
def logout():
    """Handle logout."""
    session.pop("user", None)
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    """Redirect to dashboard."""
    return redirect(url_for("dashboard"))


@app.route("/dashboard")
@login_required
def dashboard():
    """Display main dashboard."""
    servers = get_all_servers()
    for server in servers:
        server["status"] = get_server_status(server)
        server["monitor"] = gather_monitoring_for_server(server)

    running = sum(1 for s in servers if s["status"] == "running")
    stopped = sum(1 for s in servers if s["status"] == "stopped")
    config = load_config()
    return render_template(
        "dashboard.html",
        servers=servers,
        running=running,
        stopped=stopped,
        total=len(servers),
        config=config,
    )


@app.route("/servers", methods=["GET", "POST"])
@login_required
def servers():
    """Display and manage servers."""
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        folder = request.form.get("folder", "").strip() or name.lower().replace(" ", "-")
        env = request.form.get("environment", "dev").strip() or "dev"
        template = request.form.get("template", "esx-ox").strip() or "esx-ox"
        port = int(request.form.get("port", 30120) or 30120)
        notes = request.form.get("notes", "")

        if not name:
            flash("Name is required", "error")
            return redirect(url_for("servers"))

        server_dir = build_server_path(folder)
        server_dir.mkdir(parents=True, exist_ok=True)
        for subdir in ["resources", "cache", "logs", "data"]:
            (server_dir / subdir).mkdir(parents=True, exist_ok=True)

        cfg_path = server_dir / "server.cfg"
        if not cfg_path.exists():
            cfg_path.write_text(
                f"# Auto-generated server.cfg\n"
                f"sv_hostname \"{name}\"\n"
                f"sv_maxclients 32\n"
                f"endpoint_add_tcp \"0.0.0.0:{port}\"\n",
                encoding="utf-8",
            )

        conn = db_connection()
        conn.execute(
            "INSERT INTO servers (name, folder, environment, template, port, rcon_port, notes) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (name, folder, env, template, port, port + 1, notes),
        )
        conn.commit()
        conn.close()
        add_log(name, "create", f"Server created from {template} template", "info", session.get("user", "system"))
        flash(f"Server '{name}' created successfully", "success")
        return redirect(url_for("servers"))

    servers_list = get_all_servers()
    for server in servers_list:
        server["status"] = get_server_status(server)
    config = load_config()
    return render_template("servers.html", servers=servers_list, config=config)


@app.route("/server/<int:server_id>")
@login_required
def server_detail(server_id: int):
    """Display server details."""
    server = get_server_from_db(server_id)
    if not server:
        flash("Server not found", "error")
        return redirect(url_for("servers"))
    server["status"] = get_server_status(server)
    server["monitor"] = gather_monitoring_for_server(server)
    cfg_path = build_server_path(server["folder"]) / "server.cfg"
    server["config_text"] = read_text_file(cfg_path)
    config = load_config()
    return render_template("server_detail.html", server=server, config=config)


@app.route("/server/<int:server_id>/config", methods=["POST"])
@login_required
def save_server_config(server_id: int):
    """Save server configuration."""
    server = get_server_from_db(server_id)
    if not server:
        flash("Server not found", "error")
        return redirect(url_for("servers"))
    cfg_path = build_server_path(server["folder"]) / "server.cfg"
    content = request.form.get("content", "")
    cfg_path.write_text(content, encoding="utf-8")
    add_log(server["name"], "config-update", "server.cfg updated", "info", session.get("user", "system"))
    flash("Configuration saved successfully", "success")
    return redirect(url_for("server_detail", server_id=server_id))


@app.route("/api/server/<int:server_id>/<action>", methods=["POST"])
@login_required
def server_action(server_id: int, action: str):
    """Handle server actions via API."""
    server = get_server_from_db(server_id)
    if not server:
        return jsonify({"status": "error", "message": "Server not found"}), 404

    if action == "start":
        if get_server_status(server) == "running":
            return jsonify({"status": "ok", "message": "Server already running"})
        ok = start_demo_server(server)
        return jsonify({"status": "ok" if ok else "error", "message": "Server started" if ok else "Failed to start server"})

    elif action == "stop":
        ok = stop_demo_server(server)
        return jsonify({"status": "ok" if ok else "error", "message": "Server stopped"})

    elif action == "restart":
        stop_demo_server(server)
        time.sleep(1)
        ok = start_demo_server(server)
        return jsonify({"status": "ok" if ok else "error", "message": "Server restarted" if ok else "Failed to restart server"})

    return jsonify({"status": "error", "message": "Unknown action"}), 400


@app.route("/logs")
@login_required
def logs():
    """Display activity logs."""
    conn = db_connection()
    rows = conn.execute("SELECT * FROM logs ORDER BY created_at DESC LIMIT 300").fetchall()
    conn.close()
    config = load_config()
    return render_template("logs.html", entries=[dict(r) for r in rows], config=config)


@app.route("/backups")
@login_required
def backups():
    """Display backups."""
    backup_root = BASE_DIR / "backups"
    items = []
    if backup_root.exists():
        for path in sorted(backup_root.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True):
            if path.is_file():
                items.append({"name": path.name, "size": path.stat().st_size, "type": "file", "modified": datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")})
    config = load_config()
    return render_template("backups.html", backups=items, config=config)


@app.route("/backup/create", methods=["POST"])
@login_required
def create_backup():
    """Create a backup."""
    backup_root = BASE_DIR / "backups"
    backup_root.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive_name = f"backup-{stamp}.zip"
    archive_path = backup_root / archive_name
    if not archive_path.exists():
        archive_path.write_bytes(b"PK\x05\x06" + b"\x00" * 18)  # Empty ZIP
    add_log("system", "backup", f"Backup created: {archive_name}", "info", session.get("user", "system"))
    flash(f"Backup created: {archive_name}", "success")
    return redirect(url_for("backups"))


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    """Display and update settings."""
    config = load_config()
    if request.method == "POST":
        config["app_name"] = request.form.get("app_name", config["app_name"])
        config["theme"] = request.form.get("theme", config["theme"])
        config["primary_color"] = request.form.get("primary_color", config["primary_color"])
        config["webhook_url"] = request.form.get("webhook_url", config["webhook_url"])
        config["default_environment"] = request.form.get("default_environment", config["default_environment"])
        save_config(config)
        add_log("system", "settings-update", "Settings updated", "info", session.get("user", "system"))
        flash("Settings saved successfully", "success")
        return redirect(url_for("settings"))

    return render_template("settings.html", config=config)


@app.errorhandler(404)
def not_found(error):
    config = load_config()
    return render_template("404.html", config=config), 404


@app.errorhandler(500)
def server_error(error):
    config = load_config()
    return render_template("500.html", config=config), 500


if __name__ == "__main__":
    print("\n" + "="*50)
    print("  FiveM Dev Lab - Starting")
    print("="*50)
    print()
    print("[INIT] Setting up directories...")
    ensure_directories()
    print()
    print("[INIT] Initializing database...")
    init_db()
    print()
    print("[INIT] Setting up sample server...")
    ensure_sample_server()
    print()
    print("[CONFIG] Loading configuration...")
    config = load_config()
    print(f"  App Name: {config['app_name']}")
    print(f"  Admin User: {config['default_admin_user']}")
    print(f"  Password: {config['default_admin_password']}")
    print()
    print("="*50)
    print("  READY TO START")
    print("="*50)
    print()
    print(f"  Open your browser: http://localhost:5000")
    print(f"  Login: {config['default_admin_user']} / {config['default_admin_password']}")
    print()
    print("  Press Ctrl+C to stop the server")
    print()
    app.run(host="0.0.0.0", port=5000, debug=False)
