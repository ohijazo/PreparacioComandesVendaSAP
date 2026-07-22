# CLAUDE.md — Variant SAP B1

> Aquesta és la **còpia SAP** de l'aplicació. La còpia original (Kais) viu a
> `P:\preparacioComandesVenda\` i continua en producció al port 5001 llegint
> de la base de dades de Kais (`vkais\kais / GWSV_AGRI`). **Aquesta còpia no
> ha de modificar cap arxiu de la variant Kais.**

## 0. Arquitectura de la còpia SAP

- **Codi específic SAP** (viu aquí, es pot modificar lliurement):
  `app.py`, `motor.py`, `consultes.py`, `_bootstrap.py`, `.env`, `templates/`, `static/`.
- **Mòduls compartits** amb Kais (importats via `sys.path` shim; **NO editar aquí**):
  `models.py`, `regles.py`, `mailer.py`. Es resolen a
  `KAIS_APP_PATH` (per defecte `..\preparacioComandesVenda`).
- **Bootstrap**: `_bootstrap.py` insereix `KAIS_APP_PATH` al `sys.path` al principi
  de qualsevol punt d'entrada (`app.py`, `motor.py`, `consultes.py`,
  `tests/conftest.py`). Sense això, els imports de `models`/`regles`/`mailer` fallen.
- **Port**: 5002 per defecte (override amb `PORT` env var).

## 1. Proyecto

Aplicación de cálculo automático de embalaje para pedidos de venta —
**variant que llegeix de SAP Business One**.

Manté el mateix motor de regles (RF1-RF14) que la variant Kais; només canvia
la capa de dades (`consultes.py`).

---

## 2. Entorno técnico

- Servidor SQL SAP: `<pendent>` (SAP B1 sobre SQL Server)
- Base de dades: `DB_FARINERA_TEST`
- Usuari: `sa`
- Aplicació canònica Kais: `P:\preparacioComandesVenda`

---

## 3. Objetivo

Eliminar decisiones manuales mediante un motor determinista que:

- Estandariza reglas
- Evita errores
- Genera resultados reproducibles
- Explica cada decisión

---

## 4. Flujo principal

1. Input: número de pedido
2. Consulta SQL
3. Construcción de contexto
4. Aplicación de reglas
5. Generación de embalajes
6. Respuesta

---

## 5. Tablas principales

### ek_Pedido
| Campo | Descripción |
|---|---|
| `pedi_num` | Número de pedido |
| `cli_codi` | Código de cliente |
| `pedi_dire` | Dirección de entrega |
| `pedi_fech` | Fecha del pedido |

### ek_PedidoLineas
| Campo | Descripción |
|---|---|
| `pedi_num` | Número de pedido |
| `linea_num` | Número de línea |
| `art_codi` | Código de artículo |
| `linea_unidades` | Unidades de línea |
| `linea_cantidad` | Cantidad de línea |

### ARTICLES
| Campo | Descripción |
|---|---|
| `art_codi` | Código de artículo |
| `art_descunit` | Tipo de unidad (TUnitat) |
| `art_unitcaixa` | Unidades por caja (UxC) |
| `art_pes` | Peso del artículo |

### CLIENVIO
| Campo | Descripción |
|---|---|
| `cli_codi` | Código de cliente |
| `adr_codi` | Código de dirección |

---

## 6. Relaciones SQL

```
ek_Pedido.pedi_num    = ek_PedidoLineas.pedi_num
ek_PedidoLineas.art_codi = ARTICLES.art_codi
ek_Pedido.cli_codi    = CLIENVIO.cli_codi
ek_Pedido.pedi_dire   = CLIENVIO.adr_codi
```

---

## 7. TUnitat (clave)

`ARTICLES.art_descunit`:

| Valor | Acción |
|---|---|
| `GRA` | Excluir |
| `UNI` | Excluir |
| `Sxx` | Incluir (sacos) |

---

## 8. Pipeline de cálculo

1. Cargar pedido
2. Cargar líneas
3. Join artículos
4. Join dirección
5. Filtrar líneas
6. Validar reglas
7. Calcular embalajes

---

## 9. Reglas funcionales

### RF1 – Filtrado
Excluir `GRA` y `UNI`.

### RF2 – Pedido mínimo
- 40 palet
- 20 despaletizado

### RF3 – Comanda mínima producció
≥ mínim kg obligatori per article.

### RF4 – Artículos especiales
Si no cumple condiciones → `NO_CALCULABLE`.

### RF5 – Prioridad dirección
Dirección sobrescribe artículo.

### RF6 – Máximo sacs
`min(dirección, UxC)`

### RF7 – Base
`dirección > artículo > default`

### RF8 – Sac colagne multi-article
Quan hi ha ≥ 2 articles amb `sac_colagne_normal = SI` a la comanda:
- **Total colagne ≤ 26 sacs**: condicions de la direcció (com RF9).
- **Total colagne ≥ 27 sacs**: base=3, max=30, palet fusta europeu (PALET) o BasePalet (MANUAL). **Aquest cas estricte preval sobre RF7 (aprovisionament d'estoc)**: si un article és alhora colagne i d'estoc, RF8 estricte mana.

Prioritat: RF6 (sac_25_especial) > RF8 estricte (≥27 colagne multi) > RF7 (estoc) > RF8 ≤26 > RF9.

### RF11 – S05/S10 max=UxC
Si la comanda inclou ≥ 30 sacs amb TUnitat S05 i/o S10, el màxim de sacs per palet d'aquests articles s'iguala a la seva UxC (override sobre la dirección).

Si l'article té `cantidadapilable` definida, RF11 també l'imposa com a `sacs_x_base` (la UxC del proveïdor i el seu `cantidadapilable` van junts: barrejar `max=UxC` amb la base de la direcció produeix un nombre de capes físicament impossible). Exemple: 60190 té UxC=132 i cantidadapilable=11 → palet de 12 capes × 11 sacs = 132 sacs.

### RF12 – No barreja si quantitat múltiple del max
Si `sacs_article % max_efectiu == 0`, l'article ocupa palets dedicats sense barrejar-se amb altres articles. `max_efectiu` = `min(direcció, UxC, defecte)`.

### RF13 – Override palet per (client, article)
Per a combinacions específiques `(cli_codi, art_codi)` definides a `OVERRIDES_PALET_CLIENT`, el palet de condicions de la direcció del client preval sobre el tipus de palet assignat per RF7 (palet d'estoc). Aplicat com a post-pass: qualsevol palet que contingui un article amb override veu el seu `tipus_palet` forçat a "condicions direcció".

Casos definits actualment: `(00301614, 40150)` — Acid Cafe + Ecològica Força usen el palet americà del client en lloc del palet d'estoc.

### RF14 – Fusió de palets residuals amb capacitat lliure
Post-pass després de RF13. Quan, després d'aplicar totes les regles, queda un palet "petit" (residu) i existeix un altre palet compatible amb prou capacitat lliure, el residu s'absorbeix per estalviar un palet físic.

Condicions de fusió (tots han de complir-se):
- `total_sacs(font) ≤ max(font) // 3` (llindar de "petit").
- `total_sacs(font) + total_sacs(receptor) ≤ max(receptor)` (capacitat física).
- Compatibilitat de tipus de palet:
  - `tipus_palet(font) == tipus_palet(receptor)` (mateix tipus), o
  - `tipus_palet(font) == "01030"` (europeu) i `tipus_palet(receptor) is None` (condicions direcció, presumiblement ≥ europeu).
- Cap dels palets pot ser `es_no_barreja` (RF12) ni `es_embalatge_propi` (RF4).

Tria del receptor si hi ha múltiples candidats: el palet amb més sacs actuals (millor compactació).

Els sacs traslladats adopten la base del palet receptor (`sacs_x_base=0` al `PaletContingut`). La traçabilitat marca clarament la fusió amb prefix `RF14:`.

Cas típic: residu de colagne (RF8 estricte, base=3, palet europeu) que cap dins el palet d'estoc del client (RF7+RF13, base=5, palet condicions direcció).

---

## 10. Output

- `estado`
- `embalajes`
- `mensajes`
- `trazabilidad`

---

## 11. Estados

| Estado | Significado |
|---|---|
| `CALCULADO` | Cálculo completado sin incidencias |
| `CALCULADO_CON_AVISOS` | Completado con advertencias |
| `NO_CALCULABLE` | No se puede calcular |

---

## 12. Pendiente (CRÍTICO)

### Dirección
- `tipus_descarrega`
- `sacs_x_base`
- `max_sacs_palet`
- `preval_direccio`

### Artículo
- `dimensio_especial`
- `aprovisionament_estoc`
- `sac_25_especial`
- `comanda_minima_produccio`

---

## 13. Principios técnicos

- **Determinista**: el mismo input siempre produce el mismo output
- **Sin lógica en SQL**: las queries solo recuperan datos, nunca deciden
- **Reglas separadas**: cada regla funcional es un módulo independiente
- **Trazabilidad obligatoria**: toda decisión queda registrada y explicada

---

## 14. Definition of Done

- [ ] Consulta SQL correcta
- [ ] Reglas aplicadas
- [ ] Resultado explicable
- [ ] Sin lógica en queries

---

## 15. Definición final

Motor de decisión logística determinista basado en SQL.

---

## 16. Orquestación del flujo de trabajo

### 16.1 Modo de planificación predeterminado

- Entrar en **modo planificación** para CUALQUIER tarea no trivial (3+ pasos o decisiones arquitectónicas).
- Si algo sale mal, **PARAR** y replantear inmediatamente — no seguir presionando.
- Usar el modo planificación también en los pasos de **verificación**, no solo en la construcción.
- Escribir especificaciones detalladas desde el principio para reducir ambigüedad.

### 16.2 Estrategia de subagentes

- Usar subagentes de forma generosa para mantener limpia la ventana de contexto principal.
- Delegar a subagentes: investigación, exploración y análisis paralelo.
- Para problemas complejos, lanzar más cómputo mediante subagentes.
- **Una tarea por subagente** para mantener el foco.

### 16.3 Bucle de superación continua

- Tras CUALQUIER corrección del usuario: actualizar `tasks/lessons.md` con el patrón aprendido.
- Escribir reglas explícitas para evitar repetir el mismo error.
- Iterar sin piedad sobre estas lecciones hasta reducir la tasa de errores.
- **Revisar `tasks/lessons.md` al inicio de cada sesión** del proyecto.

### 16.4 Verificación antes de cerrar

- Nunca marcar una tarea como completada sin demostrar que funciona.
- Aplicar comportamiento diferencial entre cambios mayores y menores cuando sea relevante.
- Preguntarse: *"¿Aprobaría esto un ingeniero senior?"*
- Realizar pruebas, comprobar logs, demostrar la corrección.

### 16.5 Exigencia de elegancia (equilibrada)

- Para cambios no triviales: pausar y preguntar *"¿hay una forma más elegante?"*
- Si una solución parece un parche: *"Sabiendo todo lo que sé ahora, implemento la solución elegante."*
- **Omitir este paso** para soluciones simples y evidentes — sin sobreingeniería.
- Cuestionar el propio trabajo antes de presentarlo.

### 16.6 Corrección autónoma de errores

- Ante un informe de error: simplemente **arreglarlo**. No pedir que te guíen paso a paso.
- Localizar logs, errores y pruebas fallidas — y resolverlos.
- Cero necesidad de cambio de contexto por parte del usuario.
- Ir a arreglar pruebas de CI fallidas sin esperar instrucciones.

---

## 17. Gestión de tareas

| Paso | Acción |
|---|---|
| 1. Planificar primero | Escribir el plan en `tasks/todo.md` con elementos comprobables |
| 2. Verificar el plan | Revisar antes de comenzar la implementación |
| 3. Seguimiento del progreso | Marcar ítems como completados mientras se avanza |
| 4. Explicar los cambios | Resumen de alto nivel en cada paso |
| 5. Documentar resultados | Añadir sección de revisión a `tasks/todo.md` |
| 6. Capturar lecciones | Actualizar `tasks/lessons.md` tras cada corrección |

---

## 18. Principios fundamentales

- **Simplicidad primero**: hacer cada cambio lo más sencillo posible. Impacto mínimo en el código.
- **Sin pereza**: encontrar las causas raíz. Sin soluciones temporales. Estándares de desarrollador senior.
- **Impacto mínimo**: los cambios solo deben afectar lo estrictamente necesario. Evitar introducir nuevos errores.
