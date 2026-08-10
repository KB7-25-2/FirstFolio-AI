import mysql.connector
from mysql.connector.abstracts import MySQLConnectionAbstract

from app.core.config import Settings


def create_mysql_connection(
    settings: Settings,
) -> MySQLConnectionAbstract:
    password = settings.mysql_password.get_secret_value()

    if not password:
        raise ValueError("MYSQL_PASSWORD 환경변수가 비어 있습니다.")

    # DDL이 DEFAULT CURRENT_TIMESTAMP로 시각을 채우므로 세션 시간대가 기준이 된다.
    # Spring은 JDBC URL의 serverTimezone=UTC로 UTC를 고정한다. 여기서 지정하지 않으면
    # DB 서버 설정을 그대로 따라가, 같은 테이블에 기준이 다른 값이 섞인다.
    return mysql.connector.connect(
        host=settings.mysql_host,
        port=settings.mysql_port,
        database=settings.mysql_database,
        user=settings.mysql_user,
        password=password,
        # @@session.time_zone = SYSTEM => 기존 값 DB 서버 설정에 끌려감
        time_zone="+00:00",
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
