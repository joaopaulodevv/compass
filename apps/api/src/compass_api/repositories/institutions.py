"""Reads and writes for `financial_institutions`."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from compass_api.db.models import FinancialInstitution
from compass_api.domain.open_finance import InstitutionSnapshot


class InstitutionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_many(
        self, provider: str, snapshots: Sequence[InstitutionSnapshot]
    ) -> dict[str, uuid.UUID]:
        """Insert or refresh institutions, returning `external_id -> id`.

        Institutions are shared between users, so a second user at the same bank updates
        the existing row rather than creating a rival one.
        """
        if not snapshots:
            return {}

        statement = (
            insert(FinancialInstitution)
            .values(
                [
                    {
                        "id": uuid.uuid4(),
                        "provider": provider,
                        "external_id": snapshot.external_id,
                        "name": snapshot.name,
                    }
                    for snapshot in snapshots
                ]
            )
            .on_conflict_do_update(
                index_elements=["provider", "external_id"],
                set_={"name": insert(FinancialInstitution).excluded.name, "updated_at": func.now()},
            )
            .returning(FinancialInstitution.external_id, FinancialInstitution.id)
        )
        result = await self._session.execute(statement)
        return dict(result.all())  # rows are (external_id, id) pairs
