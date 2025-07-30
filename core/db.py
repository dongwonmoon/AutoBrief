import psycopg2
from psycopg2 import sql

from .settings import config


def get_db():
    conn = psycopg2.connect(
        host=config["db"]["host"],
        dbname=config["db"]["dbname"],
        user=config["db"]["user"],
        password=config["db"]["password"],
        port=config["db"]["port"],
    )
    try:
        yield conn
    finally:
        conn.close()
