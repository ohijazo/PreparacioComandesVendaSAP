<#
.SYNOPSIS
    Instal·la, actualitza o desinstal·la el worker de sync SAP com a servei
    Windows amb NSSM (Non-Sucking Service Manager).

.DESCRIPTION
    El worker (`run_sync.py`) ha de córrer contínuament al host on ja hi ha
    la variant SAP de l'aplicació. Aquest script el registra com a servei
    Windows perquè arrenqui automàticament, es reinicii en cas d'error, i
    rote els logs.

.PARAMETER Install
    Instal·la el servei (per defecte si no es passa cap acció).

.PARAMETER Uninstall
    Atura i desinstal·la el servei.

.PARAMETER ServiceName
    Nom del servei Windows. Per defecte 'MotorComandesSyncSAP'.

.PARAMETER ProjectPath
    Ruta al projecte SAP. Per defecte, el directori pare d'aquest script.

.PARAMETER PythonExe
    Ruta a l'executable python. Per defecte '<ProjectPath>\venv\Scripts\python.exe'.

.PARAMETER NssmPath
    Ruta a nssm.exe. Per defecte s'agafa del PATH.

.EXAMPLE
    .\install_sync_service.ps1
    .\install_sync_service.ps1 -Install
    .\install_sync_service.ps1 -Uninstall
    .\install_sync_service.ps1 -ServiceName MotorSyncTest -Install

.NOTES
    Requereix executar com a Administrador (crear servei Windows).
    NSSM disponible a https://nssm.cc/download
#>
param(
    [switch]$Install,
    [switch]$Uninstall,
    [string]$ServiceName = 'MotorComandesSyncSAP',
    [string]$ProjectPath = (Split-Path -Parent $PSScriptRoot),
    [string]$PythonExe,
    [string]$NssmPath
)

$ErrorActionPreference = 'Stop'

# ------------------------------------------------------------------
# Validacions
# ------------------------------------------------------------------
function Assert-Admin {
    $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($currentUser)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "Cal executar aquest script com a Administrador (per crear serveis Windows)."
    }
}

function Get-NssmPath {
    param([string]$Override)
    if ($Override -and (Test-Path $Override)) { return $Override }
    $cmd = Get-Command nssm -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    throw "nssm.exe no trobat al PATH. Instal·la NSSM des de https://nssm.cc/download o passa -NssmPath."
}

function Resolve-PythonExe {
    param([string]$Override, [string]$Project)
    if ($Override) {
        if (-not (Test-Path $Override)) { throw "PythonExe no existeix: $Override" }
        return $Override
    }
    $venvPython = Join-Path $Project 'venv\Scripts\python.exe'
    if (Test-Path $venvPython) { return $venvPython }
    Write-Warning "venv\Scripts\python.exe no trobat a $Project. Usarem el python del PATH."
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $cmd) { throw "python no trobat al PATH." }
    return $cmd.Source
}

# ------------------------------------------------------------------
# Uninstall
# ------------------------------------------------------------------
function Uninstall-Service {
    Assert-Admin
    $nssm = Get-NssmPath -Override $NssmPath
    Write-Host "Aturant $ServiceName..."
    & $nssm stop $ServiceName confirm 2>&1 | Out-Host
    Write-Host "Desinstal·lant $ServiceName..."
    & $nssm remove $ServiceName confirm 2>&1 | Out-Host
    Write-Host "Servei $ServiceName desinstal·lat."
}

# ------------------------------------------------------------------
# Install
# ------------------------------------------------------------------
function Install-Service {
    Assert-Admin
    $nssm = Get-NssmPath -Override $NssmPath
    $python = Resolve-PythonExe -Override $PythonExe -Project $ProjectPath
    $runSync = Join-Path $ProjectPath 'run_sync.py'
    if (-not (Test-Path $runSync)) {
        throw "run_sync.py no trobat a $ProjectPath"
    }

    $logsDir = Join-Path $ProjectPath 'logs'
    if (-not (Test-Path $logsDir)) {
        New-Item -ItemType Directory -Path $logsDir | Out-Null
        Write-Host "Creat directori de logs: $logsDir"
    }
    $logOut = Join-Path $logsDir 'sync_worker.log'
    $logErr = Join-Path $logsDir 'sync_worker.err.log'

    # Si ja existeix, aturar i eliminar per re-instal·lar net
    $existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Warning "Servei $ServiceName ja existeix — el desinstal·lem primer."
        & $nssm stop $ServiceName confirm 2>&1 | Out-Host
        & $nssm remove $ServiceName confirm 2>&1 | Out-Host
    }

    Write-Host "Registrant servei $ServiceName..."
    & $nssm install $ServiceName $python $runSync 2>&1 | Out-Host
    & $nssm set $ServiceName AppDirectory $ProjectPath 2>&1 | Out-Host
    & $nssm set $ServiceName DisplayName "Motor Comandes — Sync SAP" 2>&1 | Out-Host
    & $nssm set $ServiceName Description "Worker Python que polleja comandes marcades a SAP i escriu el resum via Service Layer." 2>&1 | Out-Host
    & $nssm set $ServiceName Start SERVICE_AUTO_START 2>&1 | Out-Host

    # Logs amb rotació (5 MB × 5 fitxers)
    & $nssm set $ServiceName AppStdout $logOut 2>&1 | Out-Host
    & $nssm set $ServiceName AppStderr $logErr 2>&1 | Out-Host
    & $nssm set $ServiceName AppRotateFiles 1 2>&1 | Out-Host
    & $nssm set $ServiceName AppRotateOnline 1 2>&1 | Out-Host
    & $nssm set $ServiceName AppRotateBytes 5242880 2>&1 | Out-Host  # 5 MB

    # Restart on failure amb throttle mínim 10s
    & $nssm set $ServiceName AppExit Default Restart 2>&1 | Out-Host
    & $nssm set $ServiceName AppRestartDelay 10000 2>&1 | Out-Host
    & $nssm set $ServiceName AppThrottle 10000 2>&1 | Out-Host

    # Arrencar
    Write-Host "Arrencant $ServiceName..."
    & $nssm start $ServiceName 2>&1 | Out-Host

    Start-Sleep -Seconds 2
    $svc = Get-Service -Name $ServiceName
    Write-Host ""
    Write-Host "Estat: $($svc.Status)"
    Write-Host "Logs a: $logOut"
    Write-Host ""
    Write-Host "Comandes útils:"
    Write-Host "  Get-Service $ServiceName            # veure estat"
    Write-Host "  Get-Content $logOut -Tail 20 -Wait  # veure logs en directe"
    Write-Host "  nssm stop $ServiceName              # aturar"
    Write-Host "  nssm start $ServiceName             # arrencar"
    Write-Host "  nssm restart $ServiceName           # reiniciar"
    Write-Host "  .\install_sync_service.ps1 -Uninstall  # desinstal·lar"
}

# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------
if ($Uninstall) {
    Uninstall-Service
} else {
    # per defecte, Install
    Install-Service
}
