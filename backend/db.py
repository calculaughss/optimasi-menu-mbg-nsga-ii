import configparser
import os

import pymysql
import pymysql.cursors
from pymysql.constants import FIELD_TYPE
from pymysql.converters import conversions

CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config", "database.ini",
)

_CONVERSIONS = conversions.copy()
_CONVERSIONS[FIELD_TYPE.DECIMAL] = float
_CONVERSIONS[FIELD_TYPE.NEWDECIMAL] = float


def get_connection():
    """Buka koneksi MySQL baru (DictCursor supaya baris bisa diakses lewat nama kolom)."""
    parser = configparser.ConfigParser()
    parser.read(CONFIG_PATH)
    cfg = parser["database"]
    return pymysql.connect(
        host=cfg.get("host", "127.0.0.1"),
        port=cfg.getint("port", 3306),
        user=cfg.get("username"),
        password=cfg.get("password"),
        database=cfg.get("dbname"),
        charset=cfg.get("charset", "utf8mb4"),
        cursorclass=pymysql.cursors.DictCursor,
        conv=_CONVERSIONS,
        autocommit=False,
    )
