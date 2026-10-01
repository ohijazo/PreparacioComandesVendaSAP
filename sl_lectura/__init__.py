"""Capa de lectura OData sobre el Service Layer de SAP B1.

Viu aqui, al costat de `sap_service_layer.py`, perque la comparteixen dues
aplicacions: aquesta (motor d'embalatges) i `agrupacioCarreguesSAP`, que hi
arriba pel `sys.path` que ja li injecta `PREPARACIO_PATH`.

Per que no una copia a cada repo: el codi de sessio del Service Layer ja va
costar un incident de produccio (login per peticio -> 502 amb 8 peticions
concurrents, 29-09-2026), i tenir-ne dues versions divergint es la manera mes
segura de repetir-lo. Una sola font.

Regla per a qui hi toqui: aqui NOMES hi va el que es generic de SAP. Res de
carregues, agrupacions, tarifes ni embalatges. El domini va a l'app que el te.

    from sl_lectura import odata as od
    from sl_lectura.client import client
    from sl_lectura import cache_articles
"""
