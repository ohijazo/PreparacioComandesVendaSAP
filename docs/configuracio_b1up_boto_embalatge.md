# Configuració B1UP — Botó "Calcular embalatges" al Sales Order

Aquesta guia configura el botó **"Calcular embalatges"** dins B1UP de
Boyum que apareix al formulari **Comanda de venda** (form 139) de SAP B1.
Al clicar, executa un petit codi C# que:

1. Verifica que la comanda estigui desada i sense canvis pendents.
2. Fa `POST http://localhost:5002/api/afegir-palets/<DocEntry>` al Flask.
3. Flask executa el motor RF1-RF14 i insereix les línies palet físiques
   (`01030 PALET FUSTA EUROPEU`, `01010 BASE PALET`, `01060 PALET FUSTA
   AMERICA`, etc.) amb `U_FCAfegit='S'` per idempotència.
4. Refresca automàticament el registre del form perquè l'operari vegi les
   línies noves sense haver de clicar cap altre botó.

## Prerequisits

1. **UDF `RDR1.U_FCAfegit`** creat — veure `docs/creacio_udf_rdr1_afegit.md`.
2. **App Flask** corrent al port 5002 al servidor
   (`http://<host-app>:5002/api/afegir-palets/<N>`).
3. **B1UP instal·lat i configurat** al Fat Client de SAP.
4. **Accés al B1UP Configurator** amb l'usuari SAP que fa la config.

## Pas 1 — Crear la Función Universal (UF-038)

1. Obre B1UP Configurator: menú **Boyum IT → B1 Usability Package → Configurator**.
2. **Función → Función Universal → Añadir**.
3. Omple:

| Camp | Valor |
|---|---|
| **Código** | `UF-038` (o l'autoassignat) |
| **Nombre** | `HTTP Motor Embalatges` |
| **Clase** | **`Código dinámico (.NET SDK)`** |

4. Al camp gran de codi, **enganxa el contingut de `docs/b1up_uf038_calcular_embalatges.cs`** (versionat al repo).
5. **Actualizar**.

### Punts clau del codi

- Usa els paràmetres **`application`** i **`form`** (locals a la signatura
  `DynamicCode`). **NO** usa `SBO_Application` (no existeix a B1UP).
- Obté DocEntry via `form.DataSources.DBDataSources.Item("ORDR").GetValue("DocEntry", 0)`.
- Refresca amb `application.ActivateMenuItem("1304")` amb la precondició
  `form.Mode == fm_OK_MODE`. Si el form té canvis pendents, mostra
  missatge demanant desar primer.

Detall complet dels gotchas: `tasks/lessons.md` L5.

## Pas 2 — Vincular la UF a un botó del form 139

1. B1UP Configurator: **Function → Function Buttons**.
2. **Filtra per Form Type = 139** (Sales Order).
3. **Obre la FB existent** per aquest form (a l'entorn actual és `FB-004`).
   ⚠️ No creïs una FB nova — B1UP configura els botons **per grup**
   dins la FB del form (veure `tasks/lessons.md` L3).
4. **Afegeix una línia nova** a la graella "Botones":

| Camp | Valor |
|---|---|
| **Activo** | ✅ |
| **Título** | `Calcular embalatges` |
| **Función** | `Función universal` |
| **Función universal** | `UF-038` |
| **OK** | ✅ (fa el botó visible en mode View) |

5. **Actualizar** per desar.

## Pas 3 — Provar

1. Obre una comanda de venda existent al Fat Client (ex: `26600128`).
2. Ha d'aparèixer el botó **"Calcular embalatges"** al toolbar del form.
3. Clica'l.
4. Espera 2-5s. Al StatusBar (peu del SAP) surt:
   `Embalatges recalculats i comanda actualitzada.`
5. Les línies palet apareixen automàticament a la graella del formulari.

## Pas 4 — Exportar la configuració

Un cop verificat que funciona:

1. B1UP Configurator: **File → Export Configuration Package**.
2. Guarda el fitxer com `docs/b1up_function_button_calcular_embalatges.b1up`
   dins el repo Git.
3. Permet reimportar la mateixa configuració a un altre entorn (prod)
   sense refer-la manualment.

## Diagnòstic

### El botó no apareix al form

- Verifica que la línia està a la FB del form correcte (Form Type = 139).
- Verifica **Activo** ✅ i almenys una de **Añadir/Buscar/OK** marcada.
- Reinicia SAP Fat Client (B1UP cachea la config).

### "El nombre 'SBO_Application' no existe"

Codi antic copiat d'un tutorial. Usar **`application`** en lloc de
`SBO_Application`. Similar per `form`.

### "Cannot activate a disabled menu item [66000-75]"

`ActivateMenuItem("1304")` cridat quan el form té canvis pendents. El
codi al repo ja té la precondició `form.Mode == fm_OK_MODE`; si l'usuari
prem el botó amb la comanda a mig editar, veurà un missatge demanant
desar-la primer.

### "General Failure" / errors HTTP

- Verifica que Flask corre: `curl.exe -s http://localhost:5002/api/admin/sync-status`.
- Si torna a passar el bloqueig SL `-1116`, reinicia els 4 serveis SL
  (`tasks/lessons.md` L1).

### La comanda diu "no processable" (NO_CALCULABLE)

- Només articles `GRA`/`UNI`, o falta configuració a l'article a SAP.
- Comportament esperat: no s'afegeix res, l'operari veu el motiu al popup.

### SOTA_MINIM — sí calcula i afegeix

Tot i estar sota mínim, el motor calcula la proposta d'embalatges (mateix
comportament que Kais) i les línies s'afegeixen. El popup mostra el
missatge de RF2 STOP com a informació.

### Les línies palet velles queden en gris

Comportament esperat: el nostre patró in-place recicla línies del mateix
`ItemCode` (0 residus grisos). Si un canvi de regla fa que un tipus de
palet desaparegui, la línia vella no es pot esborrar (limitació SL,
`tasks/lessons.md` L2 G2.1) → queda tancada visualment en gris. No afecta
totals ni albarà. Pot amagar-se amb **Ajustes de formulario → Ocultar
líneas cerradas**.

---

**Data actualització**: 2026-07-29.
**Relacionat amb**: `docs/creacio_udf_rdr1_afegit.md`,
`docs/b1up_uf038_calcular_embalatges.cs`, `tasks/lessons.md` (L1-L5).
