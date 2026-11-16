"""Start the read-only API bound to local loopback, never a factory network."""
import uvicorn


def main() -> None:
    """Only localhost is permitted by this standalone launcher."""
    uvicorn.run("capstone.api.app:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
