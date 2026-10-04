from pathlib import Path

from alembic import op

SQL_DIR = Path(__file__).parent / "sql"


def run_sql_file(name: str) -> None:
    """Ejecuta un archivo .sql completo dentro de la transacción de la migración.

    Se usa el cursor de psycopg sin parámetros (protocolo simple), que admite varias
    sentencias y bloques $$ ... $$ sin interpretar ':' o '%' como placeholders.
    """
    sql = (SQL_DIR / name).read_text(encoding="utf-8")
    driver_conn = op.get_bind().connection.driver_connection
    with driver_conn.cursor() as cur:
        cur.execute(sql)
