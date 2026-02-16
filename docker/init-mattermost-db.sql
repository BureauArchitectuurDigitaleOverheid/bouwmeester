-- Create a separate database and user for Mattermost (runs on first PG init only).
-- The mattermost user only has access to the mattermost database, not bouwmeester.
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'mattermost') THEN
    CREATE ROLE mattermost WITH LOGIN PASSWORD 'mattermost';
  END IF;
END
$$;

SELECT 'CREATE DATABASE mattermost OWNER mattermost'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'mattermost')\gexec

GRANT ALL PRIVILEGES ON DATABASE mattermost TO mattermost;
