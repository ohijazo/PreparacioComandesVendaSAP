# Motor de Preparacio de Comandes de Venda
## Resum de Desenvolupament

**Periode:** 30 de marc - 29 d'abril de 2026
**Dies treballats:** 17
**Total hores estimades:** ~116 hores
**Total commits:** 115

---

## Detall per jornada

| Data | Horari | Commits | H. Dev | H. Proves | H. Altres | H. Total | Bloc de treball |
|------|--------|--------:|-------:|----------:|----------:|---------:|-----------------|
| 30/03 | 10:19 | 1 | 2.0 | 1.5 | - | 3.5 | Versio inicial del motor |
| 31/03 | 15:27 | 1 | 2.0 | 2.0 | - | 4.0 | Implementacio V4: regles RF1-RF9 |
| 01/04 | 08:53 - 16:42 | 6 | 6.5 | 1.5 | - | 8.0 | UI, cerca comandes, tipus descarrega, llista progressiva |
| 02/04 | 08:32 | 1 | 2.0 | 1.5 | - | 3.5 | UX, optimitzacio ompliment palets, agrupacio comandes |
| 03/04 | - | 0 | - | 5.0 | 3.0 | 8.0 | Proves funcionals regles, analisi model de dades SQL |
| 04/04 | - | 0 | - | 4.0 | 4.0 | 8.0 | Proves amb comandes reals, planificacio i documentacio |
| 07/04 | 10:16 - 17:06 | 14 | 6.0 | 2.0 | - | 8.0 | RF4/RF6, filtres, polling, preview palets, mode fosc |
| 08/04 | 11:35 - 17:03 | 7 | 5.5 | 2.5 | - | 8.0 | Migracio CPALBARA/ALBLINIA, desplegament servidor |
| 09/04 | 07:55 - 14:42 | 10 | 5.5 | 2.5 | - | 8.0 | Fixes palets, filtres serie, total unitats, cerca |
| 10/04 | - | 0 | - | 5.5 | 2.5 | 8.0 | Proves validacio migracio, comunicacio i seguiment |
| 14/04 | 11:47 | 1 | 2.0 | 1.0 | - | 3.0 | Fix divisio article en palet mixt cross-base |
| 22/04 | 15:09 - 17:04 | 10 | 3.0 | 2.5 | - | 5.5 | Regles V6, pedido original, max individual per article |
| 23/04 | 08:06 - 14:33 | 12 | 5.5 | 2.5 | - | 8.0 | Aprovisionament estoc, seguretat admin, lookup KAIS |
| 24/04 | - | 0 | - | 5.0 | 3.0 | 8.0 | Proves regles V6 amb casos reals, reunions validacio |
| 27/04 | 10:14 - 15:13 | 9 | 5.0 | 3.0 | - | 8.0 | Optimitzacio SQL, monitoritzacio, cache, single-flight |
| 28/04 | 08:26 - 17:08 | 10 | 6.0 | 2.0 | - | 8.0 | Connexions BD, pool, semaphore, background refresh |
| 29/04 | 07:58 - 16:33 | 33 | 5.5 | 2.5 | - | 8.0 | Regles V7, 4 rondes optimitzacio SQL, batch endpoint, fixes |
| | | **115** | **56** | **46.5** | **12.5** | **116** | |

---

## Resum per area funcional

### 1. Motor de calcul i regles de negoci (~30h)
- Regles RF1-RF9 (filtratge, minim, aprovisionament, especials, general)
- Regles V6: pedido original, max individual, resolucio client
- Regles V7: dimensio especial, sac colagne normal, RF8
- Optimitzacio ompliment palets, cross-base, capes parcials
- Agrupacio de comandes (multiples comandes = 1 calcul)

### 2. Interficie d'usuari (~18h)
- Llista de comandes pendents amb calcul automatitzat d'estats
- Filtres multi-select (serie, magatzem, client)
- Preview visual de palets, mode fosc, ajuda
- Exportacio CSV, calcul en batch
- Cache localStorage per evitar recalculs innecessaris
- Polling intel.ligent amb fingerprint

### 3. Integracio amb base de dades i rendiment (~26h)
- Migracio de ek_Pedido a CPALBARA/ALBLINIA
- Traduccio de series de pedido via SERIEALB
- Resolucio de pedido original (lin_p_serie_ori)
- 4 rondes d'optimitzacio SQL:
  - Caches amb TTL i LRU per totes les queries
  - Batch queries (1 query per N comandes)
  - Endpoint /api/calcular-batch (1 request HTTP per N comandes)
  - SET NOCOUNT ON, autocommit, connexio compartida
  - CTE en lloc d'OUTER APPLY
  - Filtratge per exercici a subqueries
  - Single-flight locks, polling amb jitter
- Monitoritzacio SQL amb dashboard visual

### 4. Infraestructura i desplegament (~8h)
- Desplegament al servidor (scripts, port, .env)
- Seguretat: proteccio endpoints admin
- Control de concurrencia: semaphore 1 connexio
- Tracking d'activitat d'usuaris

### 5. Proves i validacio (~22h)
- Proves funcionals amb comandes reals
- Validacio de dades mestres amb avisos
- Trazabilitat completa de cada decisio
- Coherencia de caches amb invalidacio completa
- Cicles fix-prova amb casos reportats per usuaris

### 6. Analisi, reunions i documentacio (~12h)
- Analisi previa: taules SQL, model de dades, planificacio
- Comunicacio: correus, discussio requisits, validacio casos
- Documentacio: guies desplegament, pagina ajuda

---

## Metriques actuals de rendiment

| Metrica | Valor |
|---------|-------|
| Temps mitja per query | 3ms |
| 100% queries cachejades | Si (TTL 10min o permanent) |
| Connexions simultanees max | 1 |
| Polling interval | 60-75s (amb jitter) |
| Cache fingerprint | 55s TTL + single-flight |
| Errors SQL | 0 |

---

## Tecnologies utilitzades

- **Backend:** Python 3, Flask, pyodbc
- **Frontend:** HTML5, CSS3, JavaScript (vanilla)
- **Base de dades:** SQL Server (GWSV_AGRI)
- **Desplegament:** Windows Server, servei systemd-compatible
- **Assistencia IA:** Claude Code (Anthropic)
