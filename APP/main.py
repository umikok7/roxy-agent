from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn
from APP.api.app import create_app
from dotenv import load_dotenv

from harness.client import HarnessClient
from harness.rag import KnowledgeBaseService

app = create_app()


def _run_reindex() -> int:
    project_root = Path(__file__).resolve().parents[1]
    load_dotenv(project_root / ".env")
    client = HarnessClient(project_root=project_root)
    client.config.rag.knowledge_dir.mkdir(parents=True, exist_ok=True)
    count = KnowledgeBaseService(client.config.rag).index_documents()
    print(f"Indexed {count} knowledge chunks from {client.config.rag.knowledge_dir}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", nargs="?", default="serve", choices=["serve", "reindex-kb"])
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    if args.command == "reindex-kb":
        raise SystemExit(_run_reindex())

    uvicorn.run(app, host=args.host, port=args.port)
