# Configuració B1UP — Botó "Calcular embalatges" al Sales Order

Aquesta guia configura un **Function Button** dins B1UP de Boyum que
apareix al formulari **Comanda de venda** (form 139) de SAP B1. Al clicar,
crida l'endpoint Python `POST /api/afegir-palets/<DocEntry>` que:

1. Executa el motor RF1-RF14 amb les dades reals de la comanda.
2. Insereix línies físiques de palet (`01030 PALET FUSTA EUROPEU`,
   `01010 BASE PALET`, etc.) a la mateixa comanda amb preu 0 i marcades
   amb `U_FCAfegit='Y'`.
3. Refresca el formulari perquè l'operari vegi les línies noves.

## Prerequisits

1. **UDF `RDR1.U_FCAfegit`** ja creat — veure `docs/creacio_udf_rdr1_afegit.md`.
2. **App Flask corrent al port 5002** al servidor
   (`http://<host-app>:5002/api/afegir-palets/<N>`).
3. **B1UP instal·lat i configurat** al Fat Client de SAP.
4. **Accés al B1UP Configurator** amb l'usuari SAP que fa la config.

## Pas 1 — Obrir el B1UP Configurator

1. Dins SAP Fat Client, menú **Boyum IT → B1 Usability Package → Configurator**
   (o Ctrl+Shift+F12, depenent de la versió).
2. Es carrega la interfície B1UP amb l'arbre de mòduls.

## Pas 2 — Crear una nova Function Button

1. Al menú lateral, expandeix: **Function → Function Buttons**.
2. Clica **+ Add** (o botó "New").
3. Ompliu el formulari general:

| Camp | Valor |
|---|---|
| **Name** | `CalcularEmbalatges` |
| **Description** | Botó que calcula i afegeix línies palet a la comanda |
| **Category** | (opcional, ex: `Embalatges`) |

## Pas 3 — Configurar la ubicació del botó

A la pestanya **Form** / **Positioning**:

| Camp | Valor |
|---|---|
| **Form Type** | `139` (Sales Order) |
| **Position** | `Toolbar` (o `Buttons area at the bottom`, segons preferència) |
| **Caption on button** | `Calcular embalatges` |
| **Icon** | Opcional (ex: calculadora) |

**Visibility Rules** (recomanat):
- Mostrar només quan la comanda està **desada** (té `DocEntry`).
  Regla: `Form.Mode = View` OR `Form.Mode = Update` (no `Add`).
- Amagar quan la comanda està **tancada** (`DocStatus = 'C'`).
  Regla: `$[ORDR.DocStatus] = 'O'`.

## Pas 4 — Configurar l'acció HTTP

A la pestanya **Actions**, afegeix una acció de tipus **HTTP Request**
(o **Rest Client**, segons versió B1UP):

| Camp | Valor |
|---|---|
| **Method** | `POST` |
| **URL** | `http://<HOST-APP>:5002/api/afegir-palets/$[$8.1.0]` |
| **Content-Type** | `application/json` |
| **Body** | (buit, no cal payload) |
| **Timeout (ms)** | `30000` |
| **Wait for response** | Yes |

**Explicació del placeholder `$[$8.1.0]`**:
- `$8` = camp DocEntry (a form 139).
- `.1.0` = índex/fila (0 = capçalera).
- És la sintaxi estàndard B1UP per referenciar valors del formulari actiu.

**Substitueix `<HOST-APP>`** pel nom del host o IP on corre Flask
(ex: `comandes.agrienergia.local` o `192.168.11.240`).

## Pas 5 — Manegar la resposta

Configura què fer segons el resultat HTTP:

### Si èxit (HTTP 200 amb `ok: true`)

1. **Show Message Box** (accio B1UP):
   ```
   Afegides ${response.linies_afegides} línies palet
   (esborrades ${response.linies_esborrades} velles).
   Total: ${response.resum.total_palets} palets · ${response.resum.total_sacs} sacs.
   ```
2. **Refresh Form** (acció B1UP `Menu → View → Refresh` o `Ctrl+W`).
   Necessari perquè el formulari mostri les línies noves.

### Si error (HTTP 4xx o 5xx, o `ok: false`)

1. **Show Message Box** amb el text del camp `error` de la resposta.
   Ex: `Error: ${response.error}`.
2. **No refresh** — el formulari es queda com estava.

## Pas 6 — Testar

1. Guarda la configuració B1UP.
2. Obre una comanda de venda existent al Fat Client
   (ex: `26600126` o qualsevol amb DocStatus='O').
3. Ha d'aparèixer el botó **"Calcular embalatges"** al toolbar.
4. Clica el botó.
5. Espera 2-5 segons.
6. Missatge d'èxit + les línies palet apareixen a la graella.

## Pas 7 — Exportar la configuració

Un cop verificat que funciona:

1. Menú B1UP: **File → Export Configuration Package**.
2. Guarda el fitxer com `docs/b1up_function_button_calcular_embalatges.b1up`
   dins el repo Git.
3. Aquest fitxer permet reimportar la mateixa configuració a un altre
   entorn (test/prod) sense refer-la manualment.

## Diagnòstic

### El botó no apareix

- Verifica **Form Type = 139**.
- Verifica les Visibility Rules (potser són massa restrictives).
- Comprova que B1UP està enabled per l'usuari actual.

### El botó apareix però no fa res

- Verifica que la URL és accessible des del servidor SAP:
  `curl -X POST http://<HOST-APP>:5002/api/afegir-palets/126`.
- Comprova firewall entre servidor SAP i host de l'app.

### HTTP 500 amb error de Service Layer

- Verifica que Service Layer respon: `curl -k https://<sap-server>:50000/b1s/v1/`.
- Si torna a passar el bloqueig `-1116`, reinicia els 4 serveis SL
  (veure `tasks/lessons.md` L1).

### HTTP 400 "no calculable"

- La comanda té només articles `GRA`/`UNI`, o està sota el mínim.
- Comportament esperat: no s'afegeix res, l'operari veu el motiu.

### Línies velles no s'esborren

- Verifica que el UDF `RDR1.U_FCAfegit` existeix (veure guia relacionada).
- Verifica que les línies velles tenen realment `U_FCAfegit='S'`
  (query `SELECT LineNum, U_FCAfegit FROM RDR1 WHERE DocEntry=126`).

---

**Data creació guia**: 2026-07-28.
**Relacionat amb**: `docs/creacio_udf_rdr1_afegit.md`, `tasks/lessons.md`.
