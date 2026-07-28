"""Diagnòstic: executa el motor sobre DocEntry 94 i imprimeix resultat.palets."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))
import _bootstrap  # noqa
import consultes
from motor import calcular_embalatges

conn = consultes.connectar()
meta = consultes.obtenir_metadata_ordr_per_doc_entry(conn, 94)
conn.close()
print("Metadata:", meta)
print()

resultat = calcular_embalatges(meta["series"], meta["docnum"], forcar=True)
print(f"Estat: {resultat.estat.value}")
print(f"Embalatges (palets físics): {len(resultat.embalatges)}")
print(f"Palets (resum): {len(resultat.palets)}")
print()
print("=== resultat.palets ===")
for i, p in enumerate(resultat.palets):
    print(f"  [{i}] art_codi={p.art_codi!r:20} descrip={p.art_descrip!r:40} "
          f"quantitat={p.quantitat:>4} es_fisic={p.es_fisic}")

# Ara aplica generar_linies_palet_sap i veiem què surt
from sap_line_builder import generar_linies_palet_sap
linies = generar_linies_palet_sap(resultat.palets, meta.get("whs_code"))
print()
print(f"=== Línies generades: {len(linies)} ===")
for l in linies:
    print(f"  {l}")
