"""Tests unitaris del pipeline botó B1UP → afegir línies palet.

Cobreix:
- `sap_line_builder.generar_linies_palet_sap`: filtra no-físics, marca amb
  U_FCAfegit, aplica WhsCode i TaxCode opcionals.
- `SLClient.replace_marked_lines`: patró GET-modify-PATCH sobre Orders,
  esborrat de línies marcades, preservació de línies "usuari".

No cobreix l'endpoint Flask (test integració seguent, requereix mock de BD).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from unittest.mock import patch

import pytest
import responses

import sap_line_builder as slb
import sap_service_layer as sl_mod
from sap_service_layer import SLClient


# ============================================================
# Fixtures i factories
# ============================================================

@dataclass
class _PaletResumStub:
    """Reprodueix l'estructura mínima de models.PaletResum sense import."""
    art_codi: str
    art_descrip: str
    quantitat: int
    es_fisic: bool = True


URL = "https://sap.test/b1s/v2"
COMPANY = "DB_FARINERA_TEST"
USER = "manager"
PWD = "secret"


def _make_client() -> SLClient:
    return SLClient(
        url=URL, company=COMPANY, user=USER, pwd=PWD,
        verify=False, timeout=5,
        max_retries_5xx=1, backoff_base_sec=0.0,
    )


def _login_response():
    responses.add(responses.POST, f"{URL}/Login",
                  json={"SessionId": "s"}, status=200)


# ============================================================
# generar_linies_palet_sap
# ============================================================

def test_generar_linies_palets_fisics_normal():
    palets = [
        _PaletResumStub("01030", "PALET FUSTA EUROPEU", 3, es_fisic=True),
        _PaletResumStub("01010", "BASE PALET", 1, es_fisic=True),
    ]

    linies = slb.generar_linies_palet_sap(palets, whs_code="01")

    assert len(linies) == 2
    l1, l2 = linies
    assert l1["ItemCode"] == "01030"
    assert l1["Quantity"] == 3
    assert l1["UnitPrice"] == 0
    assert l1["PriceAfterVAT"] == 0
    assert l1["DiscountPercent"] == 0
    assert l1["U_FCAfegit"] == "S"
    assert l1["WarehouseCode"] == "01"
    assert "FreeText" in l1
    assert l2["ItemCode"] == "01010"
    assert l2["Quantity"] == 1


def test_generar_linies_inclou_base_palet_encara_que_no_fisic():
    """El motor marca BASE PALET com es_fisic=False (lògic, no s'emporta
    al client en despaletitzat), però l'usuari vol veure'l a la comanda
    igualment per traçabilitat. Verifica que NO es filtra."""
    palets = [
        _PaletResumStub("01030", "PALET FUSTA", 2, es_fisic=True),
        _PaletResumStub("01010", "BASE PALET", 5, es_fisic=False),
    ]

    linies = slb.generar_linies_palet_sap(palets, whs_code="01")

    assert len(linies) == 2
    codes = {l["ItemCode"] for l in linies}
    assert codes == {"01030", "01010"}
    # BASE PALET també porta el marcador d'idempotència
    base = next(l for l in linies if l["ItemCode"] == "01010")
    assert base["Quantity"] == 5
    assert base["U_FCAfegit"] == "S"


def test_generar_linies_filtra_quantitat_zero():
    palets = [
        _PaletResumStub("01030", "P", 0, es_fisic=True),   # 0 → omès
        _PaletResumStub("01010", "P", -1, es_fisic=True),  # negatiu → omès
        _PaletResumStub("01000", "P", 2, es_fisic=True),
    ]

    linies = slb.generar_linies_palet_sap(palets, whs_code="01")

    assert len(linies) == 1
    assert linies[0]["ItemCode"] == "01000"


def test_generar_linies_sense_whs_code():
    palets = [_PaletResumStub("01030", "P", 1, es_fisic=True)]

    linies = slb.generar_linies_palet_sap(palets, whs_code=None)

    assert len(linies) == 1
    assert "WarehouseCode" not in linies[0]


def test_generar_linies_sense_tax_code_per_defecte():
    palets = [_PaletResumStub("01030", "P", 1, es_fisic=True)]

    # Assegura que la variable env no està setted per aquest test
    with patch.object(slb, "TAX_CODE_PALET", None):
        linies = slb.generar_linies_palet_sap(palets, whs_code="01")

    assert "TaxCode" not in linies[0]


def test_generar_linies_amb_tax_code_configurat():
    palets = [_PaletResumStub("01030", "P", 1, es_fisic=True)]

    with patch.object(slb, "TAX_CODE_PALET", "IVA_NS"):
        linies = slb.generar_linies_palet_sap(palets, whs_code="01")

    assert linies[0]["TaxCode"] == "IVA_NS"


def test_generar_linies_llista_buida():
    assert slb.generar_linies_palet_sap([], whs_code="01") == []


def test_generar_linies_agrega_mateix_itemcode():
    """El motor pot retornar múltiples PaletResum amb el mateix ItemCode
    (p.ex. quan diferents regles assignen 01030). L'agregat produeix una
    sola línia amb la suma de quantitats."""
    palets = [
        _PaletResumStub("01030", "PALET FUSTA", 3, es_fisic=True),
        _PaletResumStub("01030", "PALET FUSTA", 5, es_fisic=True),
        _PaletResumStub("01010", "BASE PALET", 2, es_fisic=False),
    ]

    linies = slb.generar_linies_palet_sap(palets, whs_code="01")

    assert len(linies) == 2
    fusta = next(l for l in linies if l["ItemCode"] == "01030")
    base = next(l for l in linies if l["ItemCode"] == "01010")
    assert fusta["Quantity"] == 8   # 3 + 5
    assert base["Quantity"] == 2


# ============================================================
# SLClient.replace_marked_lines
# ============================================================

@responses.activate
def test_replace_marked_lines_tanca_marcades_i_afegeix_noves():
    """Cas típic: comanda amb 3 línies (1 usuari + 2 marcades palet). El PATCH
    ha d'enviar només instruccions de tancar les 2 marcades + 2 noves palet.
    NO envia la línia usuari (SAP la preserva automàticament)."""
    _login_response()

    responses.add(
        responses.GET,
        f"{URL}/Orders(126)",
        match=[responses.matchers.query_param_matcher({"$select": "DocEntry,DocumentLines"})],
        json={
            "DocEntry": 126,
            "DocumentLines": [
                {"LineNum": 0, "ItemCode": "30001", "Quantity": 100, "U_FCAfegit": "N", "LineStatus": "bost_Open"},
                {"LineNum": 1, "ItemCode": "01030", "Quantity": 2,   "U_FCAfegit": "S", "LineStatus": "bost_Open"},
                {"LineNum": 2, "ItemCode": "01010", "Quantity": 1,   "U_FCAfegit": "S", "LineStatus": "bost_Open"},
            ],
        },
        status=200,
    )
    responses.add(responses.PATCH, f"{URL}/Orders(126)", status=204)

    c = _make_client()
    c.login()

    new_lines = [
        {"ItemCode": "01030", "Quantity": 3, "U_FCAfegit": "S", "UnitPrice": 0},
        {"ItemCode": "01010", "Quantity": 2, "U_FCAfegit": "S", "UnitPrice": 0},
    ]
    stats = c.replace_marked_lines(126, "U_FCAfegit", "S", new_lines)

    assert stats == {"removed": 2, "added": 2, "kept": 1}

    patch_calls = [call for call in responses.calls if call.request.method == "PATCH"]
    assert len(patch_calls) == 2

    # PATCH #1: tancament pur (2 línies palet velles)
    close_body = json.loads(patch_calls[0].request.body)
    assert close_body == {
        "DocumentLines": [
            {"LineNum": 1, "LineStatus": "bost_Close"},
            {"LineNum": 2, "LineStatus": "bost_Close"},
        ]
    }

    # PATCH #2: placeholder de la línia usuari (L0, no tancada) + 2 noves.
    # SAP interpreta {LineNum: X} sense altres camps com "preserva'm intacta L X"
    # i les noves sense LineNum s'afegeixen al final.
    add_body = json.loads(patch_calls[1].request.body)
    add_lines = add_body["DocumentLines"]
    assert len(add_lines) == 3
    assert add_lines[0] == {"LineNum": 0}  # placeholder línia usuari L0
    assert "LineNum" not in add_lines[1]
    assert "LineNum" not in add_lines[2]
    assert add_lines[1]["Quantity"] == 3
    assert add_lines[2]["Quantity"] == 2


@responses.activate
def test_replace_marked_lines_primer_calcul_sense_marcades():
    """Cas primer clic: cap línia marcada, només s'afegeixen les noves."""
    _login_response()

    responses.add(
        responses.GET,
        f"{URL}/Orders(200)",
        json={
            "DocEntry": 200,
            "DocumentLines": [
                {"LineNum": 0, "ItemCode": "30001", "Quantity": 50, "U_FCAfegit": "N", "LineStatus": "bost_Open"},
            ],
        },
        status=200,
    )
    responses.add(responses.PATCH, f"{URL}/Orders(200)", status=204)

    c = _make_client()
    c.login()

    new_lines = [{"ItemCode": "01030", "Quantity": 1, "U_FCAfegit": "S"}]
    stats = c.replace_marked_lines(200, "U_FCAfegit", "S", new_lines)

    assert stats == {"removed": 0, "added": 1, "kept": 1}

    patch_body = json.loads(
        [c for c in responses.calls if c.request.method == "PATCH"][0].request.body
    )
    # Placeholder L0 (línia usuari a preservar) + 1 nova palet
    lines = patch_body["DocumentLines"]
    assert len(lines) == 2
    assert lines[0] == {"LineNum": 0}
    assert lines[1]["ItemCode"] == "01030"


@responses.activate
def test_replace_marked_lines_new_lines_buit_nomes_tanca():
    """Si new_lines=[], el PATCH només envia les instruccions de tancament."""
    _login_response()

    responses.add(
        responses.GET, f"{URL}/Orders(300)",
        json={
            "DocEntry": 300,
            "DocumentLines": [
                {"LineNum": 0, "ItemCode": "30001", "Quantity": 100, "U_FCAfegit": "N", "LineStatus": "bost_Open"},
                {"LineNum": 1, "ItemCode": "01030", "Quantity": 2,   "U_FCAfegit": "S", "LineStatus": "bost_Open"},
            ],
        },
        status=200,
    )
    responses.add(responses.PATCH, f"{URL}/Orders(300)", status=204)

    c = _make_client()
    c.login()

    stats = c.replace_marked_lines(300, "U_FCAfegit", "S", [])

    assert stats == {"removed": 1, "added": 0, "kept": 1}

    patch_body = json.loads(
        [c for c in responses.calls if c.request.method == "PATCH"][0].request.body
    )
    # Només instrucció tancar L1
    assert len(patch_body["DocumentLines"]) == 1
    assert patch_body["DocumentLines"][0] == {"LineNum": 1, "LineStatus": "bost_Close"}


@responses.activate
def test_replace_marked_lines_marcades_ja_tancades_no_es_re_processen():
    """Si una línia ja té LineStatus=bost_Close, no s'inclou al PATCH."""
    _login_response()

    responses.add(
        responses.GET, f"{URL}/Orders(350)",
        json={
            "DocEntry": 350,
            "DocumentLines": [
                {"LineNum": 0, "ItemCode": "30001", "Quantity": 100, "U_FCAfegit": "N", "LineStatus": "bost_Open"},
                # Aquesta té U_FCAfegit=S però ja tancada — no la re-processem
                {"LineNum": 1, "ItemCode": "01030", "Quantity": 2, "U_FCAfegit": "S", "LineStatus": "bost_Close"},
            ],
        },
        status=200,
    )
    responses.add(responses.PATCH, f"{URL}/Orders(350)", status=204)

    c = _make_client()
    c.login()

    stats = c.replace_marked_lines(350, "U_FCAfegit", "S", [
        {"ItemCode": "01030", "Quantity": 3, "U_FCAfegit": "S"},
    ])

    assert stats == {"removed": 0, "added": 1, "kept": 2}

    patch_body = json.loads(
        [c for c in responses.calls if c.request.method == "PATCH"][0].request.body
    )
    # Placeholders per TOTES les línies existents (obertes + tancades) +
    # 1 nova palet. La L1 ja Close no es tanca de nou, però sí s'inclou
    # al placeholder perquè SAP no reorganitzi el document.
    lines = patch_body["DocumentLines"]
    assert len(lines) == 3
    assert lines[0] == {"LineNum": 0}
    assert lines[1] == {"LineNum": 1}
    assert lines[2]["ItemCode"] == "01030"


@responses.activate
def test_replace_marked_lines_ignora_lineNum_a_new_lines():
    """Si algú passa new_lines amb LineNum, s'ha d'omitir (SAP les auto-numera)."""
    _login_response()

    responses.add(
        responses.GET, f"{URL}/Orders(400)",
        json={"DocEntry": 400, "DocumentLines": []},
        status=200,
    )
    responses.add(responses.PATCH, f"{URL}/Orders(400)", status=204)

    c = _make_client()
    c.login()

    new_lines = [{"LineNum": 99, "ItemCode": "01030", "Quantity": 1, "U_FCAfegit": "S"}]
    c.replace_marked_lines(400, "U_FCAfegit", "S", new_lines)

    patch_body = json.loads(
        [c for c in responses.calls if c.request.method == "PATCH"][0].request.body
    )
    # Sense línies existents: només la nova, sense LineNum (l'omitim del payload)
    assert len(patch_body["DocumentLines"]) == 1
    assert "LineNum" not in patch_body["DocumentLines"][0]
    assert patch_body["DocumentLines"][0]["ItemCode"] == "01030"


@responses.activate
def test_replace_marked_lines_header_fields_opcional():
    """Si es passa header_fields, s'inclouen al PATCH (ex: reset flag U_FCCalcular)."""
    _login_response()

    responses.add(
        responses.GET, f"{URL}/Orders(500)",
        json={"DocEntry": 500, "DocumentLines": []},
        status=200,
    )
    responses.add(responses.PATCH, f"{URL}/Orders(500)", status=204)

    c = _make_client()
    c.login()

    c.replace_marked_lines(
        500, "U_FCAfegit", "S",
        [{"ItemCode": "01030", "Quantity": 1, "U_FCAfegit": "S"}],
        header_fields={"U_FCCalcular": "N"},
    )

    patch_body = json.loads(
        [c for c in responses.calls if c.request.method == "PATCH"][0].request.body
    )
    assert patch_body["U_FCCalcular"] == "N"
    assert len(patch_body["DocumentLines"]) == 1
