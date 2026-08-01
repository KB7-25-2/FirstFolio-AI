import mysql.connector
from mysql.connector.abstracts import MySQLConnectionAbstract

from app.core.config import Settings


def create_mysql_connection(
    settings: Settings,
) -> MySQLConnectionAbstract:
    password = settings.mysql_password.get_secret_value()

    if not password:
        raise ValueError("MYSQL_PASSWORD 환경변수가 비어 있습니다.")

    return mysql.connector.connect(
        host=settings.mysql_host,
        port=settings.mysql_port,
        database=settings.mysql_database,
        user=settings.mysql_user,
        password=password,
        autocommit=False,
    )


def check_mysql_connection(
    settings: Settings,
) -> bool:
    connection = create_mysql_connection(settings)
    cursor = connection.cursor()

    try:
        cursor.execute("SELECT 1")
        return cursor.fetchone() == (1,)
    finally:
        cursor.close()
        connection.close()
