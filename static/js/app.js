document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("search-form");
    const input = document.getElementById("pedi-num");
    const btn = document.getElementById("btn-calcular");
    const emptyState = document.getElementById("empty-state");
    const loadingState = document.getElementById("loading-state");
    const errorState = document.getElementById("error-state");
    const resultState = document.getElementById("result-state");
    const btnHome = document.getElementById("btn-home");
    const btnForcar = document.getElementById("btn-forcar");

    let lastPediNum = null;
    let lastResultData = null;  // Últim resultat per exportar/imprimir
    let currentController = null;  // AbortController per cancel·lar peticions anteriors
    let _allComandes = [];  // Totes les comandes carregades per detecció d'agrupació

    // --- Persistència de filtres amb localStorage ---
    const FILTRES_KEY = "comandes_filtres";
    const ORDRE_KEY = "comandes_ordre";

    // Estat d'ordenació actual de la taula de comandes
    let _sortState = { key: null, type: null, dir: null };
    try {
        const raw = localStorage.getItem(ORDRE_KEY);
        if (raw) {
            const parsed = JSON.parse(raw);
            if (parsed && parsed.key && parsed.dir) _sortState = parsed;
        }
    } catch (e) { /* ignorem */ }

    function _guardarFiltres() {
        try {
            const filtres = {
                text: document.getElementById("filtre-text").value,
                estat: document.getElementById("filtre-estat").value,
                tipusDesc: document.getElementById("filtre-tipus-desc").value,
                data: document.getElementById("filtre-data").value,
                series: [..._selectedSeries],
                magatzems: [..._selectedMagatzems],
                clients: [..._selectedClients],
            };
            localStorage.setItem(FILTRES_KEY, JSON.stringify(filtres));
        } catch (e) { /* localStorage no disponible */ }
    }

    function _carregarFiltres() {
        try {
            const raw = localStorage.getItem(FILTRES_KEY);
            if (raw) return JSON.parse(raw);
        } catch (e) { /* ignorem */ }
        return null;
    }

    // ── Ordenació per capçalera ──
    const SORT_VALUE_GETTERS = {
        serie: (row) => row.dataset.pediKey || "",
        data: (row) => row.dataset.date || "",
        servir: (row) => (row.querySelectorAll("td")[2]?.textContent || "").trim(),
        client: (row) => row.dataset.client || "",
        dire: (row) => (row.querySelectorAll("td")[4]?.textContent || "").trim(),
        agent: (row) => (row.querySelectorAll("td")[5]?.textContent || "").trim(),
        tipus_desc: (row) => {
            const c = row.querySelector(".td-tipus-desc");
            return (c?.dataset?.tipusDesc || c?.textContent || "").trim();
        },
        linies: (row) => parseInt(row.querySelectorAll("td")[7]?.textContent, 10) || 0,
        unitats: (row) => parseInt(row.querySelectorAll("td")[8]?.textContent, 10) || 0,
        estat: (row) => (row.querySelector(".td-estat")?.dataset?.estat || "").trim(),
        palets: (row) => {
            const t = (row.querySelector(".td-palets")?.textContent || "").trim();
            const n = parseInt(t, 10);
            return Number.isFinite(n) ? n : null;
        },
        tipus_palet: (row) => (row.querySelector(".td-tipus-palet")?.textContent || "").trim(),
    };

    function _sortCompare(va, vb, type, dir) {
        // nulls/empty always last regardless of direction
        const aEmpty = va === null || va === undefined || va === "";
        const bEmpty = vb === null || vb === undefined || vb === "";
        if (aEmpty && bEmpty) return 0;
        if (aEmpty) return 1;
        if (bEmpty) return -1;
        if (type === "number") {
            return dir * ((Number(va) || 0) - (Number(vb) || 0));
        }
        if (type === "date") {
            // Les dates de l'API són DD/MM/YYYY → reutilitzar _parseDate
            const da = _parseDate(String(va));
            const db = _parseDate(String(vb));
            if (!da && !db) return 0;
            if (!da) return 1;
            if (!db) return -1;
            return dir * (da.getTime() - db.getTime());
        }
        if (type === "natural") {
            return dir * String(va).localeCompare(String(vb), "ca", { numeric: true, sensitivity: "base" });
        }
        return dir * String(va).localeCompare(String(vb), "ca", { sensitivity: "base" });
    }

    function ordenarFilesDom() {
        const tbody = document.getElementById("ultimes-body");
        if (!tbody) return;
        const rows = Array.from(tbody.querySelectorAll(".ultimes-row"));
        if (!rows.length) return;
        if (!_sortState.key || !_sortState.dir) {
            // Restaurar ordre natural (el del servidor)
            const orderMap = new Map(_allComandes.map((c, i) => [_comandaKey(c), i]));
            rows.sort((a, b) => {
                const ia = orderMap.has(a.dataset.pediKey) ? orderMap.get(a.dataset.pediKey) : Infinity;
                const ib = orderMap.has(b.dataset.pediKey) ? orderMap.get(b.dataset.pediKey) : Infinity;
                return ia - ib;
            });
        } else {
            const getter = SORT_VALUE_GETTERS[_sortState.key];
            if (!getter) return;
            const dir = _sortState.dir === "asc" ? 1 : -1;
            rows.sort((a, b) => _sortCompare(getter(a), getter(b), _sortState.type, dir));
        }
        const frag = document.createDocumentFragment();
        rows.forEach(r => frag.appendChild(r));
        tbody.appendChild(frag);
    }

    function actualitzarIndicadorsSort() {
        document.querySelectorAll("#ultimes-table th.sortable").forEach(th => {
            th.classList.remove("sorted-asc", "sorted-desc");
            th.setAttribute("aria-sort", "none");
            const ind = th.querySelector(".sort-indicator");
            if (ind) ind.textContent = "▼";
        });
        if (_sortState.key && _sortState.dir) {
            const th = document.querySelector(`#ultimes-table th.sortable[data-sort-key="${_sortState.key}"]`);
            if (th) {
                const isAsc = _sortState.dir === "asc";
                th.classList.add(isAsc ? "sorted-asc" : "sorted-desc");
                th.setAttribute("aria-sort", isAsc ? "ascending" : "descending");
                const ind = th.querySelector(".sort-indicator");
                if (ind) ind.textContent = isAsc ? "▲" : "▼";
            }
        }
    }

    function _guardarOrdenacio() {
        try { localStorage.setItem(ORDRE_KEY, JSON.stringify(_sortState)); }
        catch (e) { /* ignorem */ }
    }

    function ciclarOrdenacio(key, type) {
        if (_sortState.key !== key) return { key, type, dir: "asc" };
        if (_sortState.dir === "asc") return { key, type, dir: "desc" };
        return { key: null, type: null, dir: null };
    }

    // ==========================================
    // Dark mode
    // ==========================================
    const darkBtn = document.getElementById("btn-dark-mode");
    function applyTheme(theme) {
        document.documentElement.setAttribute("data-theme", theme);
        localStorage.setItem("theme", theme);
        darkBtn.textContent = theme === "dark" ? "\u2600" : "\u263E";
    }
    const savedTheme = localStorage.getItem("theme") ||
        (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    applyTheme(savedTheme);
    darkBtn.addEventListener("click", () => {
        applyTheme(document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark");
    });

    // ==========================================
    // Preview palets toggle
    // ==========================================
    let _previewPaletsActiu = localStorage.getItem("previewPalets") === "1";
    const previewBtn = document.getElementById("btn-preview-palets");
    function _applyPreviewState() {
        previewBtn.classList.toggle("btn-preview-active", _previewPaletsActiu);
        previewBtn.title = _previewPaletsActiu
            ? "Preview palets activat (clic per desactivar)"
            : "Preview palets desactivat (clic per activar)";
    }
    _applyPreviewState();
    previewBtn.addEventListener("click", () => {
        _previewPaletsActiu = !_previewPaletsActiu;
        localStorage.setItem("previewPalets", _previewPaletsActiu ? "1" : "0");
        _applyPreviewState();
        if (!_previewPaletsActiu) _amagarPreviewPalets();
    });

    // ==========================================
    // Recent orders (localStorage)
    // ==========================================
    function getRecentOrders() {
        try { return JSON.parse(localStorage.getItem("recentOrders") || "[]"); } catch { return []; }
    }
    function addRecentOrder(serieNum, clientNom, palets) {
        let recent = getRecentOrders().filter(r => r.id !== serieNum);
        recent.unshift({ id: serieNum, client: clientNom || "", palets: palets || 0, ts: Date.now() });
        if (recent.length > 15) recent = recent.slice(0, 15);
        localStorage.setItem("recentOrders", JSON.stringify(recent));
        renderRecentOrders();
    }
    function renderRecentOrders() {
        const container = document.getElementById("recent-orders");
        const recent = getRecentOrders();
        if (recent.length === 0) { container.innerHTML = ""; return; }
        container.innerHTML = recent.slice(0, 10).map(r =>
            `<span class="recent-chip" data-id="${escapeHtml(r.id)}" title="${escapeHtml(r.client)}">` +
            `${escapeHtml(r.id)} <span class="recent-info">${r.palets ? r.palets + 'p' : ''}</span></span>`
        ).join("");
        container.querySelectorAll(".recent-chip").forEach(chip => {
            chip.addEventListener("click", () => {
                input.value = chip.dataset.id;
                form.dispatchEvent(new Event("submit"));
            });
        });
    }
    renderRecentOrders();

    // Resol un número KAIS (visualització) al salKey (sal_codigo/cpa_albara real)
    // buscant a les comandes carregades.
    function _resoldreSalKey(pediNum) {
        if (!_allComandes) return null;
        const match = _allComandes.find(c => {
            const key = c.pedi_serie ? `${c.pedi_serie}/${c.pedi_numero}` : c.pedi_numero;
            return key === pediNum;
        });
        if (!match) return null;
        return match.sal_codigo
            ? `${match.sal_codigo}/${match.pedi_numero}`
            : `${match.pedi_serie}/${match.pedi_numero}`;
    }

    form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const pediNum = input.value.trim();
        if (!pediNum) return;
        // Resoldre KAIS a salKey si coincideix amb una comanda del llistat
        const apiNum = _resoldreSalKey(pediNum) || pediNum;
        lastPediNum = apiNum;
        await executarCalcul(apiNum, false);
    });

    btnForcar.addEventListener("click", async () => {
        if (!lastPediNum) return;
        await executarCalcul(lastPediNum, true);
    });

    btnHome.addEventListener("click", () => {
        if (currentController) currentController.abort();
        showState("empty");
        btnHome.classList.add("hidden");
        input.value = "";
        input.focus();
    });

    async function executarCalcul(pediInput, forcar) {
        // Cancel·lar petició anterior si n'hi ha una en curs
        if (currentController) currentController.abort();
        currentController = new AbortController();
        const signal = currentController.signal;

        showState("loading");
        btn.disabled = true;
        btn.textContent = "Calculant...";
        btnHome.classList.remove("hidden");

        // Mostrar temps transcorregut
        const t0 = Date.now();
        const loadingText = document.querySelector("#loading-state p");
        const timerInterval = setInterval(() => {
            const elapsed = ((Date.now() - t0) / 1000).toFixed(1);
            loadingText.textContent = `Calculant embalatges… (${elapsed}s)`;
        }, 500);

        try {
            // Calcular directament amb serie/numero
            if (!pediInput.includes("/")) {
                showError("Format invàlid. Usa Sèrie/Número (ex: 51/0002456)", false);
                return;
            }

            const url = forcar
                ? `/api/calcular/${encodeURIComponent(pediInput)}?forcar=1`
                : `/api/calcular/${encodeURIComponent(pediInput)}`;
            const resp = await fetch(url, { signal });
            if (!resp.ok) { showError(`Error del servidor (${resp.status})`, false); return; }
            const data = await resp.json();
            if (signal.aborted) return;

            if (!data.ok) {
                showError(data.error, false);
                return;
            }

            if (data.estat === "NO_CALCULABLE" && !forcar) {
                showError(data.missatges.join("\n"), true);
                return;
            }

            lastResultData = data;
            renderResult(data);
            showState("result");

            // Guardar a recents
            const clientNom = data.direccio ? (data.direccio.adr_nom || "") : "";
            const numPalets = data.resum ? data.resum.total_palets : 0;
            addRecentOrder(input.value, clientNom, numPalets);
            addToHistory(input.value);

            // Detectar comandes agrupables (mateix client+direcció+data)
            // TODO: agrupació de comandes desactivada temporalment
            // if (data.comanda && !data.agrupat) {
            //     detectarAgrupables(data.comanda)
            // }
        } catch (err) {
            if (err.name === "AbortError") return;  // Petició cancel·lada, ignorar
            showError("Error de connexió amb el servidor.", false);
        } finally {
            clearInterval(timerInterval);
            loadingText.textContent = "Calculant embalatges…";
            btn.disabled = false;
            btn.textContent = "Calcular";
            currentController = null;
        }
    }

    // Historial de navegació
    const _searchHistory = [];
    let _historyIdx = -1;
    function addToHistory(val) {
        if (!val) return;
        // Evitar duplicats consecutius
        if (_searchHistory.length > 0 && _searchHistory[_searchHistory.length - 1] === val) return;
        _searchHistory.push(val);
        if (_searchHistory.length > 50) _searchHistory.shift();
        _historyIdx = _searchHistory.length;
    }

    input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") form.dispatchEvent(new Event("submit"));
        if (e.key === "Escape") {
            if (currentController) currentController.abort();
            showState("empty");
            btnHome.classList.add("hidden");
            input.value = "";
            input.focus();
        }
        // Fletxes amunt/avall: navegar historial
        if (e.key === "ArrowUp" && _searchHistory.length > 0) {
            e.preventDefault();
            if (_historyIdx <= 0) _historyIdx = 0;
            else _historyIdx--;
            input.value = _searchHistory[_historyIdx] || "";
        }
        if (e.key === "ArrowDown" && _searchHistory.length > 0) {
            e.preventDefault();
            _historyIdx++;
            if (_historyIdx >= _searchHistory.length) {
                _historyIdx = _searchHistory.length;
                input.value = "";
            } else {
                input.value = _searchHistory[_historyIdx];
            }
        }
    });

    function showState(state) {
        emptyState.classList.add("hidden");
        loadingState.classList.add("hidden");
        errorState.classList.add("hidden");
        resultState.classList.add("hidden");
        document.getElementById("batch-state").classList.add("hidden");

        if (state === "empty") emptyState.classList.remove("hidden");
        if (state === "loading") loadingState.classList.remove("hidden");
        if (state === "error") errorState.classList.remove("hidden");
        if (state === "result") resultState.classList.remove("hidden");

        if (state === "empty") btnHome.classList.add("hidden");
    }

    function showError(msg, canForce) {
        document.getElementById("error-message").textContent = msg;
        const helpEl = document.getElementById("error-help");
        if (msg.includes("STOP") && msg.includes("mínim")) {
            helpEl.textContent = "La comanda no arriba al mínim de sacs requerit. Reviseu les quantitats o consulteu el responsable.";
        } else if (msg.includes("granel") || msg.includes("GRA")) {
            helpEl.textContent = "Les comandes amb granel requereixen tractament manual. No es pot calcular automàticament.";
        } else if (msg.includes("producció") || msg.includes("mínim")) {
            helpEl.textContent = "La quantitat no arriba al mínim de producció per aquest article. Cal ajustar la comanda.";
        } else if (msg.includes("especial")) {
            helpEl.textContent = "Conté articles especials que no compleixen les condicions automàtiques. Cal revisió manual.";
        } else {
            helpEl.textContent = "";
        }
        btnForcar.classList.toggle("hidden", !canForce);
        showState("error");
    }

    const rfTooltips = {
        RF1: "Filtre articles computables. Si la comanda inclou article a granel (GRA) no es pot activar el proc\u00e9s de preparaci\u00f3. Nom\u00e9s es tenen en compte per al c\u00e0lcul d\u2019embalatges els articles amb TUnitat S05, S10, S15, S20 o S25; qualsevol article que no tingui un d\u2019aquests formats queda excl\u00f2s del c\u00e0lcul.",
        RF2: "Validaci\u00f3 comanda m\u00ednima. El m\u00ednim aplicable deriva del Tipus de desc\u00e0rrega de la direcci\u00f3 d\u2019enviament: si \u00e9s A PALET, el m\u00ednim \u00e9s 40 sacs; si \u00e9s DESPALETITZADA, el m\u00ednim \u00e9s 20 sacs. Poden existir excepcions definides a la direcci\u00f3 d\u2019enviament. Si la comanda no arriba al m\u00ednim, cal ajustar les unitats.",
        RF3: "Validaci\u00f3 de comanda m\u00ednima producci\u00f3. Per a cada l\u00ednia computable marcada amb Comanda m\u00ednima producci\u00f3 = num\u00e8ric, el motor valida que la quantitat de la comanda compleix la producci\u00f3 m\u00ednima requerida detallada a l\u2019article. Si no es compleix, retorna un av\u00eds de revisi\u00f3/ajust.",
        RF4: "Validaci\u00f3 d\u2019articles especials. Si la comanda inclou l\u00ednies amb Article_especial = S\u00ed, el motor nom\u00e9s pot fer c\u00e0lcul autom\u00e0tic si el nombre total de sacs especials \u00e9s inferior o igual a Cantidad_apilable, o si la quantitat de cada article especial \u00e9s exactament igual a les seves Unitats x caixa, cas en qu\u00e8 forma embalatge propi.",
        RF5: "Prioritat de la direcci\u00f3 d\u2019enviament. Si a la direcci\u00f3 d\u2019enviament el camp PrevalDireccio = S\u00ed, la configuraci\u00f3 de tipus de palet, Sacs x base i M\u00e0xim per embalatge de la direcci\u00f3 mana per sobre de la fitxa d\u2019article.",
        RF6: "En comandes amb articles Sac_25_especial: fins a 8 sacs, el tipus de palet, sacs x base i unitats x caixa segons estipula la direcci\u00f3 d\u2019enviament. A partir de 9 sacs s\u2019aplicar\u00e0 per defecte palet europeu fusta (01030), sacs x base = 3 i unitats x caixa = 30.",
        RF7: "En articles d\u2019aprovisionament d\u2019estoc: fins a 20 sacs del mateix article, el tipus de palet, sacs x base i unitats x caixa segons estipula la direcci\u00f3 d\u2019enviament. A partir de 21 sacs del mateix article, s\u2019ha de respectar el tipus de palet, sacs x base i unitats x caixa definits a la fitxa d\u2019article.",
        RF8: "En comandes amb varis articles d\u2019aprovisionament d\u2019estoc: fins a 26 sacs de varis articles, el tipus de palet, sacs x base i unitats x caixa segons estipula la direcci\u00f3 d\u2019enviament. A partir de 27 sacs de varis articles s\u2019aplicar\u00e0 palet europeu fusta (01030), sacs x base = 3 i unitats x caixa = 30.",
        RF9: "Valors per defecte de la direcci\u00f3 d\u2019enviament: si la direcci\u00f3 d\u2019enviament no especifica res, s\u2019aplicar\u00e0 per defecte palet europeu fusta (01030), Sacs x base = 5 i M\u00e0xim sacs per palet = 45.",
        RF10: "Articles no adjudicats a embalatges anteriors. Aplica els mateixos criteris que RF9: tipus de palet seg\u00f3ns condicions de direcci\u00f3, sin\u00f3 Base palet (01010). M\u00e0xim sacs per palet segons direcci\u00f3, sin\u00f3 45.",
    };

    // Breadcrumb: tornar a inici
    document.getElementById("bc-home").addEventListener("click", (e) => {
        e.preventDefault();
        if (currentController) currentController.abort();
        showState("empty");
        btnHome.classList.add("hidden");
        input.value = "";
        input.focus();
    });

    // Copiar resum (desactivat temporalment)
    const btnCopiar = document.getElementById("btn-copiar");
    if (btnCopiar) {
        btnCopiar.addEventListener("click", () => {
            if (!lastResultData) return;
            const d = lastResultData;
            const serie = d.comanda ? (d.comanda.pedi_serie ? `${d.comanda.pedi_serie}/${d.comanda.pedi_numero}` : d.comanda.pedi_numero) : "-";
            const client = d.direccio ? (d.direccio.adr_nom || "") : "";
            const sacs = d.resum ? d.resum.total_sacs : 0;
            const palets = d.resum ? d.resum.total_palets : 0;
            const tipusPalet = d.palets ? d.palets.map(p => `${p.quantitat}x ${p.art_descrip.replace(/PALET\s*/i, '').trim()}`).join(", ") : "";
            const text = `Comanda ${serie} - ${client}: ${sacs} sacs, ${palets} palet(s)${tipusPalet ? ' (' + tipusPalet + ')' : ''}`;
            navigator.clipboard.writeText(text).then(() => {
                btnCopiar.classList.add("copied");
                btnCopiar.textContent = "\u2705 Copiat!";
                setTimeout(() => { btnCopiar.classList.remove("copied"); btnCopiar.innerHTML = "&#128203; Copiar resum"; }, 2000);
            });
        });
    }

    function renderResult(data) {
        // Breadcrumb
        const bcComanda = document.getElementById("bc-comanda");
        if (data.comanda) {
            bcComanda.textContent = `${data.comanda.pedi_serie}/${data.comanda.pedi_numero}`;
        } else {
            bcComanda.textContent = "-";
        }

        // Estat
        const estatEl = document.getElementById("res-estat");
        estatEl.className = `estat-badge estat-${data.estat}`;
        const icons = {
            CALCULAT: "\u2705",
            CALCULAT_AMB_AVISOS: "\u26a0\ufe0f",
            SOTA_MINIM: "\u26a0\ufe0f",
            NO_CALCULABLE: "\u274c",
        };
        const labels = {
            CALCULAT: "Calculat",
            CALCULAT_AMB_AVISOS: "Calculat amb avisos",
            SOTA_MINIM: "Sota m\u00ednim",
            NO_CALCULABLE: "Revisi\u00f3 manual",
        };
        let estatLabel = labels[data.estat] || data.estat;
        if (data.forcat) estatLabel += " (FORÇAT)";
        estatEl.innerHTML = `${icons[data.estat] || ""} ${estatLabel}`;

        // Nom del client prominent
        const clientNomEl = document.getElementById("res-client-nom");
        if (data.comanda && data.comanda.cli_nom) {
            clientNomEl.textContent = data.comanda.cli_nom;
            clientNomEl.style.display = "";
        } else if (data.direccio && data.direccio.adr_nom) {
            clientNomEl.textContent = data.direccio.adr_nom;
            clientNomEl.style.display = "";
        } else {
            clientNomEl.style.display = "none";
        }

        // Metadades compactes
        if (data.comanda) {
            const c = data.comanda;
            const numDisplay = `${c.pedi_serie}/${c.pedi_numero}`;
            document.getElementById("res-pedi-num").textContent = numDisplay;
            document.getElementById("res-cli-codi").textContent = c.cli_codi || "-";
            document.getElementById("res-pedi-dire").textContent = c.pedi_dire || "-";
            document.getElementById("res-pedi-fech").textContent = c.data_comanda || c.pedi_fech || "-";
            const dataServirEl = document.getElementById("res-data-servir");
            if (c.data_servir) {
                dataServirEl.textContent = "Servir: " + c.data_servir;
                dataServirEl.previousElementSibling.style.display = "";
            } else {
                dataServirEl.textContent = "";
                dataServirEl.previousElementSibling.style.display = "none";
            }
        }
        if (data.direccio) {
            const d = data.direccio;
            document.getElementById("res-adr-nom").textContent = d.adr_nom || "-";
            document.getElementById("res-tipus-desc").textContent = d.tipus_descarrega || "No definit";
            document.getElementById("res-tipus-desc-detail").textContent = d.tipus_descarrega || "No definit";
            document.getElementById("res-max-sacs").textContent = d.max_sacs_palet || "No definit";
            document.getElementById("res-min-exc").textContent = d.sacs_comanda_minima || "Sense excepció";
            document.getElementById("res-preval").textContent = d.preval_direccio ? "Sí" : "No";
        }
        // Avisos unificats (plegable)
        const avisosDiv = document.getElementById("avisos-unificats");
        const avisosToggle = document.getElementById("avisos-toggle");
        const avisosToggleText = document.getElementById("avisos-toggle-text");
        const avisosBodyEl = document.getElementById("avisos-body");
        const bloquejants = [];
        const avisos = [];
        const informatius = [];

        if (data.missatges && data.missatges.length > 0) {
            data.missatges.forEach(m => {
                if (m.includes("STOP")) {
                    bloquejants.push(m.replace(/STOP:?\s*/i, "").trim());
                } else {
                    avisos.push(m);
                }
            });
        }
        if (data.avisos_dades && data.avisos_dades.length > 0) {
            data.avisos_dades.forEach(a => {
                informatius.push(`${a.camp}: ${a.missatge}`);
            });
        }

        const totalAvisos = bloquejants.length + avisos.length;
        if (totalAvisos > 0) {
            avisosDiv.classList.remove("hidden");
            // Capçalera amb resum
            avisosToggle.className = "avisos-header" + (bloquejants.length > 0 ? " has-bloquejant" : " has-avisos");
            const iconText = bloquejants.length > 0 ? "\u26D4" : "\u26a0\ufe0f";
            const parts = [];
            if (bloquejants.length > 0) parts.push(`${bloquejants.length} bloquejant${bloquejants.length > 1 ? 's' : ''}`);
            if (avisos.length > 0) parts.push(`${avisos.length} av\u00eds${avisos.length > 1 ? 'os' : ''}`);
            avisosToggleText.textContent = `${iconText} ${parts.join(', ')} \u2014 clic per veure`;

            // Contingut
            let html = '';
            bloquejants.forEach(m => {
                html += `<div class="avis-unificat avis-bloquejant">
                    <span class="avis-icon">\u26D4</span>
                    <div class="avis-text"><span class="avis-label">Bloquejant</span> ${escapeHtml(m)}</div>
                </div>`;
            });
            avisos.forEach(m => {
                html += `<div class="avis-unificat avis-av\u00eds">
                    <span class="avis-icon">\u26a0\ufe0f</span>
                    <div class="avis-text"><span class="avis-label">Av\u00eds</span> ${escapeHtml(m)}</div>
                </div>`;
            });
            avisosBodyEl.innerHTML = html;
            // Tancar per defecte
            avisosBodyEl.classList.add("hidden");
            avisosToggle.classList.remove("open");
        } else {
            avisosDiv.classList.add("hidden");
        }

        // Avisos dades mestres (plegable, tancat per defecte)
        const avisosCard = document.getElementById("card-avisos-dades");
        const avisosBody = document.getElementById("res-avisos-dades");
        const avisosDadesCount = document.getElementById("avisos-dades-count");
        const avisosDadesArrow = document.getElementById("avisos-dades-arrow");
        if (informatius.length > 0) {
            avisosCard.classList.remove("hidden");
            avisosBody.classList.add("hidden");
            avisosDadesArrow.textContent = "\u25B6";
            avisosDadesCount.textContent = `(${informatius.length})`;
            avisosBody.innerHTML = informatius.map(m =>
                `<div class="avis-unificat avis-info" style="margin-bottom:0.3rem;">
                    <span class="avis-icon">\u2139\ufe0f</span>
                    <div class="avis-text"><span class="avis-label">Info</span>${escapeHtml(m)}</div>
                </div>`
            ).join("");
        } else {
            avisosCard.classList.add("hidden");
        }

        // Mantenir card-missatges per compatibilitat
        const msgsCard = document.getElementById("card-missatges");
        msgsCard.classList.add("hidden");

        // Linies comanda
        const liniesBody = document.getElementById("res-linies");
        const liniesHeader = document.getElementById("linies-header");
        const liniesBodyDiv = document.getElementById("linies-body");
        if (data.linies && data.linies.length > 0) {
            const totalUnitats = data.linies.reduce((s, l) => s + l.linea_unidades, 0);
            liniesBody.innerHTML = data.linies
                .map(
                    (l) => `<tr>
                    <td class="num">${l.linea_num}</td>
                    <td class="art-code">${escapeHtml(l.art_codi)}</td>
                    <td>${escapeHtml(l.art_descrip)}</td>
                    <td>${escapeHtml(l.tunitat)}</td>
                    <td class="num">${l.linea_unidades}</td>
                </tr>`
                )
                .join("")
                + `<tr>
                    <td colspan="4"><strong>TOTAL (${data.linies.length} línies)</strong></td>
                    <td class="num"><strong>${totalUnitats}</strong></td>
                </tr>`;
            liniesHeader.classList.remove("open");
            liniesBodyDiv.classList.remove("open");
        }

        // Resum prominent
        const resumProminent = document.getElementById("res-resum-prominent");
        if (data.embalatges && data.embalatges.length > 0 && data.resum) {
            resumProminent.classList.remove("hidden");
            // Color segons estat
            resumProminent.className = "resum-prominent";
            if (data.estat === "CALCULAT") resumProminent.classList.add("resum-estat-ok");
            else if (data.estat === "CALCULAT_AMB_AVISOS") resumProminent.classList.add("resum-estat-avisos");
            else if (data.estat === "SOTA_MINIM") resumProminent.classList.add("resum-estat-avisos");
            document.getElementById("resum2-sacs").textContent = data.resum.total_sacs;
            document.getElementById("resum2-palets").textContent = data.resum.total_palets;
            document.getElementById("resum2-linies").textContent = `${data.linies ? data.linies.length : 0} articles`;

            // Pes estimat
            const pesTotalKg = data.embalatges.reduce((s, e) =>
                s + e.contingut.reduce((s2, c) => s2 + (c.pes_kg || 0), 0), 0);
            if (pesTotalKg > 0) {
                document.getElementById("resum2-pes").textContent = pesTotalKg >= 1000
                    ? (pesTotalKg / 1000).toFixed(1) + " t"
                    : Math.round(pesTotalKg) + " kg";
                const pesPerPalet = Math.round(pesTotalKg / data.embalatges.length);
                document.getElementById("resum2-pes-detail").textContent = `~${pesPerPalet} kg/palet`;
            } else {
                document.getElementById("resum2-pes").textContent = "-";
                document.getElementById("resum2-pes-detail").textContent = "Sense dades de pes";
            }

            // Botó "Sol·licitar autorització" si pes < 500 kg
            actualitzarBtnAutoritzacio(pesTotalKg);

            // Tipus palets resum
            if (data.palets && data.palets.length > 0) {
                document.getElementById("resum2-tipus").textContent = data.palets
                    .map(p => `${p.quantitat}x ${p.art_descrip.replace(/PALET\s*/i, '').trim()}`)
                    .join(", ");
            }
        } else {
            resumProminent.classList.add("hidden");
            actualitzarBtnAutoritzacio(0);
        }

        // Composicio de palets
        const embCard = document.getElementById("card-embalatges");
        const embBody = document.getElementById("res-embalatges");
        if (data.embalatges && data.embalatges.length > 0) {
            embCard.classList.remove("hidden");

            // Mapeig d'articles a colors (compartit amb vista gràfica)
            const artColorsEmb = {};
            let colorIdxEmb = 0;
            data.embalatges.forEach(e => {
                e.contingut.forEach(c => {
                    if (!(c.art_codi in artColorsEmb)) {
                        artColorsEmb[c.art_codi] = colorIdxEmb % 8;
                        colorIdxEmb++;
                    }
                });
            });

            let rows = data.embalatges
                .map((e) => {
                    const contingutStr = e.contingut
                        .map((c) => {
                            return `<span class="palet-art">`
                                + `<span class="art-code">${escapeHtml(c.art_codi)}</span> `
                                + `${escapeHtml(c.art_descrip)} `
                                + `<strong>(${c.sacs})</strong>`
                                + `</span>`;
                        })
                        .join('<span class="palet-sep"> + </span>');
                    const mixBadge = e.contingut.length > 1
                        ? ' <span class="mixt-badge">MIXT</span>'
                        : '';
                    const propiBadge = e.es_embalatge_propi
                        ? ' <span class="propi-badge">PROPI</span>'
                        : '';

                    // Calcular pisos del palet
                    const pisos = calcularPisos(e.contingut, e.sacs_x_base);
                    const pisosHtml = pisos.map((pis, idx) => {
                        const pisStr = pis.map(p =>
                            `<span class="art-code">${escapeHtml(p.art_codi)}</span> ${escapeHtml(p.art_descrip)} <strong>(${p.sacs})</strong>`
                        ).join(' + ');
                        return `<div class="pis-item"><span class="pis-num">Pis ${idx + 1}</span>${pisStr}</div>`;
                    }).reverse().join("");

                    const inlineVisualHtml = renderPaletVisual(e, pisos, artColorsEmb, 'palet-visual-inline');

                    const tipusPaletStr = e.tipus_palet_descrip
                        ? `<span class="art-code">${escapeHtml(e.tipus_palet)}</span> ${escapeHtml(e.tipus_palet_descrip)}`
                        : '-';

                    const pesEmb = e.contingut.reduce((s, c) => s + (c.pes_kg || 0), 0);
                    const pesStr = pesEmb > 0 ? `${Math.round(pesEmb)} kg` : '-';

                    return `<tr class="palet-row" data-palet="${e.palet_num}">
                        <td class="num palet-num-cell"><span class="palet-expand-arrow">&#9654;</span> ${e.palet_num}</td>
                        <td>${contingutStr}${mixBadge}${propiBadge}</td>
                        <td class="num"><strong>${e.total_sacs}</strong></td>
                        <td class="num">${pesStr}</td>
                        <td class="num">${e.sacs_x_base}</td>
                        <td class="num">${e.max_sacs}</td>
                        <td>${tipusPaletStr}</td>
                    </tr>
                    <tr class="palet-pisos-row hidden" data-palet-detail="${e.palet_num}">
                        <td></td>
                        <td colspan="6">
                            <div class="pisos-detail-split">
                                <div class="pisos-detail">${pisosHtml}</div>
                                <div class="pisos-visual">${inlineVisualHtml}</div>
                            </div>
                        </td>
                    </tr>`;
                })
                .join("");

            // Fila total
            const pesTotalEmb = data.embalatges.reduce((s, e) =>
                s + e.contingut.reduce((s2, c) => s2 + (c.pes_kg || 0), 0), 0);
            const pesTotalStr = pesTotalEmb > 0 ? `${Math.round(pesTotalEmb)} kg` : '-';
            rows += `<tr>
                <td><strong>TOTAL</strong></td>
                <td><strong>${data.embalatges.length} palet(s)</strong></td>
                <td class="num"><strong>${data.resum ? data.resum.total_sacs : '-'}</strong></td>
                <td class="num"><strong>${pesTotalStr}</strong></td>
                <td colspan="3"></td>
            </tr>`;

            embBody.innerHTML = rows;

            // Click per expandir/col·lapsar pisos (event delegation)
            embBody.querySelectorAll(".palet-row").forEach(r => { r.style.cursor = "pointer"; });
            if (!embBody._paletDelegated) {
                embBody._paletDelegated = true;
                embBody.addEventListener("click", (ev) => {
                    const row = ev.target.closest(".palet-row");
                    if (!row) return;
                    const num = row.dataset.palet;
                    const detail = embBody.querySelector(`[data-palet-detail="${num}"]`);
                    if (detail) {
                        detail.classList.toggle("hidden");
                        row.classList.toggle("palet-row-open");
                    }
                });
            }

        } else {
            embCard.classList.add("hidden");
        }

        // Tipus palet
        const palCard = document.getElementById("card-tipus-palet");
        const palBody = document.getElementById("res-tipus-palet");
        if (data.palets && data.palets.length > 0) {
            palCard.classList.remove("hidden");
            palBody.innerHTML = data.palets
                .map(
                    (p) => `<tr>
                    <td class="art-code">${escapeHtml(p.art_codi)}</td>
                    <td>${escapeHtml(p.art_descrip)}</td>
                    <td>${p.es_fisic ? "Pàlet físic" : "Base pàlet (lògic)"}</td>
                    <td class="num"><strong>${p.quantitat}</strong></td>
                </tr>`
                )
                .join("");
        } else {
            palCard.classList.add("hidden");
        }

        // Vista grafica palets
        const visualCard = document.getElementById("card-visual-palets");
        const visualGrid = document.getElementById("res-visual-palets");
        if (data.embalatges && data.embalatges.length > 0) {
            visualCard.classList.remove("hidden");

            // Mapeig d'articles a colors
            const artColors = {};
            let colorIdx = 0;
            data.embalatges.forEach(e => {
                e.contingut.forEach(c => {
                    if (!(c.art_codi in artColors)) {
                        artColors[c.art_codi] = colorIdx % 8;
                        colorIdx++;
                    }
                });
            });

            visualGrid.innerHTML = data.embalatges.map(e => {
                const pisos = calcularPisos(e.contingut, e.sacs_x_base);
                return renderPaletVisual(e, pisos, artColors, '');
            }).join('');

            // Llegenda de colors
            const llegenda = Object.entries(artColors).map(([art, ci]) => {
                const descrip = data.embalatges.flatMap(e => e.contingut).find(c => c.art_codi === art);
                const nom = descrip ? descrip.art_descrip : art;
                return `<span style="display:inline-flex;align-items:center;gap:0.3rem;margin-right:1rem;font-size:0.78rem;">
                    <span style="display:inline-block;width:12px;height:12px;border-radius:2px" class="palet-color-${ci}"></span>
                    <span class="art-code" style="font-size:0.75rem">${escapeHtml(art)}</span> ${escapeHtml(nom)}
                </span>`;
            }).join('');
            visualGrid.insertAdjacentHTML("beforeend", `<div style="width:100%;margin-top:0.75rem;padding-top:0.75rem;border-top:1px solid var(--gray-200)">${llegenda}</div>`);
        } else {
            visualCard.classList.add("hidden");
        }

        // Trazabilitat
        const traceList = document.getElementById("res-trazabilitat");
        if (data.trazabilitat && data.trazabilitat.length > 0) {
            traceList.innerHTML = data.trazabilitat
                .map((t, i) => {
                    let text = escapeHtml(t);
                    text = text.replace(/(RF\d)/g, (match) => {
                        const tip = rfTooltips[match] || "";
                        return `<span class="rf-tag" title="${tip}">${match}</span>`;
                    });
                    // Aplicar tags STOP/FORÇAT/MIXT només al text fora de tags HTML
                    text = text.replace(/(^|>)([^<]*?)($|<)/g, (full, pre, inner, post) => {
                        let r = inner;
                        r = r.replace(/STOP/g, '<span class="stop-tag">STOP</span>');
                        r = r.replace(/FORÇAT|FORCAT/g, (m) => `<span class="forcat-tag">${m}</span>`);
                        r = r.replace(/\[MIXT\]/g, '<span class="mixt-tag">[MIXT]</span>');
                        return `${pre}${r}${post}`;
                    });
                    return `<li><span class="trace-num">${i + 1}</span><span class="trace-text">${text}</span></li>`;
                })
                .join("");
        }

        // Restaurar estat de seccions col·lapsables
        const defaultOpen = ["visual-palets"];
        ["trace", "embalatges", "visual-palets", "linies"].forEach(s => {
            const hId = s + "-header";
            const bId = s + "-body";
            const h = document.getElementById(hId);
            const b = document.getElementById(bId);
            if (h && b) {
                h.classList.remove("open");
                b.classList.remove("open");
                const saved = sessionStorage.getItem("collapse_" + hId);
                if (saved === "1" || (saved === null && defaultOpen.includes(s))) {
                    h.classList.add("open");
                    b.classList.add("open");
                } else if (saved === "0") {
                    // Respectar que l'usuari l'ha tancat
                }
            }
        });
    }

    // Collapsible sections amb persistència i accessibilitat
    function toggleSection(headerId, bodyId) {
        const header = document.getElementById(headerId);
        const body = document.getElementById(bodyId);
        header.classList.toggle("open");
        body.classList.toggle("open");
        const isOpen = body.classList.contains("open");
        header.setAttribute("aria-expanded", isOpen);
        sessionStorage.setItem("collapse_" + headerId, isOpen ? "1" : "0");
    }

    function restoreSection(headerId, bodyId) {
        const saved = sessionStorage.getItem("collapse_" + headerId);
        if (saved === "1") {
            document.getElementById(headerId).classList.add("open");
            document.getElementById(bodyId).classList.add("open");
            document.getElementById(headerId).setAttribute("aria-expanded", "true");
        }
    }

    // Click + keyboard (Enter/Space) per collapsible headers
    ["trace-header", "linies-header", "visual-palets-header"].forEach(hid => {
        const bodyId = hid.replace("-header", "-body");
        const el = document.getElementById(hid);
        if (!el) return;
        el.addEventListener("click", () => toggleSection(hid, bodyId));
        el.addEventListener("keydown", (e) => {
            if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggleSection(hid, bodyId); }
        });
    });

    // Toggle avisos plegable
    document.getElementById("avisos-toggle").addEventListener("click", () => {
        const body = document.getElementById("avisos-body");
        const header = document.getElementById("avisos-toggle");
        body.classList.toggle("hidden");
        header.classList.toggle("open");
    });

    // Toggle qualitat dades mestres
    document.getElementById("avisos-dades-toggle").addEventListener("click", () => {
        const body = document.getElementById("res-avisos-dades");
        const arrow = document.getElementById("avisos-dades-arrow");
        const isHidden = body.classList.toggle("hidden");
        arrow.textContent = isHidden ? "\u25B6" : "\u25BC";
    });

    function _toggleEmbalatges() {
        toggleSection("embalatges-header", "embalatges-body");
        const isOpen = document.getElementById("embalatges-body").classList.contains("open");
        const embBody = document.getElementById("res-embalatges");
        embBody.querySelectorAll(".palet-row").forEach(row => {
            const num = row.dataset.palet;
            const detail = embBody.querySelector(`[data-palet-detail="${num}"]`);
            if (detail) {
                if (isOpen) {
                    detail.classList.remove("hidden");
                    row.classList.add("palet-row-open");
                } else {
                    detail.classList.add("hidden");
                    row.classList.remove("palet-row-open");
                }
            }
        });
    }
    document.getElementById("embalatges-header").addEventListener("click", _toggleEmbalatges);
    document.getElementById("embalatges-header").addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); _toggleEmbalatges(); }
    });

    function renderPaletVisual(e, pisos, artColors, extraClass) {
        const maxSacs = e.max_sacs || 45;

        // Alçada proporcional: garantir espai per totes les capes (min 20px/capa)
        const minByLayers = pisos.length * 20;
        const proportional = Math.round((e.total_sacs / maxSacs) * 160);
        const stackHeight = Math.max(minByLayers, proportional, 60);

        const layersHtml = pisos.map(pis => {
            const sacsInPis = pis.reduce((s, x) => s + x.sacs, 0);
            const parts = pis.map(p => {
                const ci = artColors[p.art_codi] || 0;
                const w = pis.length > 1 ? `width:${Math.round(p.sacs / sacsInPis * 100)}%` : 'width:100%';
                return `<span class="palet-visual-layer palet-color-${ci}" style="${w}" title="${p.art_codi} - ${p.art_descrip} (${p.sacs} sacs)">${escapeHtml(p.art_codi)} (${p.sacs})</span>`;
            }).join('');
            return `<div class="palet-visual-pis">${parts}</div>`;
        }).join('');

        const tipusStr = e.tipus_palet_descrip
            ? escapeHtml(e.tipus_palet_descrip).replace(/PALET\s*/i, '').replace(/\s*\d+X\d+/i, '').trim()
            : '';
        const pesContingut = e.contingut.reduce((s, c) => s + (c.pes_kg || 0), 0);
        const pesStr = pesContingut > 0 ? `${Math.round(pesContingut)} kg` : '';
        const badges = [];
        if (e.contingut.length > 1) badges.push('<span class="mixt-badge">MIXT</span>');
        if (e.es_embalatge_propi) badges.push('<span class="propi-badge">PROPI</span>');
        const badgesHtml = badges.length > 0
            ? `<div class="palet-visual-badges">${badges.join('')}</div>` : '';

        const tp = (e.tipus_palet_descrip || '').toLowerCase();
        let baseClass = 'palet-base-fusta';
        if (/pl[àa]stic/i.test(tp)) baseClass = 'palet-base-plastic';
        else if (/base/i.test(tp) && !/fusta/i.test(tp)) baseClass = 'palet-base-logic';
        else if (/americ/i.test(tp)) baseClass = 'palet-base-america';

        return `<div class="palet-visual${extraClass ? ' ' + extraClass : ''}">
            <div class="palet-visual-title">Palet ${e.palet_num}</div>
            ${badgesHtml}
            <div class="palet-visual-sacs">${e.total_sacs} sacs${pesStr ? ' · ' + pesStr : ''}</div>
            <div class="palet-visual-stack" style="height:${stackHeight}px">${layersHtml}</div>
            <div class="palet-visual-base-bar ${baseClass}"></div>
            ${tipusStr ? `<div class="palet-visual-tipus">${tipusStr}</div>` : ''}
        </div>`;
    }

    function calcularPisos(contingut, defaultBase) {
        const pisos = [];
        let currentPis = [];
        let currentCount = 0;
        let currentBase = defaultBase;
        for (const item of contingut) {
            const itemBase = (item.sacs_x_base && item.sacs_x_base > 0)
                ? item.sacs_x_base : defaultBase;
            // Si canvia la base, tancar el pis actual (no es barregen bases)
            if (itemBase !== currentBase && currentPis.length > 0) {
                pisos.push(currentPis);
                currentPis = [];
                currentCount = 0;
            }
            currentBase = itemBase;
            let remaining = item.sacs;
            while (remaining > 0) {
                const espai = currentBase - currentCount;
                const posar = Math.min(remaining, espai);
                currentPis.push({ art_codi: item.art_codi, art_descrip: item.art_descrip, sacs: posar });
                currentCount += posar;
                remaining -= posar;
                if (currentCount >= currentBase) {
                    pisos.push(currentPis);
                    currentPis = [];
                    currentCount = 0;
                }
            }
        }
        if (currentPis.length > 0) pisos.push(currentPis);
        return pisos;
    }

    function escapeHtml(str) {
        const div = document.createElement("div");
        div.textContent = str;
        return div.innerHTML;
    }

    // --- Tooltip preview palets (hover sobre files últimes comandes) ---
    const _tooltipEl = document.createElement("div");
    _tooltipEl.className = "palet-preview-tooltip";
    _tooltipEl.style.display = "none";
    document.body.appendChild(_tooltipEl);
    let _tooltipTimeout = null;

    function _mostrarPreviewPalets(row, pediKey) {
        const data = _calculDataMap.get(pediKey);
        if (!data || !data.embalatges || data.embalatges.length === 0) return;

        const artColors = {};
        let colorIdx = 0;
        data.embalatges.forEach(e => {
            e.contingut.forEach(c => {
                if (!(c.art_codi in artColors)) {
                    artColors[c.art_codi] = colorIdx % 8;
                    colorIdx++;
                }
            });
        });

        const paletsHtml = data.embalatges.map(e => {
            const pisos = calcularPisos(e.contingut, e.sacs_x_base);
            return renderPaletVisual(e, pisos, artColors, 'palet-preview-mini');
        }).join('');

        const estatIcons = { CALCULAT: "\u2705", CALCULAT_AMB_AVISOS: "\u26a0\ufe0f", SOTA_MINIM: "\u26a0\ufe0f", NO_CALCULABLE: "\u274c" };
        const estatLabels = { CALCULAT: "OK", CALCULAT_AMB_AVISOS: "Avisos", SOTA_MINIM: "Sota m\u00ednim", NO_CALCULABLE: "Revisi\u00f3" };
        const estatStr = `${estatIcons[data.estat] || ""} ${estatLabels[data.estat] || data.estat}`;
        const totalSacs = data.resum ? data.resum.total_sacs : 0;
        const totalPalets = data.resum ? data.resum.total_palets : 0;

        _tooltipEl.innerHTML = `
            <div class="palet-preview-header">
                <span class="mini-estat mini-estat-${data.estat}">${estatStr}</span>
                <span>${totalSacs} sacs · ${totalPalets} palet${totalPalets !== 1 ? 's' : ''}</span>
            </div>
            <div class="palet-preview-grid">${paletsHtml}</div>`;

        // Posicionar tooltip
        const rect = row.getBoundingClientRect();
        const tooltipWidth = 320;
        let left = rect.right + 8;
        // Si no hi cap a la dreta, posar a l'esquerra
        if (left + tooltipWidth > window.innerWidth) {
            left = rect.left - tooltipWidth - 8;
        }
        // Si tampoc cap a l'esquerra, centrar a sota
        if (left < 0) {
            left = Math.max(8, rect.left);
        }
        let top = rect.top;
        // Ajustar si surt per sota de la pantalla
        _tooltipEl.style.display = "block";
        const tooltipHeight = _tooltipEl.offsetHeight;
        if (top + tooltipHeight > window.innerHeight - 8) {
            top = Math.max(8, window.innerHeight - tooltipHeight - 8);
        }

        _tooltipEl.style.left = `${left}px`;
        _tooltipEl.style.top = `${top}px`;
    }

    function _amagarPreviewPalets() {
        _tooltipEl.style.display = "none";
    }

    // Delegació d'events per hover sobre files (mouseover/mouseout fan bubble)
    let _tooltipCurrentRow = null;
    document.getElementById("ultimes-body").addEventListener("mouseover", (ev) => {
        if (!_previewPaletsActiu) return;
        const row = ev.target.closest(".ultimes-row");
        if (!row || row === _tooltipCurrentRow) return;
        _tooltipCurrentRow = row;
        clearTimeout(_tooltipTimeout);
        _tooltipTimeout = setTimeout(() => {
            const pediKey = row.dataset.pediKey;
            if (pediKey && _calculDataMap.has(pediKey)) {
                _mostrarPreviewPalets(row, pediKey);
            }
        }, 300);
    });

    document.getElementById("ultimes-body").addEventListener("mouseout", (ev) => {
        const row = ev.target.closest(".ultimes-row");
        const related = ev.relatedTarget ? ev.relatedTarget.closest(".ultimes-row") : null;
        // Només amagar si sortim de la fila (no si movem entre cel·les de la mateixa fila)
        if (row && row !== related) {
            _tooltipCurrentRow = null;
            clearTimeout(_tooltipTimeout);
            _amagarPreviewPalets();
        }
    });

    // Amagar tooltip quan es fa scroll
    window.addEventListener("scroll", _amagarPreviewPalets, true);

    // --- Ultimes comandes ---
    function _crearFilaComanda(c) {
        // Número visible: DocNum SAP (pedi_numero). NumAtCard queda al tooltip.
        const serieNum = c.pedi_serie
            ? `${c.pedi_serie}/${c.pedi_numero}`
            : c.pedi_numero;
        // sal_codigo real + cpa_albara per la crida API
        const salNum = c.sal_codigo
            ? `${c.sal_codigo}/${c.pedi_numero}`
            : `${c.pedi_serie}/${c.pedi_numero}`;
        const miniSpinner = '<span class="mini-spinner"></span>';
        const tr = document.createElement("tr");
        tr.className = "ultimes-row";
        tr.dataset.pediKey = serieNum;
        tr.dataset.salKey = salNum;
        tr.dataset.serie = c.pedi_serie || "";
        tr.dataset.date = c.pedi_fech || "";
        tr.dataset.client = c.cli_nom || "";
        tr.dataset.almacen = c.almacen || "";
        tr.dataset.numPedidoKais = c.num_pedido_kais || "";
        tr.innerHTML = `
            <td class="art-code"${c.num_pedido_kais ? ` title="Ref. client: ${escapeHtml(c.num_pedido_kais)}"` : ""}>${escapeHtml(serieNum)}</td>
            <td>${escapeHtml(c.pedi_fech)}</td>
            <td>${escapeHtml(c.data_servir || "")}</td>
            <td>${escapeHtml(c.cli_nom)}</td>
            <td class="mono">${escapeHtml(c.pedi_dire)}</td>
            <td>${escapeHtml(c.agent || "")}</td>
            <td class="td-tipus-desc">${miniSpinner}</td>
            <td class="num">${c.num_linies}</td>
            <td class="num">${c.total_unitats}</td>
            <td class="td-estat">${miniSpinner}</td>
            <td class="td-palets num">${miniSpinner}</td>
            <td class="td-tipus-palet">${miniSpinner}</td>`;
        tr.addEventListener("click", () => {
            input.value = serieNum;
            form.dispatchEvent(new Event("submit"));
        });
        return tr;
    }

    function _comandaKey(c) {
        return `${c.pedi_serie}/${c.pedi_numero}`;
    }

    function _fingerComanda(c) {
        return `${_comandaKey(c)}|${c.num_linies}|${c.total_unitats}|${c.pedi_fech}|${c.pedi_dire}`;
    }

    function _actualitzarTaulaComandes(comandes) {
        const tbody = document.getElementById("ultimes-body");
        const nouMap = new Map();
        comandes.forEach(c => nouMap.set(_comandaKey(c), c));

        // 1. Detectar files existents
        const existents = new Map();
        tbody.querySelectorAll(".ultimes-row").forEach(row => {
            existents.set(row.dataset.pediKey, row);
        });

        // 2. Eliminar files que ja no existeixen
        existents.forEach((row, key) => {
            if (!nouMap.has(key)) {
                row.remove();
                _estatsCalculats.delete(key);
            }
        });

        // 3. Actualitzar o inserir, mantenint l'ordre del servidor
        let prevRow = null;
        for (const c of comandes) {
            const key = _comandaKey(c);
            const existing = existents.get(key);

            if (existing) {
                // Actualitzar dades estàtiques si han canviat (linies, unitats, data)
                const oldFinger = _fingerComanda({
                    pedi_serie: c.pedi_serie,
                    pedi_numero: c.pedi_numero,
                    num_linies: parseInt(existing.querySelectorAll("td")[7].textContent) || 0,
                    total_unitats: parseInt(existing.querySelectorAll("td")[8].textContent) || 0,
                    pedi_fech: existing.dataset.date,
                    pedi_dire: existing.querySelectorAll("td")[4].textContent.trim(),
                });
                const newFinger = _fingerComanda(c);
                if (oldFinger !== newFinger) {
                    // Dades estàtiques canviades → recalcular estat
                    const serieNum = `${c.pedi_serie}/${c.pedi_numero}`;
                    existing.querySelectorAll("td")[0].textContent = serieNum;
                    existing.querySelectorAll("td")[1].textContent = c.pedi_fech;
                    existing.querySelectorAll("td")[2].textContent = c.data_servir || "";
                    existing.querySelectorAll("td")[3].textContent = c.cli_nom;
                    existing.querySelectorAll("td")[4].textContent = c.pedi_dire;
                    existing.querySelectorAll("td")[5].textContent = c.agent || "";
                    existing.querySelectorAll("td")[7].textContent = c.num_linies;
                    existing.querySelectorAll("td")[8].textContent = c.total_unitats;
                    existing.dataset.date = c.pedi_fech || "";
                    existing.dataset.client = c.cli_nom || "";
                    existing.dataset.almacen = c.almacen || "";
                    // Marcar per recalcular estat
                    _estatsCalculats.delete(key);
                    _calculDataMap.delete(key);
                    const miniSpinner = '<span class="mini-spinner"></span>';
                    existing.querySelector(".td-tipus-desc").innerHTML = miniSpinner;
                    existing.querySelector(".td-estat").innerHTML = miniSpinner;
                    existing.querySelector(".td-palets").innerHTML = miniSpinner;
                    existing.querySelector(".td-tipus-palet").innerHTML = miniSpinner;
                }
                // Assegurar ordre correcte
                if (prevRow) {
                    prevRow.after(existing);
                } else {
                    tbody.prepend(existing);
                }
                prevRow = existing;
            } else {
                // Nova comanda → crear fila
                const newRow = _crearFilaComanda(c);
                if (prevRow) {
                    prevRow.after(newRow);
                } else {
                    tbody.prepend(newRow);
                }
                prevRow = newRow;
            }
        }
    }

    let _lastLoadTime = Date.now();

    async function carregarUltimesComandes(deltaUpdate) {
        _lastLoadTime = Date.now();
        if (!deltaUpdate) { _estatsCalculats.clear(); _calculDataMap.clear(); }
        try {
            const resp = await fetch("/api/ultimes-comandes");
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const data = await resp.json();
            const loading = document.getElementById("ultimes-loading");
            const table = document.getElementById("ultimes-table");
            const tbody = document.getElementById("ultimes-body");

            if (!data.ok) {
                loading.innerHTML = `<p style="color: var(--danger);">Error carregant comandes</p>`;
                return;
            }

            _allComandes = data.comandes;

            if (deltaUpdate && table.style.display === "table") {
                // Delta-update: preservar scroll, estats calculats i context
                _actualitzarTaulaComandes(data.comandes);
            } else {
                // Càrrega inicial completa
                tbody.innerHTML = data.comandes
                    .map((c) => {
                        const tr = _crearFilaComanda(c);
                        return tr.outerHTML;
                    })
                    .join("");
                // Re-attach event listeners (outerHTML perd els listeners)
                tbody.querySelectorAll(".ultimes-row").forEach((row) => {
                    row.addEventListener("click", () => {
                        input.value = row.dataset.pediKey;
                        form.dispatchEvent(new Event("submit"));
                    });
                });
                loading.style.display = "none";
                table.style.display = "table";
            }

            // Aplicar ordenació activa (si n'hi ha) al DOM ja renderitzat
            ordenarFilesDom();
            actualitzarIndicadorsSort();

            // Poblar filtres multi-select
            _poblarFiltreSeries(data.comandes);
            _poblarFiltreClients(data.comandes);

            // Restaurar filtres guardats
            const saved = _carregarFiltres();
            if (saved) {
                if (saved.text) document.getElementById("filtre-text").value = saved.text;
                if (saved.estat) document.getElementById("filtre-estat").value = saved.estat;
                if (saved.tipusDesc) document.getElementById("filtre-tipus-desc").value = saved.tipusDesc;
                if ("data" in saved) document.getElementById("filtre-data").value = saved.data;
            }

            // Amagar files més enllà del límit inicial
            aplicarFiltres();

            // Calcular estat/palets progressivament en segon pla
            calcularEstatsVisibles();
        } catch (err) {
            if (!document.getElementById("ultimes-table").style.display) {
                document.getElementById("ultimes-loading").innerHTML =
                    `<p style="color: var(--danger);">Error de connexió amb el servidor.</p>`;
            }
        }
    }

    const _estatsCalculats = new Set();  // pediKey ja calculats
    const _calculDataMap = new Map();   // pediKey -> dades càlcul (per tooltip)
    let _calculantEstats = false;

    // ── Cache persistent a localStorage ──
    const _CACHE_KEY = "comandes_calcul_cache";
    const _CACHE_TTL_MS = 10 * 60 * 1000;  // 10 minuts: recalcular per detectar canvis a dades mestres

    function _loadCache() {
        try {
            return JSON.parse(localStorage.getItem(_CACHE_KEY) || "{}");
        } catch { return {}; }
    }

    function _saveCache(cache) {
        try {
            // Limitar a 500 entrades per no omplir localStorage
            const keys = Object.keys(cache);
            if (keys.length > 500) {
                keys.slice(0, keys.length - 500).forEach(k => delete cache[k]);
            }
            localStorage.setItem(_CACHE_KEY, JSON.stringify(cache));
        } catch {}
    }

    function _getCachedResult(pediKey, fingerprint) {
        const cache = _loadCache();
        const entry = cache[pediKey];
        if (!entry || entry.finger !== fingerprint) return null;
        // TTL: invalidar cache si fa més de 10 minuts
        if (entry.ts && (Date.now() - entry.ts) > _CACHE_TTL_MS) return null;
        return entry.data;
    }

    function _setCachedResult(pediKey, fingerprint, data) {
        const cache = _loadCache();
        cache[pediKey] = { finger: fingerprint, data: data, ts: Date.now() };
        _saveCache(cache);
    }

    function _getRowFingerprint(row) {
        const tds = row.querySelectorAll("td");
        const linies = tds[6] ? tds[6].textContent.trim() : "";
        const sacs = tds[7] ? tds[7].textContent.trim() : "";
        const dire = tds[3] ? tds[3].textContent.trim() : "";
        return `${row.dataset.pediKey}|${linies}|${sacs}|${dire}`;
    }

    function _aplicarResultatAFila(row, pediKey, data) {
        const tdTipusDesc = row.querySelector(".td-tipus-desc");
        const tdEstat = row.querySelector(".td-estat");
        const tdPalets = row.querySelector(".td-palets");
        const tdTipus = row.querySelector(".td-tipus-palet");

        if (data.ok) {
            _calculDataMap.set(pediKey, data);
                const td = data.direccio ? (data.direccio.tipus_descarrega || "-") : "-";
                tdTipusDesc.textContent = td;
                tdTipusDesc.dataset.tipusDesc = data.direccio ? (data.direccio.tipus_descarrega || "") : "";

                const estatIcons = { CALCULAT: "\u2705", CALCULAT_AMB_AVISOS: "\u26a0\ufe0f", SOTA_MINIM: "\u26a0\ufe0f", NO_CALCULABLE: "\u274c" };
                const estatLabels = { CALCULAT: "OK", CALCULAT_AMB_AVISOS: "Avisos", SOTA_MINIM: "Sota m\u00ednim", NO_CALCULABLE: "Revisi\u00f3" };
                let tooltip = "";
                if (data.missatges && data.missatges.length && data.estat !== "CALCULAT") {
                    tooltip = escapeHtml(data.missatges.join(" | "));
                }
                tdEstat.innerHTML = `<span class="mini-estat mini-estat-${data.estat}" ${tooltip ? `title="${tooltip}"` : ""}>${estatIcons[data.estat] || ""} ${estatLabels[data.estat] || data.estat}</span>`;
                tdEstat.dataset.estat = data.estat;

                const numPalets = data.resum ? data.resum.total_palets : 0;
                tdPalets.textContent = numPalets;

                if (data.palets && data.palets.length > 0) {
                    tdTipus.innerHTML = data.palets
                        .map(p => {
                            const nom = escapeHtml(p.art_descrip)
                                .replace(/PALET\s*/i, "")
                                .replace(/\s*\d+X\d+/i, "")
                                .trim();
                            return `<span class="mini-tipus-palet" title="${escapeHtml(p.art_descrip)}">${nom} (${p.quantitat})</span>`;
                        })
                        .join(", ");
                } else {
                    tdTipus.textContent = "-";
                }
            } else {
                tdTipusDesc.textContent = "-";
                tdEstat.innerHTML = `<span class="mini-estat mini-estat-NO_CALCULABLE">\u274c Error</span>`;
                tdPalets.textContent = "-";
                tdTipus.textContent = "-";
            }
    }

    async function processarComandaEstat(pediKey) {
        const tbody = document.getElementById("ultimes-body");
        const row = tbody.querySelector(`tr[data-pedi-key="${CSS.escape(pediKey)}"]`);
        if (!row) return;

        // Comprovar cache persistent (localStorage)
        const finger = _getRowFingerprint(row);
        const cached = _getCachedResult(pediKey, finger);
        if (cached) {
            _aplicarResultatAFila(row, pediKey, cached);
            _estatsCalculats.add(pediKey);
            return;
        }

        // Sense cache: fer la crida al servidor
        const apiKey = row.dataset.salKey || pediKey;
        const tdTipusDesc = row.querySelector(".td-tipus-desc");
        const tdEstat = row.querySelector(".td-estat");
        const tdPalets = row.querySelector(".td-palets");
        const tdTipus = row.querySelector(".td-tipus-palet");
        try {
            const ac = new AbortController();
            const tid = setTimeout(() => ac.abort(), 15000);
            const resp = await fetch(`/api/calcular/${encodeURIComponent(apiKey)}`, { signal: ac.signal });
            clearTimeout(tid);
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const data = await resp.json();
            _aplicarResultatAFila(row, pediKey, data);
            // Guardar al cache persistent
            if (data.ok) _setCachedResult(pediKey, finger, data);
        } catch (err) {
            tdTipusDesc.textContent = "-";
            const isTimeout = err && (err.name === "TimeoutError" || err.name === "AbortError");
            tdEstat.innerHTML = `<span class="mini-estat mini-estat-error" title="${isTimeout ? 'Temps excedit' : 'Error de connexió'}">${isTimeout ? '\u23F1' : '\u274c'} ${isTimeout ? 'Timeout' : 'Error'}</span>`;
            tdPalets.textContent = "-";
            tdTipus.textContent = "-";
        }
        _estatsCalculats.add(pediKey);
    }

    let _recalcularDespres = false;

    async function calcularEstatsVisibles() {
        // Calcula l'estat de les files visibles.
        // Les cacheades (localStorage) s'apliquen instantàniament, la resta es calculen al servidor.
        if (_calculantEstats) {
            _recalcularDespres = true;
            return;
        }
        _calculantEstats = true;
        _recalcularDespres = false;

        const tbody = document.getElementById("ultimes-body");
        const rows = tbody.querySelectorAll(".ultimes-row");
        const MAX_CONCURRENT = 3;

        // Recollir pediKeys visibles pendents de calcular
        const pendents = [];
        rows.forEach(row => {
            if (row.style.display !== "none") {
                const key = row.dataset.pediKey;
                if (!_estatsCalculats.has(key)) {
                    pendents.push(key);
                }
            }
        });

        // Primer pas: aplicar cacheats instantàniament (0 queries)
        const pendentsServer = [];
        for (const key of pendents) {
            const row = tbody.querySelector(`tr[data-pedi-key="${CSS.escape(key)}"]`);
            if (!row) continue;
            const finger = _getRowFingerprint(row);
            const cached = _getCachedResult(key, finger);
            if (cached) {
                _aplicarResultatAFila(row, key, cached);
                _estatsCalculats.add(key);
            } else {
                pendentsServer.push(key);
            }
        }

        if (pendentsServer.length === 0) {
            _calculantEstats = false;
            if (_recalcularDespres) calcularEstatsVisibles();
            return;
        }

        // Mostrar progrés a la capçalera
        const header = document.querySelector("#empty-state .card-header span");
        const originalText = header ? header.textContent : "";

        // NOTA: /api/calcular-batch (POST) queda bloquejat per Windows Defender
        // en aquest entorn local. Fem crides GET individuals (/api/calcular/...)
        // amb concurrència limitada. A producció Ubuntu el POST batch funciona
        // sense problema — allà es podria restaurar per rendiment.
        let completats = 0;
        const MAX_CONCURRENT_GET = 3;
        for (let i = 0; i < pendentsServer.length; i += MAX_CONCURRENT_GET) {
            const lot = pendentsServer.slice(i, i + MAX_CONCURRENT_GET);
            await Promise.all(lot.map(pn => processarComandaEstat(pn)));
            completats += lot.length;
            if (header) header.textContent = `Calculant ${completats}/${pendentsServer.length}...`;
        }

        if (header) header.textContent = originalText;
        _calculantEstats = false;
        // Si s'està ordenant per una columna derivada, re-ordenar ara que les dades són completes
        if (_sortState.key && ["tipus_desc", "estat", "palets", "tipus_palet"].includes(_sortState.key)) {
            ordenarFilesDom();
            aplicarFiltres();
        }
        if (_recalcularDespres) calcularEstatsVisibles();
    }

    carregarUltimesComandes();
    input.focus();

    // --- Filtre multi-select de magatzems ---
    const _selectedMagatzems = new Set();

    (async function carregarMagatzems() {
        try {
            const resp = await fetch("/api/magatzems");
            const data = await resp.json();
            if (data.ok && data.magatzems) {
                const optionsDiv = document.getElementById("filtre-magatzem-options");
                optionsDiv.innerHTML = data.magatzems.map(m => {
                    const val = m.almacen;
                    const text = `${val} - ${escapeHtml(m.nom)}`;
                    return `<label><input type="checkbox" value="${val}"> ${text}</label>`;
                }).join("");
                optionsDiv.querySelectorAll("input[type=checkbox]").forEach(cb => {
                    cb.addEventListener("change", () => {
                        if (cb.checked) _selectedMagatzems.add(cb.value);
                        else _selectedMagatzems.delete(cb.value);
                        _actualitzarBotoMagatzems();
                        aplicarFiltres();
                        calcularEstatsVisibles();
                        _guardarFiltres();
                    });
                });
                // Restaurar magatzems guardats
                const saved = _carregarFiltres();
                if (saved && saved.magatzems && saved.magatzems.length > 0) {
                    optionsDiv.querySelectorAll("input[type=checkbox]").forEach(cb => {
                        if (saved.magatzems.includes(cb.value)) {
                            cb.checked = true;
                            _selectedMagatzems.add(cb.value);
                        }
                    });
                    _actualitzarBotoMagatzems();
                    aplicarFiltres();
                    calcularEstatsVisibles();
                }
            }
        } catch (e) { /* ignorem errors de càrrega */ }
    })();

    function _actualitzarBotoMagatzems() {
        const btn = document.getElementById("filtre-magatzem-btn");
        if (_selectedMagatzems.size === 0) {
            btn.textContent = "Tots els magatzems \u25BE";
            btn.classList.remove("active");
        } else if (_selectedMagatzems.size === 1) {
            btn.textContent = [..._selectedMagatzems][0] + " \u25BE";
            btn.classList.add("active");
        } else {
            btn.textContent = `${_selectedMagatzems.size} magatzems \u25BE`;
            btn.classList.add("active");
        }
    }

    document.getElementById("filtre-magatzem-btn").addEventListener("click", (e) => {
        e.stopPropagation();
        const dd = document.getElementById("filtre-magatzem-dropdown");
        dd.classList.toggle("hidden");
    });

    document.getElementById("filtre-magatzem-clear").addEventListener("click", () => {
        _selectedMagatzems.clear();
        document.querySelectorAll("#filtre-magatzem-options input[type=checkbox]").forEach(cb => cb.checked = false);
        _actualitzarBotoMagatzems();
        aplicarFiltres();
        calcularEstatsVisibles();
        _guardarFiltres();
    });

    document.getElementById("filtre-magatzem-dropdown").addEventListener("click", (e) => {
        e.stopPropagation();
    });

    // --- Filtre multi-select de sèries ---
    const _selectedSeries = new Set();

    function _poblarFiltreSeries(comandes) {
        const optionsDiv = document.getElementById("filtre-serie-options");
        const series = [...new Set(comandes.map(c => c.pedi_serie).filter(Boolean))].sort(
            (a, b) => a.localeCompare(b)
        );
        optionsDiv.innerHTML = series.map(s => {
            const safe = escapeHtml(s);
            return `<label><input type="checkbox" value="${safe}"> ${safe}</label>`;
        }).join("");

        optionsDiv.querySelectorAll("input[type=checkbox]").forEach(cb => {
            cb.addEventListener("change", () => {
                if (cb.checked) _selectedSeries.add(cb.value);
                else _selectedSeries.delete(cb.value);
                _actualitzarBotoSeries();
                aplicarFiltres();
                calcularEstatsVisibles();
                _guardarFiltres();
            });
        });

        // Restaurar sèries guardades
        const saved = _carregarFiltres();
        if (saved && saved.series && saved.series.length > 0) {
            optionsDiv.querySelectorAll("input[type=checkbox]").forEach(cb => {
                if (saved.series.includes(cb.value)) {
                    cb.checked = true;
                    _selectedSeries.add(cb.value);
                }
            });
            _actualitzarBotoSeries();
            aplicarFiltres();
        }
    }

    function _actualitzarBotoSeries() {
        const btn = document.getElementById("filtre-serie-btn");
        if (_selectedSeries.size === 0) {
            btn.textContent = "Totes les s\u00E8ries \u25BE";
            btn.classList.remove("active");
        } else if (_selectedSeries.size === 1) {
            btn.textContent = "S\u00E8rie " + [..._selectedSeries][0] + " \u25BE";
            btn.classList.add("active");
        } else {
            btn.textContent = `${_selectedSeries.size} s\u00E8ries \u25BE`;
            btn.classList.add("active");
        }
    }

    document.getElementById("filtre-serie-btn").addEventListener("click", (e) => {
        e.stopPropagation();
        document.getElementById("filtre-serie-dropdown").classList.toggle("hidden");
    });

    document.getElementById("filtre-serie-clear").addEventListener("click", () => {
        _selectedSeries.clear();
        document.querySelectorAll("#filtre-serie-options input[type=checkbox]").forEach(cb => cb.checked = false);
        _actualitzarBotoSeries();
        aplicarFiltres();
        calcularEstatsVisibles();
        _guardarFiltres();
    });

    document.getElementById("filtre-serie-dropdown").addEventListener("click", (e) => {
        e.stopPropagation();
    });

    // --- Filtres últimes comandes ---
    const LIMIT_VISIBLE = 25;
    let _showAll = false;

    function _parseDate(ddmmyyyy) {
        // "02/04/2026" -> Date
        const p = ddmmyyyy.split("/");
        if (p.length !== 3) return null;
        return new Date(+p[2], +p[1] - 1, +p[0]);
    }

    // --- Filtre multi-select de clients ---
    const _selectedClients = new Set();

    function _poblarFiltreClients(comandes) {
        const optionsDiv = document.getElementById("filtre-client-options");
        // Extreure noms únics, ordenats alfabèticament
        const noms = [...new Set(comandes.map(c => c.cli_nom).filter(Boolean))].sort(
            (a, b) => a.localeCompare(b, "ca")
        );
        optionsDiv.innerHTML = noms.map(nom => {
            const safe = escapeHtml(nom);
            return `<label><input type="checkbox" value="${safe}"> ${safe}</label>`;
        }).join("");

        // Listener per cada checkbox
        optionsDiv.querySelectorAll("input[type=checkbox]").forEach(cb => {
            cb.addEventListener("change", () => {
                if (cb.checked) _selectedClients.add(cb.value);
                else _selectedClients.delete(cb.value);
                _actualitzarBotoClients();
                aplicarFiltres();
                calcularEstatsVisibles();
                _guardarFiltres();
            });
        });

        // Restaurar clients guardats
        const saved = _carregarFiltres();
        if (saved && saved.clients && saved.clients.length > 0) {
            optionsDiv.querySelectorAll("input[type=checkbox]").forEach(cb => {
                if (saved.clients.includes(cb.value)) {
                    cb.checked = true;
                    _selectedClients.add(cb.value);
                }
            });
            _actualitzarBotoClients();
            aplicarFiltres();
        }
    }

    function _actualitzarBotoClients() {
        const btn = document.getElementById("filtre-client-btn");
        if (_selectedClients.size === 0) {
            btn.textContent = "Tots els clients \u25BE";
            btn.classList.remove("active");
        } else if (_selectedClients.size === 1) {
            btn.textContent = [..._selectedClients][0] + " \u25BE";
            btn.classList.add("active");
        } else {
            btn.textContent = `${_selectedClients.size} clients \u25BE`;
            btn.classList.add("active");
        }
    }

    // Toggle dropdown
    document.getElementById("filtre-client-btn").addEventListener("click", (e) => {
        e.stopPropagation();
        const dd = document.getElementById("filtre-client-dropdown");
        dd.classList.toggle("hidden");
        if (!dd.classList.contains("hidden")) {
            document.getElementById("filtre-client-search").value = "";
            document.getElementById("filtre-client-search").focus();
            _filtrarOpcionsClients("");
        }
    });

    // Cercar dins del dropdown
    document.getElementById("filtre-client-search").addEventListener("input", (e) => {
        _filtrarOpcionsClients(e.target.value.toLowerCase().trim());
    });

    function _filtrarOpcionsClients(text) {
        document.querySelectorAll("#filtre-client-options label").forEach(lbl => {
            lbl.style.display = !text || lbl.textContent.toLowerCase().includes(text) ? "" : "none";
        });
    }

    // Botó netejar
    document.getElementById("filtre-client-clear").addEventListener("click", () => {
        _selectedClients.clear();
        document.querySelectorAll("#filtre-client-options input[type=checkbox]").forEach(cb => cb.checked = false);
        _actualitzarBotoClients();
        aplicarFiltres();
        calcularEstatsVisibles();
        _guardarFiltres();
    });

    // Tancar dropdowns multi-select en clicar fora
    document.addEventListener("click", (e) => {
        const wrapClient = document.getElementById("filtre-client-wrap");
        if (!wrapClient.contains(e.target)) {
            document.getElementById("filtre-client-dropdown").classList.add("hidden");
        }
        const wrapMag = document.getElementById("filtre-magatzem-wrap");
        if (wrapMag && !wrapMag.contains(e.target)) {
            document.getElementById("filtre-magatzem-dropdown").classList.add("hidden");
        }
        const wrapSerie = document.getElementById("filtre-serie-wrap");
        if (wrapSerie && !wrapSerie.contains(e.target)) {
            document.getElementById("filtre-serie-dropdown").classList.add("hidden");
        }
    });

    // Evitar que clics dins del dropdown el tanquin
    document.getElementById("filtre-client-dropdown").addEventListener("click", (e) => {
        e.stopPropagation();
    });

    function aplicarFiltres() {
        const textFiltre = document.getElementById("filtre-text").value.toLowerCase().trim();
        const estatFiltre = document.getElementById("filtre-estat").value;
        const tipusDescFiltre = document.getElementById("filtre-tipus-desc").value;
        const serieFiltre = _selectedSeries.size > 0;
        const magatzemFiltre = _selectedMagatzems.size > 0;
        const dataFiltre = document.getElementById("filtre-data").value;
        const clientFiltre = _selectedClients.size > 0;
        const rows = document.querySelectorAll("#ultimes-body .ultimes-row");
        const teCerca = textFiltre || estatFiltre || tipusDescFiltre || serieFiltre || magatzemFiltre || dataFiltre || clientFiltre;

        // Calcular rang de dates [dataMin, dataMax] inclusiu.
        // "Avui" = només dia d'avui. "Ahir" = només dia d'ahir. "Setmana" = últims 7 dies.
        let dataMin = null, dataMax = null;
        if (dataFiltre) {
            const avui = new Date();
            avui.setHours(0, 0, 0, 0);
            if (dataFiltre === "avui") {
                dataMin = avui;
                dataMax = avui;
            } else if (dataFiltre === "ahir") {
                dataMin = new Date(avui); dataMin.setDate(dataMin.getDate() - 1);
                dataMax = dataMin;
            } else if (dataFiltre === "setmana") {
                dataMin = new Date(avui); dataMin.setDate(dataMin.getDate() - 7);
                dataMax = avui;
            }
        }

        let visibleCount = 0;
        let matchCount = 0;
        let truncated = false;
        rows.forEach(row => {
            const text = row.textContent.toLowerCase();
            const estatCell = row.querySelector(".td-estat");
            const tipusDescCell = row.querySelector(".td-tipus-desc");
            const estatVal = estatCell ? (estatCell.dataset.estat || "") : "";
            const tipusDescVal = tipusDescCell ? (tipusDescCell.dataset.tipusDesc || "") : "";

            // Incloure num_pedido_kais al text de cerca
            const searchText = text + " " + (row.dataset.numPedidoKais || "").toLowerCase();
            let match = true;
            if (textFiltre && !searchText.includes(textFiltre)) match = false;
            if (estatFiltre && estatVal !== estatFiltre) match = false;
            if (tipusDescFiltre && tipusDescVal !== tipusDescFiltre) match = false;
            if (serieFiltre && !_selectedSeries.has(row.dataset.serie || "")) match = false;
            if (magatzemFiltre && !_selectedMagatzems.has(row.dataset.almacen || "")) match = false;
            if (clientFiltre && !_selectedClients.has(row.dataset.client || "")) match = false;

            // Filtre per data (rang inclusiu [dataMin, dataMax])
            if (dataMin && match) {
                const rowDate = _parseDate(row.dataset.date || "");
                if (!rowDate || rowDate < dataMin || rowDate > dataMax) match = false;
            }

            if (match) matchCount++;

            let visible = match;
            // Sense "veure totes" i sense filtre actiu, limitar a LIMIT_VISIBLE files
            if (!_showAll && !teCerca && match && visibleCount >= LIMIT_VISIBLE) {
                visible = false;
                truncated = true;
            }

            row.style.display = visible ? "" : "none";
            if (visible) visibleCount++;
        });

        // Actualitzar comptador
        const footer = document.getElementById("table-footer");
        const countText = document.getElementById("table-count-text");
        const btnVeure = document.getElementById("btn-veure-totes");
        if (rows.length > 0) {
            footer.style.display = "";
            const total = rows.length;
            if (teCerca) {
                countText.textContent = `Mostrant ${visibleCount} de ${total} comandes`;
                btnVeure.style.display = "none";
            } else if (truncated) {
                countText.textContent = `Mostrant ${visibleCount} de ${matchCount} comandes`;
                btnVeure.style.display = "";
                btnVeure.textContent = `Veure totes (${matchCount})`;
            } else {
                countText.textContent = `${visibleCount} comandes`;
                btnVeure.style.display = _showAll ? "" : "none";
                if (_showAll) btnVeure.textContent = "Mostrar menys";
            }
        } else {
            footer.style.display = "none";
        }
    }

    document.getElementById("btn-veure-totes").addEventListener("click", () => {
        _showAll = !_showAll;
        aplicarFiltres();
        calcularEstatsVisibles();
    });

    // Debounce per evitar recàlculs excessius al teclejar
    let _filtreTimeout;
    function _debouncedFiltres(delay) {
        clearTimeout(_filtreTimeout);
        _filtreTimeout = setTimeout(() => { aplicarFiltres(); calcularEstatsVisibles(); _guardarFiltres(); }, delay);
    }
    document.getElementById("filtre-text").addEventListener("input", () => _debouncedFiltres(250));
    document.getElementById("filtre-estat").addEventListener("change", () => { aplicarFiltres(); calcularEstatsVisibles(); _guardarFiltres(); });
    document.getElementById("filtre-tipus-desc").addEventListener("change", () => { aplicarFiltres(); calcularEstatsVisibles(); _guardarFiltres(); });
    document.getElementById("filtre-data").addEventListener("change", () => { aplicarFiltres(); calcularEstatsVisibles(); _guardarFiltres(); });

    // Ordenació per clic/Enter/Espai a la capçalera
    (function inicialitzarOrdenacio() {
        const thead = document.getElementById("ultimes-table")?.querySelector("thead");
        if (!thead) return;
        function activarOrdenacio(th) {
            if (!th || !th.classList.contains("sortable")) return;
            _sortState = ciclarOrdenacio(th.dataset.sortKey, th.dataset.sortType);
            _guardarOrdenacio();
            actualitzarIndicadorsSort();
            ordenarFilesDom();
            aplicarFiltres();
        }
        thead.addEventListener("click", (e) => {
            activarOrdenacio(e.target.closest("th.sortable"));
        });
        thead.addEventListener("keydown", (e) => {
            if (e.key !== "Enter" && e.key !== " ") return;
            const th = e.target.closest("th.sortable");
            if (!th) return;
            e.preventDefault();
            activarOrdenacio(th);
        });
        actualitzarIndicadorsSort();
    })();

    // Comprovar canvis a comandes cada ~45s (amb jitter ±5s).
    // Es pausa automàticament quan la pestanya no és visible
    // per evitar càrrega SQL innecessària (p.ex. navegador obert tota la nit).
    let _lastFingerprint = 0;
    let _pollActive = true;

    document.addEventListener("visibilitychange", () => {
        if (document.hidden) {
            _pollActive = false;
        } else {
            _pollActive = true;
            // Recarregar només si fa més de 60s que no s'ha carregat
            const elapsed = Date.now() - _lastLoadTime;
            if (elapsed > 60000 && !emptyState.classList.contains("hidden")) {
                carregarUltimesComandes(true);
            }
        }
    });

    function _schedulePoll() {
        const jitter = 60000 + Math.floor(Math.random() * 15000); // 60-75s
        setTimeout(async () => {
            if (_pollActive && !emptyState.classList.contains("hidden")) {
                try {
                    const resp = await fetch("/api/comandes-check");
                    if (resp.ok) {
                        const data = await resp.json();
                        if (data.ok) {
                            const fp = data.fingerprint || 0;
                            if (_lastFingerprint !== 0 && fp !== _lastFingerprint) {
                                carregarUltimesComandes(true);
                            }
                            _lastFingerprint = fp;
                        }
                    }
                } catch (e) { /* silenci */ }
            }
            _schedulePoll();
        }, jitter);
    }
    _schedulePoll();

    // ==========================================
    // Print
    // ==========================================
    document.getElementById("btn-print").addEventListener("click", () => window.print());

    // ==========================================
    // CSV Export
    // ==========================================
    document.getElementById("btn-export-csv").addEventListener("click", () => {
        if (!lastResultData || !lastResultData.comanda) return;
        const serieNum = `${lastResultData.comanda.pedi_serie}/${lastResultData.comanda.pedi_numero}`;
        window.location.href = `/api/exportar-csv/${encodeURIComponent(serieNum)}`;
    });

    // ==========================================
    // Sol·licitar autorització (comanda < 500 kg)
    // ==========================================
    const LLINDAR_KG_AUTORITZACIO = 500;
    const MAIL_FROM_DISPLAY = "farinera@agrienergia.com";
    const btnSolAuto = document.getElementById("btn-sol-autoritzacio");
    const modalAuto = document.getElementById("modal-autoritzacio");

    function actualitzarBtnAutoritzacio(pesTotalKg) {
        if (!btnSolAuto) return;
        if (pesTotalKg > 0 && pesTotalKg < LLINDAR_KG_AUTORITZACIO) {
            btnSolAuto.classList.remove("hidden");
        } else {
            btnSolAuto.classList.add("hidden");
        }
    }

    function _pesTotalKgFromData(data) {
        if (!data || !data.embalatges) return 0;
        return data.embalatges.reduce((s, e) =>
            s + e.contingut.reduce((s2, c) => s2 + (c.pes_kg || 0), 0), 0);
    }

    function _totalSacsFromData(data) {
        if (!data || !data.linies) return 0;
        return data.linies.reduce((s, l) => s + (l.linea_unidades || 0), 0);
    }

    function _construirBodyHtmlPreview(data) {
        const c = data.comanda || {};
        const pedi = `${c.pedi_serie || "-"}/${c.pedi_numero || "-"}`;
        const cliCodi = c.cli_codi || "-";
        const cliNom = c.cli_nom || "";
        const dataServir = c.data_servir || "-";
        const totalSacs = _totalSacsFromData(data);
        const pesTotal = _pesTotalKgFromData(data);
        const nArticles = (data.linies || []).length;

        const pesPerArt = {};
        (data.embalatges || []).forEach(e => {
            e.contingut.forEach(co => {
                if (co.sacs > 0 && co.pes_kg) {
                    pesPerArt[co.art_codi] = (pesPerArt[co.art_codi] || 0) + co.pes_kg;
                }
            });
        });

        const sTh = "padding:11px 12px; background:#0f2747; color:#e2e8f0; font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:0.6px; text-align:left;";
        const sTd = "padding:11px 12px; font-size:13px; color:#1e293b; border-bottom:1px solid #e5e7eb;";

        const files = (data.linies || []).map((l, i) => {
            const bg = i % 2 === 0 ? "#ffffff" : "#fafbfc";
            const pesArt = pesPerArt[l.art_codi] != null ? pesPerArt[l.art_codi].toFixed(1).replace(/\.0$/, "") : "-";
            return `
                <tr style="background:${bg};">
                    <td style="${sTd} font-family:Consolas,Menlo,monospace; color:#0f2747; font-weight:700;">${escapeHtml(l.art_codi)}</td>
                    <td style="${sTd}">${escapeHtml(l.art_descrip || "")}</td>
                    <td style="${sTd} text-align:center;"><span style="display:inline-block; padding:2px 8px; background:#eef2f7; border-radius:10px; font-size:11px; font-weight:600; color:#475569;">${escapeHtml(l.tunitat || "")}</span></td>
                    <td style="${sTd} text-align:right; font-weight:600;">${l.linea_unidades}</td>
                    <td style="${sTd} text-align:right; color:#64748b;">${pesArt}</td>
                </tr>`;
        }).join("");

        return `
<div style="background:#f1f5f9; padding:24px 12px; font-family:'Segoe UI',Arial,Helvetica,sans-serif; color:#1e293b;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:640px; margin:0 auto; background:#ffffff; border-radius:12px; overflow:hidden; box-shadow:0 4px 24px rgba(15,23,42,0.08);">

        <tr><td style="background:#0f2747; padding:28px 32px; color:#ffffff;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                <tr>
                    <td style="vertical-align:middle;">
                        <div style="font-size:10px; text-transform:uppercase; letter-spacing:2px; color:#94a3b8; font-weight:600; margin-bottom:6px;">FARINERA COROMINA</div>
                        <div style="font-size:22px; font-weight:600; color:#ffffff; line-height:1.3;">Sol·licitud d'autorització</div>
                    </td>
                    <td align="right" style="vertical-align:middle;">
                        <span style="display:inline-block; padding:6px 14px; background:#fbbf24; color:#0f2747; border-radius:20px; font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:0.6px;">Pendent</span>
                    </td>
                </tr>
            </table>
        </td></tr>

        <tr><td style="padding:24px 32px 8px 32px;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                <tr>
                    <td style="padding-right:8px; width:50%; vertical-align:top;">
                        <div style="font-size:10px; text-transform:uppercase; letter-spacing:0.8px; color:#94a3b8; font-weight:700; margin-bottom:4px;">Núm. comanda</div>
                        <div style="font-family:Consolas,Menlo,monospace; font-size:18px; font-weight:700; color:#0f2747;">${escapeHtml(pedi)}</div>
                    </td>
                    <td style="padding-left:8px; width:50%; vertical-align:top;">
                        <div style="font-size:10px; text-transform:uppercase; letter-spacing:0.8px; color:#94a3b8; font-weight:700; margin-bottom:4px;">Client</div>
                        <div style="font-size:15px; font-weight:600; color:#0f2747; line-height:1.3;">${escapeHtml(cliNom) || "—"}</div>
                        <div style="font-family:Consolas,Menlo,monospace; font-size:12px; color:#64748b; margin-top:2px;">${escapeHtml(cliCodi)}</div>
                    </td>
                </tr>
            </table>
        </td></tr>

        <tr><td style="padding:16px 32px 8px 32px;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                <tr>
                    <td width="33%" style="padding:4px;">
                        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#fef2f2; border:1px solid #fecaca; border-radius:8px;">
                            <tr><td style="padding:14px 16px;">
                                <div style="font-size:10px; text-transform:uppercase; letter-spacing:0.8px; color:#b91c1c; font-weight:700;">Pes total</div>
                                <div style="font-size:24px; font-weight:700; color:#991b1b; margin-top:4px; line-height:1.1;">${Math.round(pesTotal)}<span style="font-size:13px; font-weight:600; color:#dc2626;"> kg</span></div>
                            </td></tr>
                        </table>
                    </td>
                    <td width="33%" style="padding:4px;">
                        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px;">
                            <tr><td style="padding:14px 16px;">
                                <div style="font-size:10px; text-transform:uppercase; letter-spacing:0.8px; color:#475569; font-weight:700;">Total sacs</div>
                                <div style="font-size:24px; font-weight:700; color:#0f2747; margin-top:4px; line-height:1.1;">${totalSacs}<span style="font-size:13px; font-weight:600; color:#64748b;"> sacs</span></div>
                            </td></tr>
                        </table>
                    </td>
                    <td width="33%" style="padding:4px;">
                        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px;">
                            <tr><td style="padding:14px 16px;">
                                <div style="font-size:10px; text-transform:uppercase; letter-spacing:0.8px; color:#475569; font-weight:700;">Data servir</div>
                                <div style="font-size:18px; font-weight:700; color:#0f2747; margin-top:6px; line-height:1.1;">${escapeHtml(dataServir)}</div>
                            </td></tr>
                        </table>
                    </td>
                </tr>
            </table>
        </td></tr>

        <tr><td style="padding:16px 32px 24px 32px;">
            <p style="margin:0 0 12px; font-size:14px; line-height:1.6; color:#334155;">Bon dia,</p>
            <p style="margin:0 0 12px; font-size:14px; line-height:1.6; color:#334155;">Tenim una comanda registrada que <strong>no arriba al mínim establert de 20 sacs</strong>.</p>
            <p style="margin:0; font-size:14px; line-height:1.6; color:#334155;">Un cop ens donis l'autorització, confirmarem la comanda al client i al comercial.</p>
        </td></tr>

        <tr><td style="padding:0 32px;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:12px;">
                <tr>
                    <td style="font-size:11px; text-transform:uppercase; letter-spacing:0.8px; color:#475569; font-weight:700;">Detall d'articles</td>
                    <td align="right" style="font-size:11px; color:#94a3b8;">${nArticles} ${nArticles === 1 ? "article" : "articles"}</td>
                </tr>
            </table>
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #e5e7eb; border-radius:8px; border-collapse:separate; border-spacing:0; overflow:hidden;">
                <thead><tr>
                    <th style="${sTh}">Article</th>
                    <th style="${sTh}">Descripció</th>
                    <th style="${sTh} text-align:center;">TUnitat</th>
                    <th style="${sTh} text-align:right;">Sacs</th>
                    <th style="${sTh} text-align:right;">Pes (kg)</th>
                </tr></thead>
                <tbody>${files}</tbody>
            </table>
        </td></tr>

        <tr><td style="padding:24px 32px 28px 32px;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#0f2747; border-radius:10px;">
                <tr><td style="padding:18px 22px;">
                    <div style="font-size:10px; text-transform:uppercase; letter-spacing:1.2px; color:#fbbf24; font-weight:700; margin-bottom:4px;">Acció requerida</div>
                    <div style="font-size:15px; font-weight:600; color:#ffffff; line-height:1.5;">Respon aquest correu indicant si autoritzes la confirmació de la comanda.</div>
                </td></tr>
            </table>
        </td></tr>

        <tr><td style="padding:18px 32px; background:#f8fafc; border-top:1px solid #e5e7eb; color:#94a3b8; font-size:11px; line-height:1.6;">
            Correu generat automàticament pel <strong style="color:#475569;">Motor de Preparació de Comandes de Venda</strong>.<br>
            Per qualsevol consulta, contacta amb Farinera Coromina.
        </td></tr>

    </table>
</div>`;
    }

    function obrirModalAutoritzacio(data) {
        const nomClient = (data.comanda && data.comanda.cli_nom) || "—";
        const subject = `PENDENT AUTORITZACIÓ COMANDA INFERIOR 500KG - ${nomClient}`;
        const defaults = data.mail_defaults || { to: "", cc: "" };

        document.getElementById("modal-mail-from").textContent = MAIL_FROM_DISPLAY;
        document.getElementById("modal-mail-to").value = defaults.to || "";
        document.getElementById("modal-mail-cc").value = defaults.cc || "";
        document.getElementById("modal-mail-subject").textContent = subject;
        document.getElementById("modal-mail-body").innerHTML = _construirBodyHtmlPreview(data);
        document.getElementById("modal-error").classList.add("hidden");
        document.getElementById("modal-error").textContent = "";
        document.getElementById("modal-mode-banner").classList.add("hidden");

        const btnSend = document.getElementById("modal-send");
        btnSend.disabled = false;
        btnSend.textContent = "Enviar correu";
        modalAuto.classList.remove("hidden");
    }

    function tancarModalAutoritzacio() {
        modalAuto.classList.add("hidden");
    }

    if (btnSolAuto) {
        btnSolAuto.addEventListener("click", () => {
            if (!lastResultData || !lastResultData.comanda) return;
            obrirModalAutoritzacio(lastResultData);
        });
    }
    document.getElementById("modal-close").addEventListener("click", tancarModalAutoritzacio);
    document.getElementById("modal-cancel").addEventListener("click", tancarModalAutoritzacio);
    let _modalMousedownTarget = null;
    modalAuto.addEventListener("mousedown", (e) => {
        _modalMousedownTarget = e.target;
    });
    modalAuto.addEventListener("click", (e) => {
        // Només tanca si tant el mousedown com el mouseup s'han produït
        // sobre l'overlay (evita tancar accidentalment quan es fa click
        // dins del modal i el cursor es desplaça mínimament fora).
        if (e.target === modalAuto && _modalMousedownTarget === modalAuto) {
            tancarModalAutoritzacio();
        }
        _modalMousedownTarget = null;
    });
    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && !modalAuto.classList.contains("hidden")) {
            tancarModalAutoritzacio();
        }
    });

    document.getElementById("modal-send").addEventListener("click", async () => {
        if (!lastResultData || !lastResultData.comanda) return;
        const c = lastResultData.comanda;
        const serieNum = `${c.pedi_serie}/${c.pedi_numero}`;
        const toVal = document.getElementById("modal-mail-to").value.trim();
        const ccVal = document.getElementById("modal-mail-cc").value.trim();
        const btn = document.getElementById("modal-send");
        const errEl = document.getElementById("modal-error");
        errEl.classList.add("hidden");

        if (!toVal) {
            errEl.textContent = "El destinatari (Per a) no pot estar buit.";
            errEl.classList.remove("hidden");
            return;
        }

        btn.disabled = true;
        btn.textContent = "Enviant…";
        try {
            const r = await fetch(
                `/api/sol-licitar-autoritzacio/${encodeURIComponent(serieNum)}`,
                {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ to: toVal, cc: ccVal }),
                }
            );
            const j = await r.json();
            if (j.ok) {
                tancarModalAutoritzacio();
                const dest = j.destinatari || toVal;
                alert(`✓ Correu enviat correctament a ${dest}.`);
            } else {
                errEl.textContent = j.error || "Error desconegut enviant el correu.";
                errEl.classList.remove("hidden");
                btn.disabled = false;
                btn.textContent = "Reintentar enviament";
            }
        } catch (err) {
            errEl.textContent = "Error de connexió: " + err.message;
            errEl.classList.remove("hidden");
            btn.disabled = false;
            btn.textContent = "Reintentar enviament";
        }
    });

    // ==========================================
    // Batch processing
    // ==========================================
    const batchState = document.getElementById("batch-state");
    const btnBatch = document.getElementById("btn-batch");
    const btnBatchClose = document.getElementById("btn-batch-close");
    const btnBatchCalc = document.getElementById("btn-batch-calc");

    btnBatch.addEventListener("click", () => {
        batchState.classList.toggle("hidden");
        if (!batchState.classList.contains("hidden")) {
            emptyState.classList.add("hidden");
            resultState.classList.add("hidden");
            document.getElementById("batch-input").focus();
        } else {
            emptyState.classList.remove("hidden");
        }
    });

    btnBatchClose.addEventListener("click", () => {
        batchState.classList.add("hidden");
        emptyState.classList.remove("hidden");
    });

    btnBatchCalc.addEventListener("click", async () => {
        const lines = document.getElementById("batch-input").value
            .split("\n").map(l => l.trim()).filter(l => l);
        if (lines.length === 0) return;

        const resultsDiv = document.getElementById("batch-results");
        const summaryDiv = document.getElementById("batch-summary");
        const progressEl = document.getElementById("batch-progress");
        resultsDiv.innerHTML = "";
        summaryDiv.classList.add("hidden");
        btnBatchCalc.disabled = true;

        let totalSacs = 0, totalPalets = 0;
        const paletTypes = {};
        let completats = 0;

        for (const line of lines) {
            completats++;
            progressEl.textContent = `Processant ${completats}/${lines.length}...`;

            try {
                if (!line.includes("/")) {
                    appendBatchError(resultsDiv, line, "Format invàlid. Usa Sèrie/Número (ex: 51/0002456)");
                    continue;
                }

                const resp = await fetch(`/api/calcular/${encodeURIComponent(line)}`);
                const data = await resp.json();

                if (!data.ok) { appendBatchError(resultsDiv, line, data.error); continue; }

                const sacs = data.resum ? data.resum.total_sacs : 0;
                const palets = data.resum ? data.resum.total_palets : 0;
                totalSacs += sacs;
                totalPalets += palets;
                if (data.palets) data.palets.forEach(p => {
                    paletTypes[p.art_descrip] = (paletTypes[p.art_descrip] || 0) + p.quantitat;
                });

                const clientNom = data.direccio ? (data.direccio.adr_nom || "") : "";
                const estatIcon = { CALCULAT: "\u2705", CALCULAT_AMB_AVISOS: "\u26a0\ufe0f", SOTA_MINIM: "\u26a0\ufe0f", NO_CALCULABLE: "\u274c" }[data.estat] || "";

                resultsDiv.insertAdjacentHTML("beforeend", `<div class="batch-item">
                    <div class="batch-item-header">
                        <span>${estatIcon} <strong>${escapeHtml(line)}</strong> - ${escapeHtml(clientNom)}</span>
                        <span>${sacs} sacs / ${palets} palets</span>
                    </div>
                </div>`);

            } catch (err) {
                appendBatchError(resultsDiv, line, "Error de connexió");
            }
        }

        progressEl.textContent = `Completat: ${lines.length} comandes`;
        btnBatchCalc.disabled = false;

        // Resum consolidat
        const tipusStr = Object.entries(paletTypes)
            .map(([k, v]) => `${v}x ${k.replace(/PALET\s*/i, '').trim()}`)
            .join(", ");
        summaryDiv.classList.remove("hidden");
        summaryDiv.innerHTML = `<div class="resum-prominent">
            <div class="resum-card"><div class="resum-num">${totalSacs}</div><div class="resum-label">Total Sacs</div></div>
            <div class="resum-card card-success"><div class="resum-num">${totalPalets}</div><div class="resum-label">Total Palets</div></div>
            <div class="resum-card"><div class="resum-num">${lines.length}</div><div class="resum-label">Comandes</div>
                <div class="resum-detail">${tipusStr || '-'}</div></div>
        </div>`;
    });

    function appendBatchError(container, line, msg) {
        container.insertAdjacentHTML("beforeend", `<div class="batch-item">
            <div class="batch-item-header" style="color: var(--danger);">
                <span>\u274c <strong>${escapeHtml(line)}</strong></span>
                <span>${escapeHtml(msg)}</span>
            </div>
        </div>`);
    }

    // ==========================================
    // Agrupació de comandes
    // ==========================================
    function detectarAgrupables(comanda) {
        const bannerOld = document.getElementById("agrupar-banner");
        if (bannerOld) bannerOld.remove();

        if (!_allComandes.length) return;

        const cliCodi = comanda.cli_codi;
        const pediDire = comanda.pedi_dire;
        const pediKey = _comandaKey(comanda);
        const fech = comanda.pedi_fech;

        // Buscar comandes del mateix client + direcció + data
        const germanes = _allComandes.filter(c =>
            c.cli_codi === cliCodi &&
            c.pedi_dire === pediDire &&
            c.pedi_fech === fech &&
            _comandaKey(c) !== pediKey
        );

        if (germanes.length === 0) return;

        const nums = germanes.map(c => {
            const sn = c.pedi_serie ? `${c.pedi_serie}/${c.pedi_numero}` : c.pedi_numero;
            return `<strong>${sn}</strong> (${c.total_unitats} uds)`;
        }).join(", ");

        const pediKeys = [
            { serie: comanda.pedi_serie, numero: comanda.pedi_numero },
            ...germanes.map(c => ({ serie: c.pedi_serie, numero: c.pedi_numero }))
        ];

        const banner = document.createElement("div");
        banner.id = "agrupar-banner";
        banner.className = "card";
        banner.style.cssText = "border: 2px solid var(--primary); margin-bottom: 1.25rem;";
        banner.innerHTML = `
            <div class="card-body" style="display: flex; align-items: center; gap: 1rem; flex-wrap: wrap;">
                <div style="flex: 1; min-width: 200px;">
                    <strong>Comandes agrupables</strong>
                    <div style="font-size: 0.85rem; color: var(--gray-500); margin-top: 0.25rem;">
                        Mateix client i direcció al mateix dia: ${nums}
                    </div>
                </div>
                <button id="btn-agrupar" class="toolbar-btn toolbar-btn-primary">
                    Calcular ${pediKeys.length} comandes juntes
                </button>
            </div>`;

        // Insertar després del toolbar
        const toolbar = document.querySelector(".result-toolbar");
        toolbar.after(banner);

        document.getElementById("btn-agrupar").addEventListener("click", async () => {
            banner.innerHTML = '<div class="card-body"><span class="mini-spinner"></span> Calculant agrupació...</div>';
            try {
                const resp = await fetch("/api/calcular-agrupat", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ pedi_keys: pediKeys, forcar: true }),
                });
                const data = await resp.json();
                if (!data.ok) {
                    banner.innerHTML = `<div class="card-body" style="color: var(--danger);">${escapeHtml(data.error)}</div>`;
                    return;
                }
                if (data.estat === "NO_CALCULABLE") {
                    const msgs = data.missatges ? data.missatges.join("<br>") : "No calculable";
                    banner.innerHTML = `<div class="card-body" style="color: var(--danger);">
                        <strong>No calculable (agrupat)</strong><br>${msgs}
                    </div>`;
                    return;
                }
                lastResultData = data;
                renderResult(data);
                showState("result");
                // Mostrar banner d'agrupació al resultat
                const agBanner = document.createElement("div");
                agBanner.className = "card";
                agBanner.style.cssText = "border: 2px solid var(--success); margin-bottom: 1.25rem;";
                agBanner.innerHTML = `<div class="card-body" style="color: var(--success);">
                    <strong>Resultat agrupat</strong> — ${pediKeys.length} comandes calculades com una sola
                </div>`;
                const toolbar2 = document.querySelector(".result-toolbar");
                toolbar2.after(agBanner);
            } catch (err) {
                banner.innerHTML = `<div class="card-body" style="color: var(--danger);">Error de connexió</div>`;
            }
        });
    }

    // ==========================================
    // Keyboard shortcuts
    // ==========================================
    const shortcutsModal = document.getElementById("shortcuts-modal");
    document.addEventListener("keydown", (e) => {
        // Ctrl+K: Focus search
        if ((e.ctrlKey || e.metaKey) && e.key === "k") {
            e.preventDefault();
            input.focus();
            input.select();
        }
        // Ctrl+P: Print (only when result visible)
        if ((e.ctrlKey || e.metaKey) && e.key === "p") {
            if (!resultState.classList.contains("hidden")) {
                e.preventDefault();
                window.print();
            }
        }
        // Ctrl+B: Batch mode
        if ((e.ctrlKey || e.metaKey) && e.key === "b") {
            e.preventDefault();
            btnBatch.click();
        }
        // ?: Show shortcuts (only if not in input)
        if (e.key === "?" && document.activeElement.tagName !== "INPUT" && document.activeElement.tagName !== "TEXTAREA") {
            shortcutsModal.classList.toggle("hidden");
        }
    });
});
