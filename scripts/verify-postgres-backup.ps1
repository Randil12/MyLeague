param(
    [Parameter(Mandatory = $true)]
    [string]$EncryptedBackup,
    [Parameter(Mandatory = $true)]
    [string]$AgeIdentity
)

$ErrorActionPreference = "Stop"
$ContainerName = "myleague-gold-postgres"
$BackupPath = (Resolve-Path -LiteralPath $EncryptedBackup).Path
$IdentityPath = (Resolve-Path -LiteralPath $AgeIdentity).Path
$Timestamp = Get-Date -Format "yyyyMMddHHmmss"
$RestoreDatabase = "gold_restore_$Timestamp"
$PlainPath = Join-Path ([System.IO.Path]::GetTempPath()) "myleague-$Timestamp.dump"
$ContainerDump = "/tmp/myleague-$Timestamp.dump"

if (-not (Get-Command age -ErrorAction SilentlyContinue)) {
    throw "La commande 'age' est obligatoire pour déchiffrer la sauvegarde."
}

try {
    age --decrypt --identity $IdentityPath --output $PlainPath $BackupPath
    if ($LASTEXITCODE -ne 0) { throw "Déchiffrement impossible." }

    docker cp $PlainPath "${ContainerName}:${ContainerDump}"
    if ($LASTEXITCODE -ne 0) { throw "docker cp a échoué." }

    docker exec $ContainerName createdb -U gold $RestoreDatabase
    if ($LASTEXITCODE -ne 0) { throw "Création de la base isolée impossible." }

    docker exec $ContainerName pg_restore -U gold -d $RestoreDatabase --exit-on-error $ContainerDump
    if ($LASTEXITCODE -ne 0) { throw "Restauration impossible." }

    docker exec $ContainerName psql -U gold -d $RestoreDatabase -c "SELECT schemaname, count(*) AS tables FROM pg_tables WHERE schemaname IN ('raw','reference','staging','intermediate','gold','audit') GROUP BY 1 ORDER BY 1;"
    Write-Output "Restauration vérifiée dans la base isolée : $RestoreDatabase"
    Write-Output "La base est conservée pour inspection ; sa suppression doit être explicitement décidée."
}
finally {
    if (Test-Path -LiteralPath $PlainPath) {
        Remove-Item -LiteralPath $PlainPath -Force
    }
    docker exec $ContainerName rm -f $ContainerDump 2>$null
}

