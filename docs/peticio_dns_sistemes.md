# Petició a Sistemes — IP secundària + DNS per l'app d'embalatges (SAP)

Text preparat per enviar per mail o obrir tiquet. Context tècnic complet a
`deploy/README.md`; guia per executar-ho a `docs/Desplegament_SAP_Sistemes.pdf`.

---

**Assumpte**: Alta d'IP secundària i registre DNS al servidor `ae01farwebsrv`

Bon dia,

Al servidor `ae01farwebsrv` (`192.168.11.244`) conviuen dues versions de
l'aplicació de càlcul d'embalatges de comandes de venda: la que està en producció
(llegeix de Kais) i la nova (llegeix de SAP Business One). Les dues han de seguir
funcionant en paral·lel una temporada.

Ara mateix la versió nova només és accessible escrivint la IP i el port
(`http://192.168.11.244:5002/`), cosa incòmoda per als usuaris i fràgil si algun
dia canvia la IP del servidor. Voldríem donar-li un nom propi, **sense tocar res
de la versió que està en producció**.

Necessitem dues coses:

**1. Una IP lliure de la VLAN, com a segona adreça del mateix servidor**

Proposem `192.168.11.245` si està lliure; qualsevol altra de la mateixa VLAN ens
serveix igual. Es tracta d'afegir-la com a adreça addicional de la interfície
existent (àlias d'IP via netplan), no d'una màquina nova:

```yaml
# /etc/netplan/*.yaml
      addresses:
        - 192.168.11.244/24
        - 192.168.11.245/24      # ← nova
```

```bash
sudo netplan apply
```

**2. Un registre DNS**

| Nom | Tipus | Valor | TTL |
|---|---|---|---|
| `comandes-sap.agrienergia.local` | A | `192.168.11.245` | 300 |

El TTL curt (300 s) és perquè més endavant, quan la versió SAP substitueixi
definitivament l'actual, el canvi serà només de DNS i volem poder revertir-lo en
minuts si cal.

**Què NO cal fer:**

- No cal tocar el registre `comandes.agrienergia.local`, que ha de seguir apuntant
  a `192.168.11.244` (versió en producció).
- No cal obrir ports al tallafocs: és tràfic HTTP intern al port 80, el mateix que
  ja fa servir l'aplicació actual.
- No cal reiniciar ni reconfigurar el servei `comandes-venda.service` (producció).
  La part del servidor la faig jo un cop la IP i el DNS estiguin donats d'alta.

Quan estigui fet, aviseu-me i ho verifico amb:

```bash
ip -o addr show | grep 192.168.11.245
```

Gràcies,
Oscar Hijazo

---

## Seguiment

| Element | Estat | Data |
|---|---|---|
| IP secundària `192.168.11.245` | ⏳ pendent | — |
| DNS `comandes-sap.agrienergia.local` | ⏳ pendent | — |
| `deploy.sh --reinstall-service` amb `SAP_BIND_IP` | ⏳ pendent | — |
| Reapuntar botó B1UP UF-038 al nom DNS (consultor) | ⏳ opcional | — |
