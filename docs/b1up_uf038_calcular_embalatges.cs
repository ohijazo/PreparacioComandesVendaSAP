// ============================================================
// B1UP — UF-038 "HTTP Motor Embalatges"
// Classe: Código dinámico (.NET SDK)
// Vinculat a: FB-004 (form 139 Sales Order), línia 3 "Calcular embalatges"
// ============================================================
//
// Fa un POST a l'endpoint Flask /api/afegir-palets/<DocEntry> que
// executa el motor RF1-RF14 i sincronitza les línies palet de la comanda
// via Service Layer. Després refresca el registre i ensenya el resum.
//
// Precondició: la comanda ha d'estar en mode View (fm_OK_MODE), és
// a dir, desada i sense canvis pendents. Si té canvis pendents,
// el MenuID 1304 (refresh) està deshabilitat i el botó falla.
//
// El codi B1UP rep aquests paràmetres al `void DynamicCode(params object[] parameters)`:
//   parameters[0] = SAPbobsCOM.Company        → company
//   parameters[1] = SAPbouiCOM.Application    → application
//   parameters[2] = SAPbouiCOM.Form           → form (el form actiu)
//   parameters[3] = SBO.UI.B1Form             → eventForm
//   parameters[4] = UniversalFunctions.Model.CommonEventObject → eventData
//   parameters[5] = SBO.AddonLogic.AddonData  → addonData
// ============================================================

// 1. Comprovar que la comanda no té canvis pendents
//    (MenuID 1304 "Refresh Record" queda deshabilitat si hi ha canvis pendents)
if (form.Mode != SAPbouiCOM.BoFormMode.fm_OK_MODE)
{
    application.MessageBox(
        "La comanda té canvis pendents. Desa-la abans de calcular els embalatges."
    );
    return;
}

// 2. Obtenir DocEntry via DBDataSource (més estable que Item ID)
string docEntry;

try
{
    docEntry = form.DataSources.DBDataSources
        .Item("ORDR")
        .GetValue("DocEntry", 0)
        .Trim();
}
catch (System.Exception ex)
{
    application.MessageBox(
        "Error obtenint DocEntry: " + ex.Message
    );
    return;
}

if (string.IsNullOrEmpty(docEntry) || docEntry == "0")
{
    application.MessageBox(
        "Cal desar la comanda abans de calcular els embalatges."
    );
    return;
}

// 3. Cridar l'endpoint Flask
try
{
    // Amfitrió de l'app Flask. A producció és el servidor Ubuntu
    // (ae01farwebsrv). Per provar contra una instància local, canvia-ho per
    // "http://localhost:5002". NOMÉS aquesta línia canvia entre entorns.
    var request = (System.Net.HttpWebRequest)
        System.Net.WebRequest.Create(
            "http://192.168.11.244:5002/api/afegir-palets/" + docEntry
        );

    request.Method = "POST";
    request.Timeout = 60000;
    request.ContentLength = 0;

    string body = "";

    using (var response =
        (System.Net.HttpWebResponse)request.GetResponse())
    {
        using (var reader = new System.IO.StreamReader(
            response.GetResponseStream()))
        {
            body = reader.ReadToEnd();
        }
    }

    // 4. Refrescar el registre obert (MenuID 1304 = "Refresh record").
    //    Aquest re-executa la SELECT del form i repinta la graella amb
    //    les línies palet acabades d'inserir per l'endpoint.
    application.ActivateMenuItem("1304");

    // 5. Ensenyar el que ha fet realment el motor.
    //    Sense això el botó sempre deia "recalculat" encara que el motor
    //    avisés (SOTA_MINIM) o no generés cap palet.
    //    Extracció manual de camps: B1UP no carrega System.Text.Json.
    System.Func<string, string, string> jsonVal = delegate(string json, string key)
    {
        int i = json.IndexOf("\"" + key + "\"");
        if (i < 0) { return ""; }
        i = json.IndexOf(':', i);
        if (i < 0) { return ""; }
        i++;
        while (i < json.Length && (json[i] == ' ' || json[i] == '"')) { i++; }
        int start = i;
        while (i < json.Length
               && json[i] != ',' && json[i] != '}'
               && json[i] != '"' && json[i] != ']') { i++; }
        return json.Substring(start, i - start).Trim();
    };

    string estat = jsonVal(body, "estat");
    string palets = jsonVal(body, "total_palets");
    string sacs = jsonVal(body, "total_sacs");
    string avisos = jsonVal(body, "avisos");

    string resum =
        (estat == "" ? "?" : estat)
        + " · " + palets + " palets · " + sacs + " sacs"
        + " · +" + jsonVal(body, "linies_afegides") + " noves"
        + " / ~" + jsonVal(body, "linies_actualitzades") + " actualitzades"
        + " / -" + jsonVal(body, "linies_esborrades") + " tancades";

    // Missatges del motor (array JSON): els mostrem tal qual, sense claudàtors.
    string missatges = "";
    int mIni = body.IndexOf("\"missatges\"");

    if (mIni >= 0)
    {
        int ini = body.IndexOf('[', mIni);
        int fi = (ini >= 0 ? body.IndexOf(']', ini) : -1);

        if (ini >= 0 && fi > ini)
        {
            missatges = body.Substring(ini + 1, fi - ini - 1)
                .Replace("\",\"", "\n")
                .Replace("\"", "")
                .Trim();
        }
    }

    bool teAvis = (estat != "CALCULAT") || (avisos != "" && avisos != "0")
                  || (palets == "0");

    if (teAvis)
    {
        application.MessageBox(
            resum + (missatges == "" ? "" : "\n\n" + missatges)
        );
    }
    else
    {
        application.StatusBar.SetText(
            resum,
            SAPbouiCOM.BoMessageTime.bmt_Short,
            SAPbouiCOM.BoStatusBarMessageType.smt_Success
        );
    }
}
catch (System.Net.WebException wex)
{
    string errBody = "";

    if (wex.Response != null)
    {
        using (var reader = new System.IO.StreamReader(
            wex.Response.GetResponseStream()))
        {
            errBody = reader.ReadToEnd();
        }
    }

    application.MessageBox(
        "Error HTTP: " + wex.Message + "\n" + errBody
    );
}
catch (System.Exception ex)
{
    application.MessageBox(
        "Error inesperat: " + ex.Message
    );
}
