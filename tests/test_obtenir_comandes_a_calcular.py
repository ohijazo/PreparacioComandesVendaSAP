"""Tests unitaris de `consultes.obtenir_comandes_a_calcular` amb mock pyodbc."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import consultes


@pytest.fixture(autouse=True)
def reset_udf_cache():
    """Reset del cache d'existència del UDF entre tests per aïllar-los."""
    consultes._udf_calcular_existeix_cache = None
    yield
    consultes._udf_calcular_existeix_cache = None


def _make_conn(rows_map):
    """Crea un mock de pyodbc.Connection amb un mapa {query_substr: [rows]}.

    Cada `row` és un objecte amb atributs (utilitza SimpleNamespace o MagicMock).
    """
    conn = MagicMock()

    def execute_side_effect(sql, *args):
        # Retorna un cursor amb .fetchone() i .fetchall() prescrits pel mapa.
        result = MagicMock()
        for substr, rows in rows_map.items():
            if substr in sql:
                result.fetchall.return_value = rows
                result.fetchone.return_value = rows[0] if rows else None
                return result
        raise AssertionError(f"Query inesperada: {sql[:120]}")

    conn.execute.side_effect = execute_side_effect
    return conn


def _row(**fields):
    """Crea una fila mock amb atributs."""
    row = MagicMock()
    for k, v in fields.items():
        setattr(row, k, v)
    # Support de row[0] per la query INFORMATION_SCHEMA
    row.__getitem__ = lambda self, i: list(fields.values())[i]
    return row


# ============================================================
# Cas UDF NO existeix
# ============================================================

def test_udf_no_existeix_retorna_llista_buida(caplog):
    conn = _make_conn({
        "INFORMATION_SCHEMA.COLUMNS": [_row(**{"": 0})],  # COUNT(*) = 0
    })
    with caplog.at_level("WARNING"):
        result = consultes.obtenir_comandes_a_calcular(conn)
    assert result == []
    assert "U_FCCalcular NO existeix" in caplog.text
    # Verifica que la query principal NO s'ha executat (només la comprovació)
    assert conn.execute.call_count == 1


def test_udf_no_existeix_cacheja_no_repeteix_check(caplog):
    conn = _make_conn({
        "INFORMATION_SCHEMA.COLUMNS": [_row(**{"": 0})],
    })
    consultes.obtenir_comandes_a_calcular(conn)
    consultes.obtenir_comandes_a_calcular(conn)
    consultes.obtenir_comandes_a_calcular(conn)
    # Només 1 crida a INFORMATION_SCHEMA (les altres 2 usen cache)
    assert conn.execute.call_count == 1


# ============================================================
# Cas UDF existeix
# ============================================================

def test_udf_existeix_retorna_comandes_marcades():
    conn = _make_conn({
        "INFORMATION_SCHEMA.COLUMNS": [_row(**{"": 1})],  # COUNT(*) = 1 → existeix
        "U_FCCalcular": [  # query principal
            _row(DocEntry=101, Series=268, DocNum=26600100, CardCode="C201119"),
            _row(DocEntry=102, Series=268, DocNum=26600101, CardCode="C221469"),
        ],
    })
    result = consultes.obtenir_comandes_a_calcular(conn)
    assert result == [
        {"doc_entry": 101, "series": 268, "docnum": 26600100, "card_code": "C201119"},
        {"doc_entry": 102, "series": 268, "docnum": 26600101, "card_code": "C221469"},
    ]


def test_udf_existeix_pero_cap_comanda_marcada():
    conn = _make_conn({
        "INFORMATION_SCHEMA.COLUMNS": [_row(**{"": 1})],
        "U_FCCalcular": [],
    })
    result = consultes.obtenir_comandes_a_calcular(conn)
    assert result == []


def test_udf_existeix_cardcode_none_es_string_buit():
    """Si CardCode és None, retornem string buit (defensiu)."""
    conn = _make_conn({
        "INFORMATION_SCHEMA.COLUMNS": [_row(**{"": 1})],
        "U_FCCalcular": [
            _row(DocEntry=1, Series=268, DocNum=1000, CardCode=None),
        ],
    })
    result = consultes.obtenir_comandes_a_calcular(conn)
    assert result == [
        {"doc_entry": 1, "series": 268, "docnum": 1000, "card_code": ""},
    ]


# ============================================================
# Cache mixt: cache pot ser omplit per True (ja no cal recomprovar)
# ============================================================

def test_udf_existeix_cache_true_reutilitzat_entre_crides():
    conn = _make_conn({
        "INFORMATION_SCHEMA.COLUMNS": [_row(**{"": 1})],
        "U_FCCalcular": [_row(DocEntry=1, Series=1, DocNum=1, CardCode="C1")],
    })
    consultes.obtenir_comandes_a_calcular(conn)
    consultes.obtenir_comandes_a_calcular(conn)
    # 1a crida: INFORMATION_SCHEMA + query principal = 2 crides
    # 2a crida: només query principal (cache) = 1 crida
    # Total: 3 crides
    assert conn.execute.call_count == 3
