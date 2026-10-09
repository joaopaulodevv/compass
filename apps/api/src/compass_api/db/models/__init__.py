"""ORM models.

Every model must be imported here: Alembic autogenerate only sees what is attached to
`Base.metadata` at import time.
"""

from compass_api.db.models.user import User

__all__ = ["User"]
