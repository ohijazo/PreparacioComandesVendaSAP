# Fix RF4: l'apilament d'articles especials ignorava la capacitat del palet (29-09-2026)

## Incidència

Un usuari reporta que una comanda de HARINAS LA ENCARNACION (`C321531`) calcula
**11 palets quan n'haurien de ser 12**: la direcció d'enviament té
`Màxim Sacs x Palet = 40` i la comanda porta 455 sacs (455 / 40 = 11,375 → 12).

## Causa

Reproduïda amb la comanda real (`DocEntry 258`, `DB_FARIN_TEST`):

```
Palet  1:  45 sacs (max=40)  [30560x40, 30360x5]   <-- supera el màxim
Palet  2:  45 sacs (max=40)  [30560x40, 30360x5]
Palet  3:  45 sacs (max=40)  [30560x40, 30360x5]
Palets 4-11: 40 sacs
```

El repartiment principal era correcte. El pas d'apilament de RF4 —
`regles.py:1614` — col·loca els articles de dimensió especial a sobre dels palets
existents limitant per `cantidadapilable` (5) però **no per l'espai lliure del
palet receptor**. L'article `30360 SEMOLA FINA` té `QryGroup2='Y'` i els seus 15
sacs anaven a parar a tres palets que ja estaven a 40/40.

La branca d'overflow que crea palets propis per als sacs que no caben ja existia
i estava provada, però era **inabastable**: com que cap palet es rebutjava per
estar ple, `remaining` sempre arribava a 0.

## Fet

- [x] Reproduir amb la comanda real de l'usuari
- [x] `regles.py`: comprovació de l'espai lliure del palet receptor
- [x] `regles.py`: traça pròpia per al cas "cap palet té espai lliure"
- [x] `regles.py`: invariant de sortida a `aplicar_regles` (`AVÍS` +
      `CALCULAT_AMB_AVISOS` si algun palet supera el seu màxim)
- [x] Dos tests de regressió, **verificats contra el codi anterior** (fallen amb
      `Palet 1: 45 sacs amb max=40`)
- [x] Sincronitzar `tests/test_rf4.py` a les dues variants (la còpia de SAP anava
      dos tests enrere)
- [x] Branca de desplegament `fix/rf4-capacitat-apilament` (`e279128`) pujada
- [ ] **Desplegar al servidor** i confirmar-ho amb l'usuari

## Resultat amb la comanda del cas

```
Palets  1-9 : 30560 x40         (max=40)
Palet  10   : 30180 x40
Palet  11   : 30180x20 + 30130x20
Palet  12   : 30360 x15          <-- sèmola, tipus_palet='01030'
```

12 palets, cap per sobre del màxim. El palet nou surt amb el mateix tipus que els
altres onze, així que l'operari només veurà la línia de palet passar d'11 a 12.

## Desplegament

La part delicada. Kais en producció corre `9691d38` (30 de juny) i el seu
`regles.py` — que és el que **SAP importa al servidor** — no tenia ni tan sols la
branca d'overflow de la qual depèn l'arreglo (`a83fed8`, mai pujat).

Branca `fix/rf4-capacitat-apilament` = `9691d38` + `db275ce` + `a83fed8` + el fix.
Deixa **fora** `332a64a` (avisos a fabricació, +207 línies a `mailer.py`, mòdul
compartit amb SAP).

```bash
cd /var/www/comandes-venda
sudo -u www-data git fetch origin
sudo -u www-data git reset --hard origin/fix/rf4-capacitat-apilament
sudo systemctl restart comandes-venda-sap
sudo systemctl restart comandes-venda
```

⚠️ Mentre el directori de Kais estigui en aquesta branca, **no fer servir el botó
"actualitzar" de Kais**: fa `git pull origin main` i tornaria a `9691d38`.

## Revisió

### Decisions

- **L'arreglo va al `regles.py` compartit**, no a un post-pass de la variant SAP.
  És un bug del motor i el seu lloc és el motor; duplicar-lo hauria fet divergir
  les dues variants.
- **La sèmola va a un palet propi** en lloc de reservar espai als palets base.
  Dona els 12 palets que espera l'usuari i reutilitza la branca d'overflow que ja
  existia, en lloc de reescriure el repartiment.
- **La invariant emet `AVÍS`, no excepció.** Llençar trencaria el càlcul de
  comandes en producció per una anomalia de la qual encara se'n pot treure un
  resultat aprofitable.
- **La feature d'avisos a fabricació es queda fora del desplegament.** Toca
  `mailer.py`, compartit amb SAP, i envia correus: mereix la seva pròpia finestra.

### Fitxers

- `P:\preparacioComandesVenda\regles.py` — capacitat, traça, invariant
- `P:\preparacioComandesVenda\tests\test_rf4.py` — dos tests nous
- `tests/test_rf4.py` (SAP) — sincronitzat
- `tasks/lessons.md` — L14
- `tasks/fase2_progress.md` — §2.10

### Pendent per a una altra passada

Tres defectes més al mateix fitxer, trobats però no tocats (cap explica el cas
reportat, i tots impliquen tocar més codi compartit):

1. **RF11 supera el màxim de la direcció** (`regles.py:403-404`): assigna
   `max_sacs = art_uxc` després de `_aplicar_criteri_restrictiu`, així que una
   direcció amb màxim 40 i un article amb `UxC=45` dona palets de 45.
2. **`art_max_map` fora d'àmbit** (definit a `regles.py:982` dins el bucle de
   grups, usat a `:1332` fora): la comprovació per article dels micro-palets
   queda neutralitzada en comandes multi-base, i si `grups` queda buit hi ha
   `NameError`.
3. **RF14 no comprova el màxim per article** (`regles.py:1829-1914`).

També cal endreçar el repo de Kais: 4 commits sense pujar i l'arbre brut.
