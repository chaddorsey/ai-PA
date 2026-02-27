#!/bin/bash
# Create litellm database and role in Supabase PostgreSQL
# Run once before starting the litellm service

set -e

LITELLM_DB_PASSWORD="${LITELLM_DB_PASSWORD:-litellm_secret}"

echo "Creating litellm role and database in supabase-db..."

docker exec supabase-db psql -U postgres -c "
  DO \$\$
  BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'litellm') THEN
      CREATE ROLE litellm WITH LOGIN PASSWORD '${LITELLM_DB_PASSWORD}';
      GRANT litellm TO postgres;
      RAISE NOTICE 'Created role litellm';
    ELSE
      RAISE NOTICE 'Role litellm already exists';
    END IF;
  END \$\$;
"

# CREATE DATABASE fails if it already exists; check first
if docker exec supabase-db psql -U postgres -tc "SELECT 1 FROM pg_database WHERE datname = 'litellm'" | grep -q 1; then
  echo "Database litellm already exists"
else
  docker exec supabase-db psql -U postgres -c "CREATE DATABASE litellm OWNER litellm;"
  echo "Created database litellm"
fi

echo "Done."
