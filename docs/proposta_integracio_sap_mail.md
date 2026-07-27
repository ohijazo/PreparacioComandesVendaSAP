# Text del mail al consultor SAP

> Aquest fitxer conté el text del mail per copiar/pegar al client de correu.
> Adjunta el fitxer `proposta_integracio_sap.docx` que hi ha en aquest mateix directori.
> Substitueix els placeholders `[...]` abans d'enviar.

---

## Assumpte

```
Consulta: integració del motor d'embalatges dins SAP B1
```

---

## Cos del mail (català)

```
Hola [Nom del consultor],

Volia compartir amb tu una idea que estem valorant a l'empresa i tenir la teva
opinió abans de tirar-la endavant.

Actualment tenim en marxa un motor de càlcul d'embalatges de comandes de venda
(Python + Flask) que funciona en dues variants — una llegint de Kais i una altra
llegint de SAP. Ens agradaria fer un pas més: que el resum del càlcul es vegi
directament al formulari Comanda de venda de SAP, sense que l'operari hagi
d'obrir cap altra aplicació per saber-ho.

El plantejament és fer-ho amb el mínim impacte a SAP: afegiríem només 2 UDFs a
la taula ORDR (amb el prefix U_FC per coherència amb els que ja tens creats) i
un worker Python en background els aniria actualitzant automàticament via
Service Layer.

Adjunto un document (Word editable) amb l'explicació completa:

  • Què fa el motor actual i les regles que aplica.
  • Com pensem que quedaria dins SAP.
  • Els 2 UDFs concrets que crearíem i on van ubicats.
No et demanem cap feina tècnica — la implementació la farà l'equip intern.
Només et volem plantejar la idea i saber si li veus algun problema o si tens
alguna alternativa millor abans de començar-ho a fer.

Si prefereixes anotar comentaris directament al Word, és editable — pots
respondre inline i me'l retornes. També podem fer una reunió breu (30 min)
quan et vagi bé si prefereixes comentar-ho en directe.

Gràcies per dedicar-hi una estona.

Salutacions,

Oscar Hijazo
[càrrec]
Agrienergia — Farinera Coromina
[telèfon]
[email]
```

---

## Notes de personalització

Abans d'enviar:

- [ ] Substituir `[Nom del consultor]` pel nom real.
- [ ] Substituir `[càrrec]`, `[telèfon]` i `[email]` de contacte.
- [ ] Adjuntar el fitxer `docs/proposta_integracio_sap.docx`.
- [ ] Considerar afegir en còpia qualsevol altre stakeholder rellevant.

## Fitxers relacionats

- `docs/proposta_integracio_sap.docx` — document adjunt (Word editable).
- `scripts/build_proposta_sap.py` — script generador (per regenerar amb canvis).
