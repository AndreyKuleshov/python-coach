"""User read/write access for Storage."""

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from python_coach.storage.models.user import User


class UsersMixin:
    """Create and look up registered accounts."""

    session: AsyncSession

    async def get_user_by_id(self, user_id: int) -> User | None:
        """Fetch one user by primary key."""
        return await self.session.get(User, user_id)

    async def get_user_by_email(self, email: str) -> User | None:
        """Fetch one user by (already lower-cased) email."""
        stmt = select(User).where(User.email == email)
        result = await self.session.exec(stmt)
        return result.first()

    async def create_user(self, email: str, password_hash: str) -> User:
        """Insert an unconfirmed user and return it with its id."""
        user = User(email=email, password_hash=password_hash)
        self.session.add(user)
        await self.session.flush()
        await self.session.refresh(user)
        return user

    async def mark_email_confirmed(self, user: User) -> User:
        """Flip the user's email-confirmed flag and persist it."""
        user.is_email_confirmed = True
        self.session.add(user)
        await self.session.flush()
        await self.session.refresh(user)
        return user
