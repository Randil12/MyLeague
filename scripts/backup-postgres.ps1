param(
    [Parameter(Mandatory = $true)]
    [string]$AgeRecipient,
    [string]$BackupDirectory = (Join-Path $PSScriptRoot "..\backups")
)

$ErrorActionPreference = "Stop"
$ContainerName = "myleague-gold-postgres"
$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$BackupRoot = [System.IO.Path]::GetFullPath($BackupDirectory)
$PlainPath = Join-Path $BackupRoot "gold-$Timestamp.dump"
$EncryptedPath = "$PlainPath.age"
$ContainerDump = "/tmp/gold-$Timestamp.dump"

if (-not (Get-Command age -ErrorAction SilentlyContinue)) {
    throw "La commande 'age' est obligatoire : aucune sauvegarde en clair ne sera conservée."
}
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker est introuvable."
}

New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null

try {
    docker exec $ContainerName pg_dump -U gold -d gold -Fc -f $ContainerDump
    if ($LASTEXITCODE -ne 0) { throw "pg_dump a échoué." }

    docker cp "${ContainerName}:${ContainerDump}" $PlainPath
    if ($LASTEXITCODE -ne 0) { throw "docker cp a échoué." }

    age --recipient $AgeRecipient --output $EncryptedPath $PlainPath
    if ($LASTEXITCODE -ne 0) { throw "Le chiffrement age a échoué." }

    $Hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $EncryptedPath).Hash
    Set-Content -Encoding ASCII -LiteralPath "$EncryptedPath.sha256" -Value "$Hash  $([IO.Path]::GetFileName($EncryptedPath))"
    Write-Output "Sauvegarde chiffrée créée : $EncryptedPath"
}
finally {
    if (Test-Path -LiteralPath $PlainPath) {
        Remove-Item -LiteralPath $PlainPath -Force
    }
    docker exec $ContainerName rm -f $ContainerDump 2>$null
}

