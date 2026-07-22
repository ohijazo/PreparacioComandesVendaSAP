-- ============================================================
-- Indexos recomanats per millorar rendiment de consultes
-- Executar al servidor SQL per un DBA
-- ============================================================

-- Index per obtenir_ultimes_comandes: filtra per eje_ejercicio + cpa_estat
-- Millora el NOT EXISTS subquery i el filtre principal
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_CPALBARA_eje_estat')
    CREATE NONCLUSTERED INDEX IX_CPALBARA_eje_estat
    ON CPALBARA (eje_ejercicio, cpa_estat)
    INCLUDE (sal_codigo, cpa_albara, cli_codi, adr_codi, cpa_fechaalta, age_codi);

-- Index per ALBLINIA: accelera JOINs de linies per comanda
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_ALBLINIA_eje_sal_alb')
    CREATE NONCLUSTERED INDEX IX_ALBLINIA_eje_sal_alb
    ON ALBLINIA (eje_ejercicio, sal_codigo, cpa_albara)
    INCLUDE (art_codi, lin_linia, lin_unit, lin_p_serie_ori, Lin_P_Numero, Lin_P_Serie);

-- Index per al NOT EXISTS de GRA a obtenir_ultimes_comandes
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_ARTICLES_descunit')
    CREATE NONCLUSTERED INDEX IX_ARTICLES_descunit
    ON ARTICLES (art_descunit)
    INCLUDE (art_codi);

-- Index per INF_ARTICULO: accelera el LEFT JOIN pivot
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_INF_ARTICULO_titulo')
    CREATE NONCLUSTERED INDEX IX_INF_ARTICULO_titulo
    ON INF_ARTICULO (INF_TITULO)
    INCLUDE (art_codi, INF_VALOR);
