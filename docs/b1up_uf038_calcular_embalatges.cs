// ============================================================
// B1UP — UF-038 "HTTP Motor Embalatges"
// Classe: Código dinámico (.NET SDK)
// Vinculat a: FB-004 (form 139 Sales Order), línia 3 "Calcular embalatges"
// ============================================================
//
// Fa un POST a l'endpoint Flask /api/afegir-palets/<DocEntry> que
// executa el motor RF1-RF14 i afegeix les línies palet a la comanda
// via Service Layer. Després refresca automàticament el registre.
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
    var request = (System.Net.HttpWebRequest)
        System.Net.WebRequest.Create(
            "http://localhost:5002/api/afegir-palets/" + docEntry
        );

    request.Method = "POST";
    request.Timeout = 60000;
    request.ContentLength = 0;

    using (var response =
        (System.Net.HttpWebResponse)request.GetResponse())
    {
        // La resposta s'ha tancat i l'API ja ha acabat.
    }

    // 4. Refrescar el registre obert (MenuID 1304 = "Refresh record").
    //    Aquest re-executa la SELECT del form i repinta la graella amb
    //    les línies palet acabades d'inserir per l'endpoint.
    application.ActivateMenuItem("1304");

    application.StatusBar.SetText(
        "Embalatges recalculats i comanda actualitzada.",
        SAPbouiCOM.BoMessageTime.bmt_Short,
        SAPbouiCOM.BoStatusBarMessageType.smt_Success
    );
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
