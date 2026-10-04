import re
from typing import Any, List, Optional

from psycopg.types.json import Jsonb
from sqlalchemy import RowMapping, text

from app.db.session import get_runtime_engine

# Único punto de acceso a la BD para v2: llama funciones del esquema api con parámetros
# enlazados. El nombre de la función y de los parámetros vienen del código (nunca del
# usuario) y además se validan contra un patrón estricto.
_FN_RE = re.compile(r"^api\.[a-z][a-z0-9_]*$")
_PARAM_RE = re.compile(r"^p_[a-z0-9_]+$")


def _adapt(value: Any) -> Any:
    # dict o lista de dicts -> jsonb; las listas de escalares van como arrays de Postgres
    if isinstance(value, dict) or (isinstance(value, list) and value and isinstance(value[0], dict)):
        return Jsonb(value)
    return value


def call(fn: str, **params: Any) -> List[RowMapping]:
    """Ejecuta SELECT * FROM api.fn(p_x => :p_x, ...) en su propia transacción (commit siempre).

    Cada función de BD es atómica por sí misma; se confirma aunque el resultado sea un
    estado de error (p. ej. para que cuente un intento fallido de código).
    """
    if not _FN_RE.match(fn):
        raise ValueError(f"Nombre de función no permitido: {fn}")
    for name in params:
        if not _PARAM_RE.match(name):
            raise ValueError(f"Nombre de parámetro no permitido: {name}")

    args = ", ".join(f"{name} => :{name}" for name in params)
    statement = text(f"SELECT * FROM {fn}({args})")
    with get_runtime_engine().begin() as conn:
        result = conn.execute(statement, {k: _adapt(v) for k, v in params.items()})
        return list(result.mappings().all()) if result.returns_rows else []


def call_one(fn: str, **params: Any) -> Optional[RowMapping]:
    rows = call(fn, **params)
    return rows[0] if rows else None


def call_scalar(fn: str, **params: Any) -> Any:
    rows = call(fn, **params)
    if not rows:
        return None
    return next(iter(rows[0].values()))
