# Petició a Sistemes — registre DNS de fallback per al swap

Text preparat per enviar per mail o obrir tiquet. Context tècnic a
`deploy/README.md`; procediment complet a `docs/runbook_swap_url_produccio.md`;
guia per Sistemes a `docs/Desplegament_SAP_Sistemes.pdf`.

---

**Assumpte**: Alta de registre DNS `comandes-kais.agrienergia.local`

Bon dia,

Volem que `http://comandes.agrienergia.local/` — la URL que ja fan servir els
usuaris per calcular embalatges de comandes de venda — passi a servir la versió de
l'aplicació que llegeix les dades de **SAP Business One**, en lloc de la que
llegeix de Kais.

La versió de Kais **no s'atura**: ha de seguir disponible en paral·lel una
temporada (política acordada: viu fins al novembre de 2026). Quedarà accessible a
`http://comandes-kais.agrienergia.local/`, i serveix també de marxa enrere ràpida
si la versió SAP dona problemes.

Les dues aplicacions ja conviuen al mateix servidor `ae01farwebsrv`
(`192.168.11.244`) darrere del mateix Apache, cadascuna amb el seu VirtualHost.
El canvi és de configuració d'Apache i el faig jo.

De vosaltres necessitem **un sol registre DNS**:

| Nom | Tipus | Valor | TTL |
|---|---|---|---|
| `comandes-kais.agrienergia.local` | A | `192.168.11.244` | 300 |

És **la mateixa IP** que ja fa servir `comandes.agrienergia.local`: el que separa
les dues aplicacions és el nom de host que llegeix Apache, no la xarxa.

**Què NO cal fer:**

- **No cal tocar el registre `comandes.agrienergia.local`.** Ha de seguir apuntant
  a `192.168.11.244` exactament com ara. El que canvia és quin VirtualHost el
  serveix, i això és config d'Apache, no DNS.
- No cal cap IP nova ni cap canvi a la configuració de xarxa del servidor.
- No cal obrir ports al tallafocs: és el port 80 que Apache ja fa servir.

Si podeu, confirmeu-me també que el TTL de `comandes.agrienergia.local` és de 300
s o menys. No el canviem, però si algun dia cal moure'l voldríem propagació
ràpida.

Quan el registre nou estigui donat d'alta, aviseu-me i acordem la finestra del
canvi (~10 min, fora d'hores actives).

Gràcies,
Oscar Hijazo

---

## Opcional, per més endavant

El botó "Calcular embalatges" de SAP Business One crida l'aplicació per IP
directa (`192.168.11.244:5002`). Funciona i el swap no l'afecta, però si algun dia
volem treure la IP del codi de B1UP caldria un segon registre:

| Nom | Tipus | Valor | TTL |
|---|---|---|---|
| `comandes-sap.agrienergia.local` | A | `192.168.11.244` | 300 |

No és urgent ni bloqueja el swap. Raonament al pas B.7 del runbook.

---

## Seguiment

| Element | Responsable | Estat | Data |
|---|---|---|---|
| Codi al dia al servidor (`a33c5e0`) | Oscar | ✅ fet | 29-09-2026 |
| Migració a Gunicorn (`--reinstall-service`) | Oscar | ✅ fet | 29-09-2026 |
| DNS `comandes-kais.agrienergia.local` | Sistemes | ⏳ pendent | — |
| Backup config Apache | Oscar | ⏳ pendent | — |
| Smoke load test amb Gunicorn | Oscar | ⏳ pendent | — |
| Finestra del swap (runbook Fase B) | Oscar | ⏳ pendent del DNS | — |
| DNS `comandes-sap` + UF-038 + `BIND_ADDR=127.0.0.1` | Oscar / consultor | ⏳ opcional | — |
