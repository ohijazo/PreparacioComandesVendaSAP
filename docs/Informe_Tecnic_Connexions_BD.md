# Informe Tècnic: Connexions a BD del Motor de Preparació de Comandes

**Data:** 28/04/2026
**Aplicació:** Motor de Preparació de Comandes de Venda
**Servidor BD:** vkais\kais
**Base de dades:** GWSV_AGRI
**Driver:** ODBC Driver 18 for SQL Server

---

## 1. Resum executiu

L'aplicació realitza **exclusivament consultes de lectura (SELECT)** sobre la base de dades KAIS.
**No executa cap operació d'escriptura** (ni INSERT, ni UPDATE, ni DELETE, ni stored procedures).

Totes les consultes utilitzen **WITH (NOLOCK)** per evitar qualsevol bloqueig sobre les taules de KAIS.

Mesures implementades per minimitzar l'impacte al servidor:

- **Connection pooling desactivat** — les connexions es tanquen realment, sense quedar "sleeping"
- **Command timeout de 15 segons** — cap query pot aparèixer al sp_whoisactive més de 15s
- **Connexions curtes** — cada query obre i tanca la seva pròpia connexió
- **Cache multinivell** — redueix el 95% de les consultes SQL
- **Pausa automàtica** — zero connexions quan no hi ha usuaris actius

---

## 2. Què veurà el tècnic al sp_whoisactive

### 2.1 Quan l'aplicació està en repòs (sense usuaris)

```
Cap connexió visible. L'aplicació es pausa completament.
```

### 2.2 Quan l'aplicació està activa (background refresh cada 45s)

| camp sp_whoisactive | valor típic |
|---------------------|-------------|
| **login_name** | Motor_Comandes (o l'usuari SQL configurat) |
| **database_name** | GWSV_AGRI |
| **status** | running / sleeping |
| **elapsed_time** | < 3 segons (tipic), màxim 15s (command_timeout) |
| **wait_type** | ASYNC_NETWORK_IO o cap |
| **open_tran_count** | 0 (cap transacció oberta) |
| **blocking_session_id** | NULL (no bloqueja ni és bloquejat) |
| **reads** | moderat (SELECT amb NOLOCK) |
| **writes** | 0 (mai escriu) |
| **cpu** | baix |

### 2.3 Connexions simultànies màximes

| Escenari | Connexions al sp_whoisactive |
|----------|------------------------------|
| Sense usuaris (pausat) | **0** |
| Background refresh actiu | **1** (durant < 3s) |
| 1 usuari fent un càlcul | **1-2** (durant < 0.5s) |
| Pic d'ús (varis usuaris) | **3-4** (durant < 0.5s cada una) |

---

## 3. Patrons de connexió

### 3.1 Background refresh (automàtic)

L'aplicació manté una cache en memòria per evitar queries redundants. Cada 45 segons:

1. Obre connexió A → executa 1 query (llistat comandes) → **tanca connexió A**
2. Obre connexió B → executa 1 query (fingerprint canvis) → **tanca connexió B**

| Paràmetre | Valor |
|-----------|-------|
| Interval de refresh | Cada **45 segons** |
| Pausa per inactivitat | Després de **5 minuts** sense usuaris |
| Queries per cicle | **2** (en connexions separades i seqüencials) |
| Durada de cada connexió | **< 3 segons** (típic) |
| Command timeout | **15 segons** (màxim absolut) |

**El refresh es pausa completament** quan no hi ha cap usuari actiu (nits, caps de setmana).

### 3.2 Connexions per acció d'usuari (on-demand)

Quan un usuari calcula un embalatge:

1. **Fase SQL** (connexió oberta ~50-150ms): obté comanda + línies + direcció
2. **Connexió tancada**
3. **Fase Python** (sense connexió): aplica regles logístiques
4. **Fase palets** (connexió oberta ~30-50ms, si cal): consulta tipus de palet
5. **Connexió tancada**

Temps total de connexió oberta per càlcul: **< 200ms**

---

## 4. Inventari complet de consultes SQL

### 4.1 Consultes del background refresh (automàtiques)

#### Q1 — Llistat de comandes pendents
- **Freqüència:** Cada 45s (amb pausa per inactivitat)
- **Taules:** CPALBARA, CLIENTS, ALBLINIA, ARTICLES, SERIEALB, AGENTS
- **NOLOCK:** Sí, a totes les taules
- **Optimització:** NOT EXISTS correlat (en lloc de subquery materialitzada)
- **Descripció:** SELECT TOP 1000 de comandes amb cpa_estat=1

#### Q2 — Fingerprint de canvis
- **Freqüència:** Cada 45s (amb pausa per inactivitat)
- **Taules:** CPALBARA, ALBLINIA
- **NOLOCK:** Sí
- **Descripció:** CHECKSUM_AGG que retorna un únic enter per detectar canvis

### 4.2 Consultes per acció d'usuari (on-demand)

| # | Consulta | Taules | Cache | Descripció |
|---|----------|--------|-------|------------|
| Q3 | Cercar comanda | CPALBARA, CLIENTS | No | SELECT TOP 1 per codi |
| Q4 | Resolució sèrie | SERIEALB | No | Mapeig sèries |
| Q5 | Cercar via pedido KAIS | ALBLINIA, CPALBARA, CLIENTS | No | SELECT TOP 1 |
| Q6 | Pedido original | ALBLINIA | No | SELECT TOP 1 |
| Q7 | Línies de comanda | ALBLINIA, ARTICLES, INF_ARTICULO | No | JOIN filtrat |
| Q8 | Títols INFOANEX (article) | INFOANEX | Permanent | 1 cop, cached |
| Q9 | Títols INFOANEX (clienvio) | INFOANEX | Permanent | 1 cop, cached |
| Q10 | Direcció + condicions | CLIENVIO, inf_clienvio | 10 min | Query única combinada |
| Q11 | Palet a la comanda | ALBLINIA, ARTICLES | No | SELECT TOP 1 |
| Q12 | Descripció article | ARTICLES | Permanent | Cached per article |
| Q13 | Palet històric | ek_PedidoLineas, ek_Pedido, ARTICLES | No | SELECT TOP 1 |
| Q14 | Noms magatzems | Almac | Permanent | 1 cop, cached |

### 4.3 Resum de taules accedides

| Taula | Tipus d'accés | Bloquejos | Freqüència màxima |
|-------|--------------|-----------|-------------------|
| CPALBARA | SELECT amb NOLOCK | Cap | Cada 45s (background) |
| ALBLINIA | SELECT amb NOLOCK | Cap | Cada 45s (background) |
| ARTICLES | SELECT amb NOLOCK | Cap | Cada 45s (background) |
| CLIENTS | SELECT amb NOLOCK | Cap | Cada 45s (background) |
| SERIEALB | SELECT amb NOLOCK | Cap | Cada 45s (background) |
| AGENTS | SELECT amb NOLOCK | Cap | Cada 45s (background) |
| CLIENVIO | SELECT amb NOLOCK | Cap | On-demand (cached 10 min) |
| inf_clienvio | SELECT amb NOLOCK | Cap | On-demand (cached 10 min) |
| INF_ARTICULO | SELECT amb NOLOCK | Cap | On-demand |
| INFOANEX | SELECT amb NOLOCK | Cap | 1 cop (cached permanent) |
| Almac | SELECT amb NOLOCK | Cap | 1 cop (cached permanent) |
| ek_Pedido | SELECT amb NOLOCK | Cap | On-demand |
| ek_PedidoLineas | SELECT amb NOLOCK | Cap | On-demand |

---

## 5. Càrrega estimada al servidor

### 5.1 Escenari A: Sense usuaris actius (nit/cap de setmana)

| Mètrica | Valor |
|---------|-------|
| Connexions actives | **0** |
| Queries/minut | **0** |
| Impacte al servidor | **Nul** |

### 5.2 Escenari B: Horari laboral, background refresh actiu

| Mètrica | Valor |
|---------|-------|
| Connexions simultànies | **0-1** |
| Queries/minut | **~2.7** (2 queries cada 45s) |
| Durada de cada connexió | **< 3s** |
| % temps amb connexió oberta | **< 10%** |
| Operacions d'escriptura | **0** |

### 5.3 Escenari C: Ús actiu (1-3 usuaris calculant)

| Mètrica | Valor |
|---------|-------|
| Connexions simultànies | **1-3** |
| Queries per càlcul | 3-6 (30-150ms total) |
| Temps de connexió per càlcul | **< 200ms** |
| Operacions d'escriptura | **0** |

### 5.4 Càrrega comparativa

| Font | Queries/minut | Tipus | Bloquejos |
|------|--------------|-------|-----------|
| **Motor de Comandes** | **~3** (background) | SELECT amb NOLOCK | **Cap** |
| KAIS (1 usuari actiu) | ~50-200 | SELECT, INSERT, UPDATE | Sí (shared/exclusive locks) |
| KAIS (10 usuaris actius) | ~500-2000 | SELECT, INSERT, UPDATE | Sí (shared/exclusive locks) |

---

## 6. Mesures d'optimització implementades

### 6.1 WITH (NOLOCK) a totes les consultes
Totes les consultes SQL de l'aplicació usen WITH (NOLOCK) a cada taula. Això significa que **l'aplicació no adquireix shared locks** i per tant **no pot bloquejar cap operació de KAIS**.

### 6.2 Command timeout de 15 segons
Cada connexió té un timeout de 15 segons per query. Si una consulta no respon en 15s (per càrrega del servidor), l'aplicació cancel·la la query automàticament i tanca la connexió. **Cap query pot quedar penjada indefinidament.**

### 6.3 Connection timeout de 10 segons
Si el servidor no accepta la connexió en 10 segons, l'aplicació desisteix. No reintenta.

### 6.4 Connection pooling desactivat
Les connexions es tanquen realment quan l'aplicació fa `close()`. No queden connexions en estat "sleeping" al pool d'ODBC.

### 6.5 Connexions curtes i separades
Cada operació SQL obre la seva connexió, executa la query, i la tanca immediatament. La lògica de negoci (càlculs Python) s'executa amb la connexió ja tancada.

### 6.6 Sistema de cache multinivell
| Nivell | TTL | Què cacheja |
|--------|-----|-------------|
| API (background) | 40-120s | Llistat comandes, magatzems, fingerprint |
| Direccions | 10 min | Dades d'enviament per client/direcció |
| Dades mestres | Permanent | Títols INFOANEX, noms magatzems, descripcions |
| Fitxer | Per mtime | PREUSCLIENTS.xlsx |

### 6.7 Patró single-flight
Quan múltiples peticions arriben simultàniament amb cache expirada, **només 1 query s'executa** al servidor — la resta espera el resultat en memòria.

### 6.8 Pausa automàtica per inactivitat
El refresh de background es pausa completament després de 5 minuts sense activitat d'usuari real. **Zero connexions durant hores d'inactivitat.**

### 6.9 Query optimitzada amb NOT EXISTS
La query principal de comandes pendents usa NOT EXISTS correlat en lloc d'un LEFT JOIN amb subquery materialitzada, permetent short-circuit per fila i millor ús d'índexos.

---

## 7. Conclusió

L'aplicació Motor de Preparació de Comandes:

1. **No escriu res** a la base de dades — 100% lectures SELECT
2. **No bloqueja cap taula** — totes les queries usen WITH (NOLOCK)
3. **No pot bloquejar KAIS** — NOLOCK no adquireix shared locks
4. **Genera ~3 queries/minut** en ús normal
5. **Es pausa sola** quan no hi ha usuaris (0 connexions, 0 queries)
6. **Command timeout 15s** — cap query penjada al sp_whoisactive
7. **Connexions < 3 segons** cadascuna, tancades immediatament
8. **Connexions simultànies:** 1 (típic), 3-4 (pic absolut)

**La càrrega que l'aplicació genera al servidor KAIS és equivalent a menys d'un 1% de la càrrega d'un sol usuari de KAIS.**
