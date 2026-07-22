# Motor de Preparació de Comandes de Venda

**URL:** http://comandes.agrienergia.local/ · **Estat:** en producció · **Període dev:** 2026 (86,6 h acumulades)

---

## Descripció

Motor de càlcul automàtic per a la preparació de comandes de venda amb regles de negoci avançades (RF1–RF14, versions V4–V9). Interfície web que consulta la base de dades **KAIS (SQL Server)**, aplica lògica determinista d'embalatge i mostra preview visual dels palets a preparar amb traçabilitat completa de cada decisió. Substitueix la planificació manual operari per operari per un càlcul reproduïble i monitorat.

## Necessitat

Abans, cada operari planificava palets aplicant les regles de memòria, amb temps mort entre 3 i 4 minuts per comanda i errors recurrents (~5 per setmana) que provocaven repreparació, devolucions i descontrol d'estoc. La complexitat creixent de les regles (mínim de comanda, aprovisionament d'estoc, sacs colagne, fusió de residuals, dimensions especials) feia impossible mantenir-les actualitzades als operaris manualment.

## Recursos dedicats

| Concepte | Valor |
|---|---|
| Hores de desenvolupament | **86,6 h** |
| Cost intern estimat (a 33,5 €/h cost empresa) | **2.901 €** |
| Stack tècnic | Python 3 · Flask · pyodbc · SQL Server KAIS · JavaScript vanilla |

## Retorn

### Quantitatiu (estudi ROI 2026-05-20)

| Indicador | Abans → Ara | Millora |
|---|---|---|
| Temps per comanda | 3–4 min → 1 min | **−75 %** |
| Errors / setmana | 5 → 1 | **−80 %** |
| Hores alliberades / any | **635 h** (0,37 FTE) | — |
| Estalvi anual (cas central 34 €/h) | **≈ 21.590 €/any** | — |
| **Payback** | **~1,6 mesos** · ROI any 1: **+600–800 %** | — |

### Qualitatiu

- **Decisions reproduïbles:** mateix càlcul independentment de qui prepari la comanda.
- **Traçabilitat completa:** cada palet conté quina regla l'ha generat.
- **Preview visual de palets** abans d'imprimir, evita reprepar feina.
- **Rendiment estable** (3 ms/query, 0 errors SQL) amb dashboard de monitorització.

## Veredicte

**Inversió de 2.901 € → retorn de ~21.590 €/any.** El projecte amb millor relació inversió/retorn del portafoli: payback < 2 mesos, ROI any 1 > 600 %. Estudi complet a `docs/Estudi_ROI_Motor_Comandes.docx`.
