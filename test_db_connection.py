"""Run explicitly to verify Neon; importing this script makes no connection."""

import sys


if __name__ == "__main__":
    try:
        from capstone.database.connection import check_database_connection

        connected = check_database_connection()
    except Exception as error:
        # Driver errors can contain connection details; never print them here.
        print(f"Connection check failed ({type(error).__name__}). Check DATABASE_URL and network access.", file=sys.stderr)
        sys.exit(1)
    print(connected)
    sys.exit(0 if connected else 1)
