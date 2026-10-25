"""Internal CLI. Default is DB-only dry run; --execute explicitly permits writes."""

import argparse
import json

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, normalize_database_url
from app.workers.home_preview import run_cycle


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument(
        "--retry-research",
        action="store_true",
        help="Explicitly resume incomplete selected-player research within the same slot budget",
    )
    parser.add_argument("--search", action="store_true")
    parser.add_argument("--prune", action="store_true")
    parser.add_argument("--fixture-id", type=int)
    parser.add_argument("--database-url")
    parser.add_argument("--env-file")
    args = parser.parse_args()
    settings = Settings(_env_file=args.env_file or ".env")
    if args.search:
        settings.home_preview_search_enabled = True
    engine = create_engine(
        normalize_database_url(args.database_url or settings.database_url),
        pool_size=1,
        max_overflow=0,
    )
    try:
        if args.prune:
            from app.services.home_preview_retention import prune_home_previews

            with Session(engine) as session:
                report = prune_home_previews(session, dry_run=not args.execute)
        else:
            report = run_cycle(
                sessionmaker(bind=engine),
                settings=settings,
                execute=args.execute,
                fixture_id=args.fixture_id,
                retry_failed=args.retry_failed,
                retry_research=args.retry_research,
            )
        print(json.dumps(report, ensure_ascii=False))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
