import asyncio

from sqlalchemy import text

from src.database import (
    AsyncSessionLocal,
)


async def main() -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                "SELECT version_num "
                "FROM alembic_version"
            )
        )

        revisions = (
            result.scalars().all()
        )

        print(
            "Alembic database state"
        )

        print(
            "=" * 50
        )

        if not revisions:
            print(
                "No Alembic revision found."
            )

        else:
            for revision in revisions:
                print(
                    f"Current revision: "
                    f"{revision}"
                )


if __name__ == "__main__":
    asyncio.run(
        main()
    )