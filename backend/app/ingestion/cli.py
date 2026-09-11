import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

import yaml

from app.core.settings import Settings, get_settings
from app.rag.errors import IngestionError
from app.rag.factory import create_knowledge_service
from app.rag.models import IngestionResult, IngestionStatus


def _result_payload(result: IngestionResult) -> dict[str, object]:
    return result.model_dump(mode="json")


def _print_results(results: list[IngestionResult]) -> None:
    for result in results:
        print(json.dumps(_result_payload(result), ensure_ascii=False))


def _add_file(path: Path, settings: Settings) -> int:
    service = create_knowledge_service(settings)
    documents_root = settings.knowledge_documents_dir.resolve()
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(documents_root):
        raise IngestionError("CLI files must be inside the approved documents directory")
    prepared = service.prepare_file(
        filename=resolved.name,
        content_type=None,
        data=resolved.read_bytes(),
    )
    results = service.upsert([prepared])
    _print_results(results)
    return int(any(result.status == IngestionStatus.ERROR for result in results))


def _add_url(url: str, settings: Settings, source_id: str | None, title: str | None) -> int:
    service = create_knowledge_service(settings)
    prepared = service.prepare_url(
        url,
        allowed_hosts=tuple(settings.knowledge_allowed_hosts),
        max_bytes=settings.knowledge_max_url_bytes,
        timeout_seconds=settings.knowledge_url_timeout_seconds,
    )
    if source_id or title:
        prepared = replace(
            prepared,
            source_id=source_id or prepared.source_id,
            title=title or prepared.title,
        )
    results = service.upsert([prepared])
    _print_results(results)
    return int(any(result.status == IngestionStatus.ERROR for result in results))


def _sync(settings: Settings) -> int:
    service = create_knowledge_service(settings)
    prepared_sources = []
    failures: list[IngestionResult] = []
    for path in sorted(settings.knowledge_documents_dir.glob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        try:
            prepared_sources.append(
                service.prepare_file(filename=path.name, content_type=None, data=path.read_bytes())
            )
        except IngestionError as exc:
            failures.append(
                IngestionResult(
                    source_id=None,
                    name=path.name,
                    status=IngestionStatus.ERROR,
                    detail=str(exc),
                )
            )

    manifest_path = settings.knowledge_documents_dir.parent / "sources.yaml"
    manifest = (
        yaml.safe_load(manifest_path.read_text()) if manifest_path.exists() else {"sources": []}
    )
    if not isinstance(manifest, dict) or not isinstance(manifest.get("sources"), list):
        raise IngestionError("Source manifest must contain a sources list")
    for item in manifest["sources"]:
        try:
            prepared = service.prepare_url(
                str(item["url"]),
                allowed_hosts=tuple(settings.knowledge_allowed_hosts),
                max_bytes=settings.knowledge_max_url_bytes,
                timeout_seconds=settings.knowledge_url_timeout_seconds,
            )
            prepared_sources.append(
                replace(
                    prepared,
                    source_id=str(item["id"]),
                    title=str(item.get("title") or prepared.title),
                )
            )
        except (IngestionError, KeyError, TypeError) as exc:
            failures.append(
                IngestionResult(
                    source_id=str(item.get("id")) if isinstance(item, dict) else None,
                    name=str(item.get("url", "manifest entry"))
                    if isinstance(item, dict)
                    else "manifest entry",
                    status=IngestionStatus.ERROR,
                    detail=str(exc),
                )
            )
    results = service.upsert(prepared_sources) if prepared_sources else []
    _print_results(results + failures)
    return int(bool(failures) or any(result.status == IngestionStatus.ERROR for result in results))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage the local Cadre AI knowledge index")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("sync", help="Synchronize approved documents and manifest URLs")
    add_file = subparsers.add_parser("add-file", help="Add or update one approved local file")
    add_file.add_argument("path", type=Path)
    add_url = subparsers.add_parser("add-url", help="Add or update one allowlisted HTTPS URL")
    add_url.add_argument("url")
    add_url.add_argument("--source-id")
    add_url.add_argument("--title")
    remove = subparsers.add_parser("remove", help="Remove one source and its chunks")
    remove.add_argument("source_id")
    subparsers.add_parser("rebuild", help="Re-embed all persisted sources")
    subparsers.add_parser("list", help="List indexed sources")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = get_settings()
    try:
        if args.command == "sync":
            return _sync(settings)
        if args.command == "add-file":
            return _add_file(args.path, settings)
        if args.command == "add-url":
            return _add_url(args.url, settings, args.source_id, args.title)
        service = create_knowledge_service(settings)
        if args.command == "remove":
            removed = service.remove(args.source_id)
            print(json.dumps({"source_id": args.source_id, "removed": removed}))
            return 0 if removed else 1
        if args.command == "rebuild":
            print(json.dumps({"chunk_count": service.rebuild()}))
            return 0
        if args.command == "list":
            for source in service.list_sources():
                print(source.model_dump_json())
            return 0
    except (IngestionError, OSError, RuntimeError, yaml.YAMLError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
