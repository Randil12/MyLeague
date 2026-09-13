-- Rôles applicatifs : principe du moindre privilège (C1.4.1).
-- Exécuté par pgsql-init avec les mots de passe passés en variables psql :
--   psql -v data_engineer_password=... -v data_analyst_password=... -f init_roles.sql

-- Création idempotente des rôles
SELECT 'CREATE ROLE data_engineer LOGIN'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'data_engineer')\gexec

SELECT 'CREATE ROLE data_analyst LOGIN'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'data_analyst')\gexec

-- Mots de passe (mis à jour à chaque démarrage depuis le .env)
ALTER ROLE data_engineer WITH LOGIN PASSWORD :'data_engineer_password';
ALTER ROLE data_analyst WITH LOGIN PASSWORD :'data_analyst_password';

SELECT format('GRANT CONNECT ON DATABASE %I TO data_engineer, data_analyst', current_database())\gexec

-- ============================================================
-- data_engineer : accès complet aux schémas data
-- ============================================================
GRANT USAGE, CREATE ON SCHEMA raw, reference, staging, intermediate, gold, audit TO data_engineer;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA raw, reference, staging, intermediate, gold, audit TO data_engineer;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA raw, reference, staging, intermediate, gold, audit TO data_engineer;

-- Les objets créés à l'avenir par le compte technique 'gold' (pipelines, dbt)
-- seront automatiquement accessibles au data engineer
ALTER DEFAULT PRIVILEGES IN SCHEMA raw, reference, staging, intermediate, gold, audit
    GRANT ALL PRIVILEGES ON TABLES TO data_engineer;

-- ============================================================
-- data_analyst : lecture seule sur les zones de consommation
-- (gold = analytique, reference = dimensions, audit = supervision)
-- Aucun accès à raw/staging/intermediate.
-- ============================================================
GRANT USAGE ON SCHEMA gold, reference, audit TO data_analyst;
GRANT SELECT ON ALL TABLES IN SCHEMA gold, reference, audit TO data_analyst;

ALTER DEFAULT PRIVILEGES IN SCHEMA gold, reference, audit
    GRANT SELECT ON TABLES TO data_analyst;
