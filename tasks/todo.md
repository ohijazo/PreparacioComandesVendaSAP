# Convivència Kais + SAP amb URL pròpia per SAP (29-09-2026)

## Context i troballa inicial

Auditant el servidor `ae01farwebsrv` (192.168.11.244) abans de desplegar els 2
commits pendents, l'estat real **no coincideix** amb el que assumia el repo:

| Assumpció al repo | Realitat al servidor |
|---|---|
| Apache reverse proxy al port 80 amb vhosts per nom | **No hi ha Apache.** El Gunicorn de Kais escolta a `0.0.0.0:80` i respon a qualsevol `Host` |
| SAP corre amb Gunicorn a `127.0.0.1:5002` | SAP corre amb el **dev server de Flask** (`Server: Werkzeug/3.1.7`) a `0.0.0.0:5002` |
| Kais accessible al port 5001 | 5001 tancat des de fora; només 80 i 5002 oberts |

Causa arrel del punt 2: el camí d'**actualització** de `deploy.sh` fa `git pull`
+ `systemctl restart`, però **mai reescriu la unit systemd**. La unit amb
Gunicorn només es crea a `--first-install`, i el servidor es va instal·lar abans
que existís.

Conseqüència: `deploy/apache/*.conf` i la Fase B del runbook de swap descriuen
passos **inexecutables** (a2ensite/apachectl sobre un Apache que no hi és).

## Decisions preses (Oscar, 29-09-2026)

1. **Les dues variants han de conviure una temporada** — Kais no es toca gens.
2. **Convivència via IP secundària**, no via reverse proxy:
   - `192.168.11.244:80` → Kais (`comandes.agrienergia.local`) — intacte
   - `192.168.11.245:80` → SAP (`comandes-sap.agrienergia.local`) — nou
   - Zero canvis a Kais; el swap futur passa a ser només un canvi de DNS.
3. **Migrar SAP a Gunicorn** en aquest mateix desplegament.
4. Mantenir el bind `0.0.0.0:5002` en paral·lel perquè el botó B1UP (UF-038),
   que apunta a `http://192.168.11.244:5002/...`, **no es trenqui**.

## Pla

- [x] Auditar l'estat real del servidor (sense SSH: capçaleres HTTP + sondeig de ports)
- [x] `deploy.sh`: extreure la generació de la unit systemd a una funció reutilitzable
- [x] `deploy.sh`: nou flag `--reinstall-service` (repetible, idempotent)
- [x] `deploy.sh`: bind dual (`SAP_BIND_IP:80` + `0.0.0.0:5002`) + `CAP_NET_BIND_SERVICE`
- [x] `deploy.sh`: `--reinstall-service` garanteix `pip install -r requirements.txt` (gunicorn)
- [x] Eliminar `deploy/apache/` (descriu una arquitectura inexistent → enganyós)
- [x] `deploy/README.md` nou: arquitectura real de xarxa del servidor
- [x] Reescriure `docs/runbook_swap_url_produccio.md` sense Apache (swap = canvi DNS)
- [x] `docs/peticio_dns_sistemes.md`: text de petició per Sistemes (IP + DNS)
- [x] `scripts/build_guia_sistemes.py` + `docs/Desplegament_SAP_Sistemes.pdf`
- [x] `app.py`: fix del servei reiniciat per `/api/admin/actualitzar` (reiniciava Kais!)
- [x] `tasks/lessons.md`: lliçó L11 sobre identificadors de Kais heretats
- [x] Actualitzar `tasks/fase2_progress.md`
- [ ] **Desplegar els 2 commits pendents** — bloquejat: sense accés SSH (veure sota)

## Bloqueig: desplegament

`ssh ohijazo@192.168.11.244` → `Permission denied (publickey,password)`. No hi ha
clau pública instal·lada per aquesta màquina, i l'autenticació per contrasenya és
interactiva. El desplegament l'ha d'executar l'Oscar o Sistemes amb els
comandaments del PDF (`docs/Desplegament_SAP_Sistemes.pdf`, apartat 4).

Versió desplegada actualment: `1b3c6d6` (15-09-2026).
Versió a desplegar: `3f266b3`. Commits pendents:
- `2aed94a` test: cobrir els dos casos en què es tanca una línia palet manual
- `3f266b3` chore(sap): la BD de test passa a `DB_FARIN_TEST`

## Ordre d'execució al servidor

```bash
# 1. Codi al dia (git pull + restart del servei actual)
sudo bash /var/www/comandes-venda-sap/deploy.sh

# 2. Migrar a Gunicorn mantenint el port 5002 (encara sense la IP .245)
sudo bash /var/www/comandes-venda-sap/deploy.sh --reinstall-service

# 3. [Quan Sistemes hagi donat d'alta la IP .245 i el DNS]
sudo SAP_BIND_IP=192.168.11.245 bash /var/www/comandes-venda-sap/deploy.sh --reinstall-service
```

Els passos 2 i 3 són repetibles: `--reinstall-service` reescriu la unit sencera
cada cop, així que canviar `SAP_BIND_IP` (o treure'l) és un `--reinstall-service`
més, sense estat acumulat.

## Revisió

### Decisions arquitectòniques

- **IP secundària en lloc de reverse proxy.** Un Apache/nginx al davant hauria
  obligat a moure el Gunicorn de Kais de `0.0.0.0:80` a `127.0.0.1:5001`, és a
  dir, a tocar un servei declarat intocable fins novembre 2026 i a obrir una
  finestra de tall. Amb una IP secundària, els dos Gunicorn conviuen al port 80
  de **IPs diferents** i Kais no s'assabenta que SAP existeix.
- **Bind dual durant la convivència.** El botó B1UP apunta a la IP:5002. Fer
  només `--bind .245:80` l'hauria trencat en silenci. Gunicorn accepta múltiples
  `--bind`, així que les dues portes conviuen fins que el consultor actualitzi la
  UF-038; llavors n'hi ha prou amb un `--reinstall-service` sense el 5002.
- **`CAP_NET_BIND_SERVICE` en lloc de córrer com a root.** El servei segueix sent
  `www-data`; la capability li dona només el permís de lligar-se a un port < 1024.
- **`After=network-online.target`.** Sense això, Gunicorn pot arrencar abans que
  l'àlies `.245` existeixi i morir amb `Cannot assign requested address`. Amb
  `Restart=always` se'n sortiria igualment, però amb reinicis lletjos al boot.
- **Esborrar `deploy/apache/` en lloc de deixar-ho documentat com a obsolet.**
  Documentació que descriu una arquitectura inexistent és pitjor que cap
  documentació: el runbook ordenava `a2ensite` sobre un Apache que no hi és.
  L'històric queda a git.

### Fitxers modificats

- `app.py` — `/api/admin/actualitzar` reiniciava `comandes-venda` (Kais, producció)
  en lloc de `comandes-venda-sap`; amb botó a la UI i sudoers concedit. Veure L11.
- `tasks/lessons.md` — L11: identificadors d'infraestructura heretats de Kais
- `deploy.sh` — funció `write_service_unit()`, flag `--reinstall-service`, bind dual
- `deploy/apache/` — **eliminat** (arquitectura inexistent)
- `deploy/README.md` — **nou**, arquitectura real de xarxa
- `docs/runbook_swap_url_produccio.md` — reescrit sense Apache
- `docs/peticio_dns_sistemes.md` — **nou**, petició per Sistemes
- `scripts/build_guia_sistemes.py` — **nou**, generador del PDF
- `docs/Desplegament_SAP_Sistemes.docx` / `.pdf` — **nous**, guia per Sistemes
- `tasks/fase2_progress.md` — secció de convivència
