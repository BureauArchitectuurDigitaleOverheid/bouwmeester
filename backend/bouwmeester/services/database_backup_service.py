"""Service for full database export (pg_dump) and import (pg_restore).

Export format: tar.gz (optionally age-encrypted → .tar.gz.age) containing:
  - metadata.json  (format version, alembic revision, timestamp, excluded tables)
  - data.dump      (pg_dump custom format, data-only)
"""

from __future__ import annotations

import io
import json
import logging
import os
import subprocess
import tarfile
import tempfile
from datetime import UTC, datetime
from urllib.parse import unquote, urlparse

from bouwmeester.core.config import get_settings
from bouwmeester.schema.database_backup import (
    DatabaseBackupInfo,
    DatabaseRestoreResult,
)

logger = logging.getLogger(__name__)

FORMAT_VERSION = 1
EXCLUDED_TABLES = ["http_sessions", "alembic_version"]


def _parse_db_url() -> dict[str, str]:
    """Extract host/port/user/password/dbname from the async DATABASE_URL."""
    url = get_settings().DATABASE_URL
    # Strip the asyncpg driver so urlparse handles it cleanly
    url = url.replace("postgresql+asyncpg://", "postgresql://", 1)
    parsed = urlparse(url)
    return {
        "host": parsed.hostname or "localhost",
        "port": str(parsed.port or 5432),
        "user": unquote(parsed.username or "bouwmeester"),
        "password": unquote(parsed.password or ""),
        "dbname": (parsed.path or "/bouwmeester").lstrip("/"),
    }


def _pg_env(db: dict[str, str]) -> dict[str, str]:
    """Return env dict with PGPASSWORD set for pg_dump / pg_restore."""
    env = os.environ.copy()
    env["PGPASSWORD"] = db["password"]
    return env


def _get_alembic_revision() -> str:
    """Query the current alembic revision via pg_dump-friendly psql or direct."""
    db = _parse_db_url()
    result = subprocess.run(
        [
            "psql",
            "-h",
            db["host"],
            "-p",
            db["port"],
            "-U",
            db["user"],
            "-d",
            db["dbname"],
            "-t",
            "-A",
            "-c",
            "SELECT version_num FROM alembic_version LIMIT 1",
        ],
        capture_output=True,
        text=True,
        env=_pg_env(db),
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to query alembic_version: {result.stderr.strip()}")
    return result.stdout.strip()


def _read_age_recipients() -> list[str]:
    """Read age public keys from age-recipients.txt.

    Searches in the backend root (/app in Docker) first, then the repo root
    (one level above backend/ for local development).
    """
    backend_dir = _get_backend_dir()
    candidates = [
        os.path.join(backend_dir, "age-recipients.txt"),
        os.path.join(backend_dir, "..", "age-recipients.txt"),
    ]
    for path in candidates:
        if os.path.exists(path):
            keys: list[str] = []
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        keys.append(line)
            return keys
    return []


def _age_encrypt(data: bytes) -> bytes:
    """Encrypt with age using recipients from age-recipients.txt.

    Only encrypts when AGE_SECRET_KEY is set (i.e. on production).
    Returns data as-is otherwise.
    """
    if not os.environ.get("AGE_SECRET_KEY", ""):
        return data
    keys = _read_age_recipients()
    if not keys:
        return data
    try:
        from pyrage import encrypt, x25519

        recipients = [x25519.Recipient.from_str(k) for k in keys]
        return encrypt(data, recipients)
    except Exception:
        logger.exception("Age encryption failed, returning unencrypted data")
        return data


def _age_decrypt(data: bytes) -> tuple[bytes, bool]:
    """Try to age-decrypt data. Returns (decrypted_data, was_encrypted).

    Falls back to returning the original data if decryption fails or no key is
    configured, assuming the file is plaintext.
    """
    secret_key = os.environ.get("AGE_SECRET_KEY", "")
    if not secret_key:
        return data, False
    try:
        from pyrage import decrypt, x25519

        identity = x25519.Identity.from_str(secret_key)
        decrypted = decrypt(data, [identity])
        return decrypted, True
    except Exception:
        # Not encrypted or wrong key — treat as plaintext
        return data, False


def export_database() -> tuple[bytes, str]:
    """Create a full database export.

    Returns (file_bytes, filename).
    """
    db = _parse_db_url()
    env = _pg_env(db)

    # 1. Get current alembic revision
    revision = _get_alembic_revision()

    # 2. Build pg_dump exclude args
    exclude_args: list[str] = []
    for table in EXCLUDED_TABLES:
        exclude_args.extend(["--exclude-table", table])

    # 3. Run pg_dump
    dump_result = subprocess.run(
        [
            "pg_dump",
            "-h",
            db["host"],
            "-p",
            db["port"],
            "-U",
            db["user"],
            "-d",
            db["dbname"],
            "-Fc",
            "--no-owner",
            "--no-privileges",
            "--data-only",
            *exclude_args,
        ],
        capture_output=True,
        env=env,
        timeout=300,
    )
    if dump_result.returncode != 0:
        raise RuntimeError(f"pg_dump failed: {dump_result.stderr.decode().strip()}")

    # 4. Build metadata
    metadata = {
        "format_version": FORMAT_VERSION,
        "app_name": "bouwmeester",
        "exported_at": datetime.now(UTC).isoformat(),
        "alembic_revision": revision,
        "excluded_tables": EXCLUDED_TABLES,
    }

    # 5. Create tarball in memory
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        # metadata.json
        meta_bytes = json.dumps(metadata, indent=2).encode()
        meta_info = tarfile.TarInfo(name="metadata.json")
        meta_info.size = len(meta_bytes)
        tar.addfile(meta_info, io.BytesIO(meta_bytes))

        # data.dump
        dump_info = tarfile.TarInfo(name="data.dump")
        dump_info.size = len(dump_result.stdout)
        tar.addfile(dump_info, io.BytesIO(dump_result.stdout))

    raw = buf.getvalue()

    # 6. Encrypt if configured
    encrypted = _age_encrypt(raw)
    is_encrypted = encrypted is not raw

    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    ext = ".tar.gz.age" if is_encrypted else ".tar.gz"
    filename = f"bouwmeester-backup-{timestamp}{ext}"

    return encrypted, filename


def get_backup_info(file_bytes: bytes) -> DatabaseBackupInfo:
    """Read metadata from an uploaded backup file without restoring."""
    data, was_encrypted = _age_decrypt(file_bytes)

    try:
        buf = io.BytesIO(data)
        with tarfile.open(fileobj=buf, mode="r:gz") as tar:
            meta_member = tar.getmember("metadata.json")
            f = tar.extractfile(meta_member)
            if f is None:
                raise ValueError("metadata.json is empty")
            metadata = json.loads(f.read())
    except (tarfile.TarError, KeyError) as e:
        raise ValueError(f"Ongeldig backup-bestand: {e}") from e

    return DatabaseBackupInfo(
        exported_at=metadata["exported_at"],
        alembic_revision=metadata["alembic_revision"],
        format_version=metadata["format_version"],
        encrypted=was_encrypted,
    )


def import_database(file_bytes: bytes) -> DatabaseRestoreResult:
    """Restore a database from an uploaded backup file.

    Steps:
    1. Decrypt if needed
    2. Extract tarball, validate metadata
    3. Compare alembic revisions
    4. Truncate app tables
    5. pg_restore data
    6. Set alembic_version
    7. Run migrations to head if needed
    """
    db = _parse_db_url()
    env = _pg_env(db)

    # 1. Decrypt
    data, _was_encrypted = _age_decrypt(file_bytes)

    # 2. Extract
    try:
        buf = io.BytesIO(data)
        with tarfile.open(fileobj=buf, mode="r:gz") as tar:
            meta_f = tar.extractfile("metadata.json")
            if meta_f is None:
                raise ValueError("metadata.json is empty")
            metadata = json.loads(meta_f.read())

            dump_f = tar.extractfile("data.dump")
            if dump_f is None:
                raise ValueError("data.dump is empty")
            dump_data = dump_f.read()
    except (tarfile.TarError, KeyError) as e:
        raise ValueError(f"Ongeldig backup-bestand: {e}") from e

    # 3. Validate
    if metadata.get("format_version") != FORMAT_VERSION:
        raise ValueError(
            f"Onbekend format_version: {metadata.get('format_version')} "
            f"(verwacht: {FORMAT_VERSION})"
        )

    export_revision = metadata["alembic_revision"]
    current_revision = _get_alembic_revision()

    # Check if the export revision exists in the migration chain
    check = subprocess.run(
        ["alembic", "history", "-r", f"{export_revision}:"],
        capture_output=True,
        text=True,
        cwd=_get_backend_dir(),
        env=env,
        timeout=30,
    )
    if check.returncode != 0 and "Can't locate revision" in check.stderr:
        raise ValueError(
            f"Onbekende migratieversie in backup: {export_revision}. "
            "Update eerst de applicatie."
        )

    # If export is newer than current, refuse
    if export_revision != current_revision:
        newer_check = subprocess.run(
            ["alembic", "history", "-r", f"{current_revision}:{export_revision}"],
            capture_output=True,
            text=True,
            cwd=_get_backend_dir(),
            env=env,
            timeout=30,
        )
        if newer_check.returncode == 0 and export_revision in newer_check.stdout:
            # export_revision is ahead of current
            raise ValueError(
                f"Backup is van een nieuwere versie ({export_revision}) "
                f"dan de huidige applicatie ({current_revision}). "
                "Update eerst de applicatie."
            )

    # 4. Write dump to temp file for pg_restore
    with tempfile.NamedTemporaryFile(suffix=".dump", delete=False) as tmp:
        tmp.write(dump_data)
        tmp_path = tmp.name

    try:
        # 5. Truncate all app tables (excluding EXCLUDED_TABLES)
        # Get list of tables from pg_restore --list
        list_result = subprocess.run(
            ["pg_restore", "--list", tmp_path],
            capture_output=True,
            text=True,
            env=env,
            timeout=60,
        )
        # Parse table names from the TOC
        tables_in_dump: set[str] = set()
        for line in list_result.stdout.splitlines():
            line = line.strip()
            if line.startswith(";") or not line:
                continue
            # Format: "id; seq tablespace owner TABLE DATA tablename owner"
            parts = line.split()
            if "TABLE DATA" in line and len(parts) >= 6:
                # Find TABLE DATA and the next word is the table name
                for i, part in enumerate(parts):
                    if (
                        part == "TABLE"
                        and i + 1 < len(parts)
                        and parts[i + 1] == "DATA"
                    ):
                        if i + 2 < len(parts):
                            tables_in_dump.add(parts[i + 2])
                        break

        # Truncate tables (CASCADE handles FK ordering)
        if tables_in_dump:
            table_list = ", ".join(sorted(tables_in_dump))
            truncate_sql = f"TRUNCATE {table_list} CASCADE"
            subprocess.run(
                [
                    "psql",
                    "-h",
                    db["host"],
                    "-p",
                    db["port"],
                    "-U",
                    db["user"],
                    "-d",
                    db["dbname"],
                    "-c",
                    truncate_sql,
                ],
                capture_output=True,
                text=True,
                env=env,
                timeout=60,
            )

        # 6. pg_restore
        restore_result = subprocess.run(
            [
                "pg_restore",
                "-h",
                db["host"],
                "-p",
                db["port"],
                "-U",
                db["user"],
                "-d",
                db["dbname"],
                "--data-only",
                "--disable-triggers",
                "--no-owner",
                "--no-privileges",
                tmp_path,
            ],
            capture_output=True,
            text=True,
            env=env,
            timeout=300,
        )
        if restore_result.returncode != 0:
            # pg_restore returns non-zero for warnings too; only fail on real errors
            stderr = restore_result.stderr.strip()
            if stderr and "error" in stderr.lower():
                raise RuntimeError(f"pg_restore mislukt: {stderr}")

        tables_restored = len(tables_in_dump)

        # 7. Set alembic_version to the export's revision
        subprocess.run(
            [
                "psql",
                "-h",
                db["host"],
                "-p",
                db["port"],
                "-U",
                db["user"],
                "-d",
                db["dbname"],
                "-c",
                "DELETE FROM alembic_version;"
                " INSERT INTO alembic_version (version_num)"
                f" VALUES ('{export_revision}')",
            ],
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )

        # 8. Migrate to head if needed
        migrations_applied = 0
        if export_revision != current_revision:
            migrate_result = subprocess.run(
                ["alembic", "upgrade", "head"],
                capture_output=True,
                text=True,
                cwd=_get_backend_dir(),
                env=env,
                timeout=120,
            )
            if migrate_result.returncode != 0:
                raise RuntimeError(
                    f"Alembic migratie mislukt: {migrate_result.stderr.strip()}"
                )
            # Count applied migrations
            for line in migrate_result.stdout.splitlines():
                if "Running upgrade" in line:
                    migrations_applied += 1

        final_revision = _get_alembic_revision()

        return DatabaseRestoreResult(
            success=True,
            tables_restored=tables_restored,
            alembic_revision_from=export_revision,
            alembic_revision_to=final_revision,
            migrations_applied=migrations_applied,
            message=f"Database hersteld: {tables_restored} tabellen, "
            f"migratieversie {final_revision}"
            + (
                f" ({migrations_applied} migraties toegepast)"
                if migrations_applied
                else ""
            ),
        )
    finally:
        os.unlink(tmp_path)


def _get_backend_dir() -> str:
    """Return the backend directory (where alembic.ini lives)."""
    return str(
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    )
