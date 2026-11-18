"""Background worker entrypoint (Northflank); no FastAPI server."""

from capstone.worker.runner import main

if __name__ == "__main__":
    main()
