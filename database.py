import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "uye_takip.db"


def get_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def init_db():
    db = get_db()

    db.execute("""
        CREATE TABLE IF NOT EXISTS uyeler (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ad TEXT NOT NULL,
            soyad TEXT,
            telefon TEXT,
            notlar TEXT,
            baslangic TEXT,
            bitis TEXT
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS odemeler (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uye_id INTEGER NOT NULL,
            tutar TEXT,
            tarih TEXT,
            aciklama TEXT,
            ay_sayisi INTEGER DEFAULT 1
        )
    """)

    db.commit()
    db.close()
