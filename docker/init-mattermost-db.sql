-- Create a separate database for Mattermost (runs on first PG init only).
SELECT 'CREATE DATABASE mattermost'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'mattermost')\gexec
