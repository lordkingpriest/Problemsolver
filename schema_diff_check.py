"""
CI helper: check for schema drift between SQLAlchemy models metadata and the live DB.

Exit code:
 - 0: no drift
 - 2: drift detected (prints differences)
 - 3: connection/config error
"""
import sys
from sqlalchemy import create_engine
from alembic.migration import MigrationContext
from alembic.autogenerate import compare_metadata
from app.db.models import Base
from app.core.config import settings

def main():
    db_url = settings.DATABASE_URL
    if not db_url:
        print("DATABASE_URL not set", file=sys.stderr)
        sys.exit(3)
    conn = create_engine(db_url).connect()
    try:
        mc = MigrationContext.configure(conn)
        diffs = compare_metadata(mc, Base.metadata)
        if not diffs:
            print("No schema drift detected")
            sys.exit(0)
        else:
            print("Schema drift detected. Diff items:")
            for d in diffs:
                print(d)
            sys.exit(2)
    finally:
        conn.close()

if __name__ == "__main__":
    main()