import os
import psycopg2
import time

from psycopg2 import pool, sql
from psycopg2.extras import RealDictCursor 

from utils.config import Config

# Load config.ini
config = Config()
env = os.environ.get("APP_ENV", "dev")  # default to 'dev' if not specified

# Read database config
db_schema = config.get("db", f"{env}_schema")
db_host = config.get("db", f"{env}_host")
db_port = config.get("db", f"{env}_port")
db_name = config.get("db", f"{env}_db_name")
db_user = config.get("db", f"{env}_db_user")
db_password = os.environ.get("PROD_DB_PWD" if env == "prod" else "DEV_DB_PWD")

if not db_password:
    raise ValueError(f"Database password not found in environment variable {'PROD_DB_PWD' if env == 'prod' else 'DEV_DB_PWD'}")

# PostgreSQL DSN
DATABASE_URL = f"postgresql://{db_user}:{db_password}@{db_host}/{db_name}?sslmode=require"
print(f"DATABASE_URL: {DATABASE_URL}")

# Connection pool (singleton-style)
class Database:
    _pool = None

    def __init__(self, db_url=DATABASE_URL, minconn=1, maxconn=5):
        if not Database._pool:
            Database._pool = psycopg2.pool.SimpleConnectionPool(
                minconn,
                maxconn,
                dsn=db_url,
                cursor_factory=RealDictCursor
            )
        self.db_url = db_url

    def _get_connection(self):
        print(f"[DB] Getting connection for schema: {db_schema}")
        retries = 3
        for attempt in range(retries):
            try:
                conn = self._pool.getconn()
                conn.autocommit = False
                with conn.cursor() as cursor:
                    cursor.execute(
                        sql.SQL("SET search_path TO {}").format(sql.Identifier(db_schema))
                    )
                return conn
            except psycopg2.OperationalError as e:
                if attempt < retries - 1:
                    time.sleep(1)
                    continue
                raise e

    def _release_connection(self, conn):
        print(f"[DB] Releasing connection for schema: {db_schema}")
        self._pool.putconn(conn)

    def create_tables(self):
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                 # Ensure schema exists
                cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {db_schema};")
                cursor.execute(f"SET search_path TO {db_schema};")

                # Create sessions table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS sessions (
                        session_id TEXT PRIMARY KEY
                    );
                """)

                # Create messages table
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
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            self._release_connection(conn)

    def create_session(self, session_id):
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO sessions (session_id) 
                    VALUES (%s)
                    ON CONFLICT (session_id) DO NOTHING;
                """, (session_id,))
                conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            self._release_connection(conn)

    def store_message(self, session_id, sender, message, is_feedback=False):
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO messages (session_id, sender, message, is_feedback)
                    VALUES (%s, %s, %s, %s);
                """, (session_id, sender, message, is_feedback))
                conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            self._release_connection(conn)

    def fetch_session(self, session_id):
        conn = self._get_connection()
        try:
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
        finally:
            self._release_connection(conn)

class ChatMessage:
    def __init__(self, user_message=None, bot_response=None):
        self.user_message = user_message
        self.bot_response = bot_response

class Session:
    def __init__(self, session_id):
        self.session_id = session_id
        self.history = []