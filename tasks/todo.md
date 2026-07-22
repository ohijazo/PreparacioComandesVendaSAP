# Pla d'implementació V9 (08-05-26)

Origen: `REGLES PREPARACIÓ DE COMANDES DE VENDA V9.docx`
Diff respecte V8: 2 regles noves (RF11, RF12). RF1-RF10 inalterades.

## Cas reportat que motiva V9

Comanda **01/0003442** client 00271060:
- 30860 PIRINEUS (S25, 80 sacs, max=40 dir)
- 30730 MEULE T80 (S25, 60 sacs, UxC=30, aprovisionament_estoc)
- 33851 GRAN FORÇA (S25, 40 sacs, max=40 dir)

Comportament actual (V8): palets mixtos 30 MEULE + 10 GRAN FORÇA = 40 sacs.
Comportament esperat (V9, RF12): MEULE no es barreja perquè 60 % 30 = 0.

## Regles noves

### RF11 — Comandes amb sacs S05/S10
Si total_sacs(S05+S10) ≥ 15 → max_sacs = UxC per aquells articles.

### RF12 — No barreja si quantitat múltiple del max
Si `sacs_article % max_efectiu == 0` → article ocupa palets propis (no es barreja).

`max_efectiu` = el max aplicat a l'article (`config.max_sacs` després de
`_aplicar_criteri_restrictiu`).

## Tasques

- [x] **T1** Implementar RF11 a `regles.py`:
  - Pre-calcular `total_s05_s10` a `_construir_embalatges`
  - Passar `aplica_rf11` com a paràmetre a `_determinar_config_article`
  - Si aplica, override `max_sacs = art_uxc` per S05/S10 (no aplicar `_aplicar_criteri_restrictiu`)

- [x] **T2** Implementar RF12 a `regles.py`:
  - Separar articles en `configs_no_barreja` / `configs_barreja`
  - Crear palets dedicats per `configs_no_barreja` (flag `es_no_barreja=True`)
  - Protegir optimitzacions cross-base i micro-palets per excloure aquests palets
  - Afegit `es_no_barreja: bool = False` a `models.Embalatge`

- [x] **T3** Afegir traçabilitat RF11/RF12 (línies "RF11:" i "RF12:" amb branca No aplica)

- [x] **T4** Actualitzar `CLAUDE.md` (afegides RF11 i RF12 a secció 9)

- [x] **T5** Tests existents: 55/55 passen (cap regressió)

## Casos a verificar

| Cas | Article | Sacs | Max | sacs%max | Comportament |
|---|---|---|---|---|---|
| 01/0003442 | MEULE T80 | 60 | 30 | 0 | No barreja → 2 palets de 30 |
| 01/0003442 | PIRINEUS | 80 | 40 | 0 | No barreja → 2 palets de 40 |
| 01/0003442 | GRAN FORÇA | 40 | 40 | 0 | No barreja → 1 palet de 40 |
| 51/0003286 (regressió) | 4 articles 39+4+1+1 | 39 | 40 | 39 | Barreja OK → 1 palet de 45 |

## Revisió (08-05-26)

### Verificació funcional

**Cas 01/0003442** (motivació V9): ✓ correcte
```
Palet 1: 33851 (40 sacs)
Palet 2: 30860 (40 sacs)
Palet 3: 30860 (40 sacs)
Palet 4: 30730 MEULE T80 (30 sacs)  ← respecta UxC=30, sense barreja
Palet 5: 30730 MEULE T80 (30 sacs)  ← respecta UxC=30, sense barreja
```

**Cas regressió 51/0003286** (39+4+1+1=45): ✓ segueix produint 1 palet barrejat de 45 sacs.

### Decisions arquitectòniques

- **Interpretació RF12**: `max_efectiu = config.max_sacs` (resultat de `_aplicar_criteri_restrictiu`, és a dir, `min(direcció, UxC, defecte)`). Aquesta és la lectura coherent amb el glossari V9 que defineix Maxim_sacs_palet com "el criteri més restrictiu".
- **Flag al model**: nou camp `es_no_barreja` a `Embalatge` (en lloc de mantenir un set local) per supervivir als renumeratges de palet i ser comprovat a totes les optimitzacions.
- **Optimitzacions protegides**: cross-base apilament i micro-palets exclouen palets `es_no_barreja=True`. Les optimitzacions intra-grup ja queden filtrades implícitament pel filter `palet_num >= palet_start`.
- **RF11 com override**: aplicat *després* de `_aplicar_criteri_restrictiu` perquè la regla és més específica i pot ser més permissiva que la dirección.

### Fitxers modificats

- `models.py` — afegit `es_no_barreja` a `Embalatge`
- `regles.py` — `_determinar_config_article` (RF11), `_construir_embalatges` (RF12 + traces)
- `CLAUDE.md` — secció 9 amb RF11 i RF12
