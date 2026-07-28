"""Converteix el resultat del motor d'embalatges a payload de línies SAP.

Ús pel `POST /api/afegir-palets/<doc_entry>` (`app.py`): un cop el motor
retorna els palets calculats (`Resultat.palets: list[PaletResum]`), aquest
mòdul genera la llista de dicts amb el format que espera Service Layer per
`Orders({N}).DocumentLines`.

Cada palet físic (`es_fisic=True`) es converteix en una línia amb:
- `ItemCode` = `art_codi` del palet (ex: `01030`, `01010`).
- `Quantity` = nombre de palets d'aquell tipus.
- `UnitPrice=0` + `PriceAfterVAT=0` + `DiscountPercent=0` → línia sense import
  (l'operari no factura el palet, només consta per traçabilitat logística).
- `U_FCAfegit='Y'` → marcador per identificar-les i substituir-les netament
  quan l'operari torni a clicar el botó (idempotència).
- `TaxCode` opcional via variable d'entorn `SAP_TAX_CODE_PALET`. Si buida,
  SAP fa fallback al TaxCode per defecte de l'article a OITM.
"""
from __future__ import annotations

import os
from typing import Any

# Iterable — no importem PaletResum directament per no crear dependencia
# hard sobre `_bootstrap.py`; treballem estructuralment amb els atributs
# `art_codi`, `quantitat`, `es_fisic`.


# TaxCode per línies palet (preu 0). Buida = deixar que SAP agafi el de l'article.
# Configurable via .env si el client necessita un codi específic (ex: "IVA_NS").
TAX_CODE_PALET = os.environ.get("SAP_TAX_CODE_PALET", "").strip() or None

# Text al camp lliure de la línia — permet identificar-les a ull nu al formulari SAP.
FREE_TEXT_MARKER = "Afegit per motor embalatges"

# Valor del UDF RDR1.U_FCAfegit per marcar línies afegides pel motor.
# Els valors vàlids configurats a SAP són "S"=Sí, "N"=No (en català).
# Aquesta constant també és el filtre que usa `SLClient.replace_marked_lines`
# per identificar les línies velles a esborrar en re-càlcul.
MARCADOR_LINIA_PALET_VALOR = "S"
MARCADOR_LINIA_PALET_UDF = "U_FCAfegit"


def generar_linies_palet_sap(
    palets,  # list[PaletResum] — evitem import per raons d'aïllament
    whs_code: str | None,
) -> list[dict[str, Any]]:
    """Converteix `resultat.palets` a llista de DocumentLine per Service Layer.

    - S'insereix una línia per cada `PaletResum` amb `art_codi` i quantitat > 0,
      independentment de `es_fisic`. Els BASE PALET (que el motor marca com
      "lògics" perquè el client no s'els emporta en despaletitzat) també van
      a la comanda com a línia informativa preu 0 — l'usuari els vol veure
      per traçabilitat i preparació.
    - Si `whs_code` és None, s'omet el camp `WarehouseCode` i SAP farà
      fallback al magatzem per defecte del client.
    - Cada línia porta `U_FCAfegit='S'` per permetre'n l'esborrat automàtic
      a la propera crida (idempotència).

    Si el motor retorna múltiples `PaletResum` amb el mateix `art_codi`
    (pot passar quan diferents regles assignen el mateix tipus de palet),
    s'agreguen en una sola línia sumant quantitats. Això evita duplicats
    a la comanda SAP i respecta el comportament de fusió que faria SAP
    silenciosament amb DocumentLines del mateix ItemCode.

    Retorna una llista ordenada tal com apareixerà a la comanda.
    """
    # Agregar per ItemCode (preserva ordre d'aparició del primer)
    agregat: dict[str, dict[str, Any]] = {}
    for p in palets:
        if not p.art_codi or p.quantitat <= 0:
            continue
        if p.art_codi in agregat:
            agregat[p.art_codi]["Quantity"] += int(p.quantitat)
            continue
        entry: dict[str, Any] = {
            "ItemCode": p.art_codi,
            "Quantity": int(p.quantitat),
            "UnitPrice": 0,
            "PriceAfterVAT": 0,
            "DiscountPercent": 0,
            "FreeText": FREE_TEXT_MARKER,
            MARCADOR_LINIA_PALET_UDF: MARCADOR_LINIA_PALET_VALOR,
        }
        if whs_code:
            entry["WarehouseCode"] = whs_code
        if TAX_CODE_PALET:
            entry["TaxCode"] = TAX_CODE_PALET
        agregat[p.art_codi] = entry

    return list(agregat.values())
