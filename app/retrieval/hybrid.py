from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.config import DATABASE_PATH, INDEXES_DIR
from app.retrieval.evidence_bundle import build_evidence_bundle
from app.retrieval.vector_store import search


def retrieve(
    source_id: str,
    query: str,
    top_k: int = 3,
    db_path: Path = DATABASE_PATH,
    index_root: Path = INDEXES_DIR,
) -> dict[str, Any]:
    event_results = search(source_id, query, top_k=top_k, db_path=db_path, index_root=index_root)
    results = []
    for rank, result in enumerate(event_results, start=1):
        bundle = build_evidence_bundle(result["event_id"], db_path)
        results.append(
            {
                "rank": rank,
                "score": result["score"],
                "event": {
                    "id": result["event_id"],
                    "title": result["title"],
                    "summary": result["summary"],
                },
                "evidence_bundle": bundle,
            }
        )
    return {"query": query, "results": results}


def _print_result(payload: dict[str, Any]) -> None:
    print("QUERY")
    print(payload["query"])
    print()
    print("TOP EVENTS")
    for result in payload["results"]:
        bundle = result["evidence_bundle"]
        print()
        print(f"EVENT {result['rank']}")
        print(f"score: {result['score']}")
        print(f"title: {result['event']['title']}")
        print(f"summary: {result['event']['summary']}")
        print()
        print("EVIDENCE")
        print("transcript:")
        for transcript in bundle["transcripts"]:
            print(f"- {transcript['start_time']} - {transcript['end_time']}: {transcript['content']}")
        print("OCR:")
        for ocr in bundle["ocr"]:
            print(f"- {ocr['timestamp']}: {ocr['text']}")
        print("frames:")
        for frame in bundle["frames"]:
            print(f"- {frame['timestamp']}: {frame['path']}")
        print("entities:")
        for entity in bundle["entities"]:
            print(f"- {entity['name']} | {entity['type']} | {entity['confidence']}")
        print("relationships:")
        for relationship in bundle["relationships"]:
            print(
                f"- {relationship['source']} --{relationship['relation']}--> "
                f"{relationship['target']} | {relationship['confidence']} | {relationship['method']}"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Hybrid event retrieval over FAISS + evidence graph.")
    parser.add_argument("source_id")
    parser.add_argument("query")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--json", action="store_true", help="Print raw JSON instead of readable output.")
    args = parser.parse_args()

    payload = retrieve(args.source_id, args.query, top_k=args.top_k)
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        _print_result(payload)


if __name__ == "__main__":
    main()
