# CLAUDE.md

## 1. Proyecto

Aplicación de cálculo automático de embalaje para pedidos de venta.

Sistema que, a partir de un número de pedido, consulta SQL, aplica reglas logísticas y devuelve una propuesta explicada.

---

## 2. Entorno técnico

- Servidor SQL: vkais\kais  
- Base de datos: GWSV_AGRI  

---

## 3. Objetivo

Eliminar decisiones manuales mediante un motor determinista que:

- estandariza reglas
- evita errores
- genera resultados reproducibles
- explica cada decisión

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
- pedi_num
- cli_codi
- pedi_dire
- pedi_fech

### ek_PedidoLineas
- pedi_num
- linea_num
- art_codi
- linea_unidades
- linea_cantidad

### ARTICLES
- art_codi
- art_descunit (TUnitat)
- art_unitcaixa (UxC)
- art_pes

### CLIENVIO
- cli_codi
- adr_codi

---

## 6. Relaciones SQL

ek_Pedido.pedi_num = ek_PedidoLineas.pedi_num  
ek_PedidoLineas.art_codi = ARTICLES.art_codi  
ek_Pedido.cli_codi = CLIENVIO.cli_codi  
ek_Pedido.pedi_dire = CLIENVIO.adr_codi  

---

## 7. TUnitat (clave)

ARTICLES.art_descunit:

- GRA → excluir  
- UNI → excluir  
- Sxx → incluir (sacos)  

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
Excluir GRA y UNI

### RF2 – Pedido mínimo
- 40 palet  
- 20 despaletizado  

### RF3 – Comanda mínima producció
≥ mínim kg obligatori per article

### RF4 – Artículos especiales
Si no cumple condiciones → NO_CALCULABLE

### RF5 – Prioridad dirección
Dirección sobrescribe artículo

### RF6 – Máximo sacs
min(dirección, UxC)

### RF7 – Base
dirección > artículo > default

---

## 10. Output

- estado
- embalajes
- mensajes
- trazabilidad

---

## 11. Estados

- CALCULADO  
- CALCULADO_CON_AVISOS  
- NO_CALCULABLE  

---

## 12. Pendiente (CRÍTICO)

### Dirección
- tipus_descarrega  
- sacs_x_base  
- max_sacs_palet  
- preval_direccio  

### Artículo
- dimensio_especial  
- aprovisionament_estoc  
- sac_25_especial  
- comanda_minima_produccio

---

## 13. Principios técnicos

- determinista  
- sin lógica en SQL  
- reglas separadas  
- trazabilidad obligatoria  

---

## 14. Definition of Done

- consulta SQL correcta  
- reglas aplicadas  
- resultado explicable  
- sin lógica en queries  

---

## 15. Definición final

Motor de decisión logística determinista basado en SQL.