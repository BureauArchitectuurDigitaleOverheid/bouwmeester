"""Repository voor GitHubLink."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.github_link import GitHubLink


class GitHubLinkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, link_id: UUID) -> GitHubLink | None:
        stmt = select(GitHubLink).where(GitHubLink.id == link_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_scope_url(
        self, scope_type: str, scope_id: UUID, url: str
    ) -> GitHubLink | None:
        stmt = select(GitHubLink).where(
            GitHubLink.scope_type == scope_type,
            GitHubLink.scope_id == scope_id,
            GitHubLink.url == url,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_scope(self, scope_type: str, scope_id: UUID) -> list[GitHubLink]:
        stmt = (
            select(GitHubLink)
            .where(
                GitHubLink.scope_type == scope_type,
                GitHubLink.scope_id == scope_id,
            )
            .order_by(GitHubLink.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(
        self,
        *,
        scope_type: str,
        scope_id: UUID,
        url: str,
        link_type: str,
        owner: str,
        repo: str,
        ref: str | None,
        title: str | None,
        created_by_id: UUID | None,
    ) -> GitHubLink:
        link = GitHubLink(
            scope_type=scope_type,
            scope_id=scope_id,
            url=url,
            link_type=link_type,
            owner=owner,
            repo=repo,
            ref=ref,
            title=title,
            created_by_id=created_by_id,
        )
        self.session.add(link)
        await self.session.flush()
        await self.session.refresh(link)
        return link

    async def update_title(self, link: GitHubLink, title: str | None) -> GitHubLink:
        link.title = title
        await self.session.flush()
        await self.session.refresh(link)
        return link

    async def delete(self, link: GitHubLink) -> None:
        await self.session.delete(link)
        await self.session.flush()
