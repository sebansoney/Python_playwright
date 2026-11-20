"""Start the sample application:  uv run python -m sample_application [--port 8000] [--env test]"""

import argparse
import os

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the sample application")
    parser.add_argument("--host", default=os.environ.get("APP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("APP_PORT", "8000")))
    parser.add_argument(
        "--env",
        default=None,
        help="APP_ENV value; 'test' enables POST /api/v1/test-support/reset",
    )
    parser.add_argument("--reset-db", action="store_true", help="wipe and reseed the database")
    parser.add_argument("--reload", action="store_true", help="auto-reload on code changes")
    args = parser.parse_args()

    if args.env:
        os.environ["APP_ENV"] = args.env
    if args.reset_db:
        from sample_application.backend.seed import init_db

        init_db(reset=True)

    uvicorn.run(
        "sample_application.backend.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
