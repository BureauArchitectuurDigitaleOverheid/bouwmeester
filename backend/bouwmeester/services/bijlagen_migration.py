"""Copy the bijlagen from the old volume into object storage, and check the result.

Runs from ``entrypoint.sh`` before uvicorn starts, as long as the volume is
still mounted:

    python -m bouwmeester.services.bijlagen_migration

It is safe to run on every start. An object that is already in the bucket
with the same size is left alone, so after the first run it only reads the
directory listing. A failure is logged but never stops the app from starting:
the read fallback in ``core/blob_store.py`` still serves anything that did not
make it across.

After copying it checks every file the database refers to against the bucket.
That count, not the copy count, is what decides whether the volume can go:
``GET /api/admin/bijlagen/opslag`` returns the same check on demand.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.blob_store import BlobStore, InvalidKeyError

logger = logging.getLogger(__name__)

# Left behind by entrypoint.sh's write check; not a bijlage.
_SKIP_PREFIX = ".write_test_"

# How many missing keys a report names; the count is always complete.
_MAX_LISTED = 20


@dataclass
class CopyReport:
    copied: int = 0
    already_present: int = 0
    failed: list[str] = field(default_factory=list)


@dataclass
class TableCheck:
    """One attachment table against the bucket.

    ``only_on_volume`` is the number that blocks removing the volume: files
    the bucket lacks but the volume still has. ``missing`` are gone from both,
    so removing the volume does not lose them; they were lost already.
    """

    table: str
    total: int = 0
    present: int = 0
    only_on_volume: int = 0
    missing_count: int = 0
    missing: list[str] = field(default_factory=list)


async def copy_directory_to_store(root: Path, store: BlobStore) -> CopyReport:
    """Put every file under *root* into *store*, keyed by its path below *root*."""
    report = CopyReport()
    if not root.is_dir():
        return report

    files = await asyncio.to_thread(
        lambda: sorted(p for p in root.rglob("*") if p.is_file())
    )
    for path in files:
        if path.name.startswith(_SKIP_PREFIX):
            continue
        key = path.relative_to(root).as_posix()
        try:
            local_size = path.stat().st_size
            if await store.size(key) == local_size:
                report.already_present += 1
                continue
            data = await asyncio.to_thread(path.read_bytes)
            await store.put(key, data)
            report.copied += 1
        except Exception:
            logger.exception("Kopiëren van bijlage %s mislukt", key)
            report.failed.append(key)
    return report


async def check_database_against_store(
    session: AsyncSession, store: BlobStore, volume: BlobStore | None = None
) -> list[TableCheck]:
    """For each attachment table, how many of its files *store* actually has.

    With *volume*, a file the store lacks is looked up there too, to tell a
    file that still has to be copied from one that is gone everywhere.
    """
    from bouwmeester.core.storage import chat_key
    from bouwmeester.models.bron_bijlage import BronBijlage
    from bouwmeester.models.chat_attachment import ChatAttachment
    from bouwmeester.models.lead_attachment import LeadAttachment

    sources = [
        ("bron_bijlage", select(BronBijlage.pad), lambda pad: pad),
        ("chat_attachment", select(ChatAttachment.pad), chat_key),
        (
            "lead_attachment",
            select(LeadAttachment.pad).where(LeadAttachment.pad.is_not(None)),
            lambda pad: pad,
        ),
    ]
    checks: list[TableCheck] = []
    for table, stmt, to_key in sources:
        check = TableCheck(table=table)
        for pad in (await session.execute(stmt)).scalars():
            check.total += 1
            key = to_key(pad)
            try:
                found = await store.size(key) is not None
                on_volume = (
                    not found
                    and volume is not None
                    and await volume.size(key) is not None
                )
            except InvalidKeyError:
                found = on_volume = False
            if found:
                check.present += 1
            elif on_volume:
                check.only_on_volume += 1
            else:
                check.missing_count += 1
                if len(check.missing) < _MAX_LISTED:
                    check.missing.append(key)
        checks.append(check)
    return checks


def _ensure_bucket(client, bucket: str) -> None:
    """Create *bucket* when it does not exist yet. ZAD normally provides it."""
    from botocore.exceptions import ClientError

    try:
        client.head_bucket(Bucket=bucket)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code not in ("404", "NoSuchBucket", "NotFound"):
            raise
        client.create_bucket(Bucket=bucket)
        logger.info("Bucket %s aangemaakt", bucket)


async def main() -> int:
    from bouwmeester.core.blob_store import (
        LocalBlobStore,
        S3BlobStore,
        s3_client_from_settings,
    )
    from bouwmeester.core.config import get_settings
    from bouwmeester.core.database import async_session
    from bouwmeester.core.storage import bijlagen_root

    logging.basicConfig(level=logging.INFO, format="[bijlagen] %(message)s")

    client = s3_client_from_settings()
    if client is None:
        logger.info("Geen objectopslag ingesteld; bijlagen blijven lokaal.")
        return 0

    bucket = get_settings().OBJECT_STORE_BUCKET_NAME
    try:
        await asyncio.to_thread(_ensure_bucket, client, bucket)
        store = S3BlobStore(client, bucket)

        root = bijlagen_root()
        report = await copy_directory_to_store(root, store)
        logger.info(
            "Kopie van %s naar bucket %s: %d gekopieerd, %d stond er al, %d mislukt",
            root,
            bucket,
            report.copied,
            report.already_present,
            len(report.failed),
        )

        async with async_session() as session:
            checks = await check_database_against_store(
                session, store, LocalBlobStore(root)
            )
        for check in checks:
            logger.info(
                "Controle %s: %d van %d in de bucket, %d alleen op het volume, "
                "%d nergens%s",
                check.table,
                check.present,
                check.total,
                check.only_on_volume,
                check.missing_count,
                f" (o.a. {check.missing})" if check.missing else "",
            )
    except Exception:
        # Never block the start: the read fallback still serves the volume.
        logger.exception("Kopie naar objectopslag mislukt; de app start toch")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
