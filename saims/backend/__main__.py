"""Run the SAIMS API server.

    python -m saims.backend --host 0.0.0.0 --port 8000

Configure with environment variables: SAIMS_DATABASE_URL (PostgreSQL in production),
SAIMS_ADMIN_PASSWORD (first administrator), SAIMS_SEED_DEMO=1 (demo data on an empty database).
Put it behind a TLS-terminating reverse proxy (HTTPS) for network use.
"""
import argparse
import logging

import uvicorn

from saims.backend.main import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="SAIMS API server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(create_app(), host=args.host, port=args.port, proxy_headers=True)


if __name__ == "__main__":
    main()
