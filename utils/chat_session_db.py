# utils/database.py

import os
import configparser
import psycopg2
from psycopg2.extras import RealDictCursor


from utils.config import Config

# Load config.ini
config = Config()

# Determine the environment
env = os.environ.get("APP_ENV", "dev")  # default to 'dev' if not specified

# Read config values
db_host = config.get("db", f"{env}_host")
db_port = config.get("db", f"{env}_port")
db_name = config.get("db", f"{env}_db_name")
db_user = config.get("db", f"{env}_db_user")

# Read password from environment variable
db_password = os.environ.get("PROD_DB_PWD" if env == "prod" else "DEV_DB_PWD")
if not db_password:
    raise ValueError(f"Database password not found in environment variable {'PROD_DB_PWD' if env == 'prod' else 'DEV_DB_PWD'}")

# PostgreSQL DSN
DATABASE_URL = f"postgresql://{db_user}:{db_password}@{db_host}/{db_name}?sslmode=require"

class ChatMessage:
    def __init__(self, user_message=None, bot_response=None):
        self.user_message = user_message
        self.bot_response = bot_response

class Session:
    def __init__(self, session_id):
        self.session_id = session_id
        self.history = []

class Database:
    def __init__(self, db_url=DATABASE_URL):
        self.db_url = db_url

    def _connect(self):
        """Establish a connection to the PostgreSQL database."""
        return psycopg2.connect(dsn=self.db_url, cursor_factory=RealDictCursor)

    def create_tables(self):
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS sessions (
                        session_id TEXT PRIMARY KEY
                    );
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS messages (
                        message_id SERIAL PRIMARY KEY,
                        session_id TEXT REFERENCES sessions(session_id),
                        sender TEXT,
                        message TEXT,
                        is_feedback BOOLEAN DEFAULT FALSE
                    );
                """)
                conn.commit()

    def create_session(self, session_id):
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO sessions (session_id) 
                    VALUES (%s)
                    ON CONFLICT (session_id) DO NOTHING;
                """, (session_id,))
                conn.commit()

    def store_message(self, session_id, sender, message, is_feedback=False):
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO messages (session_id, sender, message, is_feedback)
                    VALUES (%s, %s, %s, %s);
                """, (session_id, sender, message, is_feedback))
                conn.commit()

    def fetch_session(self, session_id):
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT session_id FROM sessions WHERE session_id = %s", (session_id,))
                row = cursor.fetchone()
                if row:
                    cursor.execute("""
                        SELECT sender, message 
                        FROM messages 
                        WHERE session_id = %s 
                        ORDER BY message_id ASC;
                    """, (session_id,))
                    history = []
                    for msg in cursor.fetchall():
                        history.append({
                            "user_message": msg["message"] if msg["sender"] == "user" else "",
                            "bot_response": msg["message"] if msg["sender"] == "bot" else ""
                        })
                    return {"session_id": session_id, "history": history}
                else:
                    return {"session_id": session_id, "history": []}
