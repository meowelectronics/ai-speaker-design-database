"""Build and query the local loudspeaker-design knowledge database."""

import argparse
import json
from pathlib import Path
import sqlite3


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SEED = ROOT / "data" / "knowledge" / "speaker_design_knowledge.json"
DEFAULT_DATABASE = ROOT / "data" / "knowledge" / "speaker_design_knowledge.sqlite3"

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS sources (
    source_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    source_type TEXT NOT NULL,
    uri TEXT NOT NULL,
    citation TEXT NOT NULL,
    notes TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS knowledge_items (
    item_id TEXT PRIMARY KEY,
    domain TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    equation TEXT NOT NULL,
    inputs_json TEXT NOT NULL,
    units_json TEXT NOT NULL,
    assumptions TEXT NOT NULL,
    implementation_ref TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS knowledge_sources (
    item_id TEXT NOT NULL REFERENCES knowledge_items(item_id) ON DELETE CASCADE,
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    citation_detail TEXT NOT NULL,
    PRIMARY KEY (item_id, source_id)
);
CREATE TABLE IF NOT EXISTS workflow_stages (
    stage_id TEXT PRIMARY KEY,
    sequence INTEGER NOT NULL UNIQUE,
    title TEXT NOT NULL,
    inputs_json TEXT NOT NULL,
    gate TEXT NOT NULL,
    implementation_ref TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS limitations (
    limitation_id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    description TEXT NOT NULL,
    needed TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_knowledge_domain ON knowledge_items(domain);
CREATE INDEX IF NOT EXISTS idx_source_type ON sources(source_type);
"""


def build_database(seed_path=DEFAULT_SEED, database_path=DEFAULT_DATABASE):
    seed_path, database_path = Path(seed_path), Path(database_path)
    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    if seed.get("schema_version") != 1:
        raise ValueError("Unsupported knowledge seed schema version.")
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database_path) as connection:
        connection.executescript(SCHEMA)
        connection.execute("DELETE FROM knowledge_sources")
        connection.execute("DELETE FROM knowledge_items")
        connection.execute("DELETE FROM sources")
        connection.execute("DELETE FROM workflow_stages")
        connection.execute("DELETE FROM limitations")
        connection.executemany(
            "INSERT INTO sources VALUES (?, ?, ?, ?, ?, ?)",
            ((item["id"], item["title"], item["kind"], item.get("uri", ""),
              item.get("citation", ""), item.get("notes", ""))
             for item in seed["sources"]),
        )
        source_ids = {item["id"] for item in seed["sources"]}
        for item in seed["knowledge_items"]:
            missing_sources = set(item["source_ids"]) - source_ids
            if missing_sources:
                raise ValueError(f"Unknown source IDs for {item['id']}: {sorted(missing_sources)}")
            connection.execute(
                "INSERT INTO knowledge_items VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (item["id"], item["domain"], item["title"], item["summary"],
                 item["equations"], json.dumps(item["inputs_json"], sort_keys=True),
                 json.dumps(item["units_json"], sort_keys=True), item["assumptions"],
                 item["implementation_ref"]),
            )
            connection.executemany(
                "INSERT INTO knowledge_sources VALUES (?, ?, ?)",
                ((item["id"], source_id, item.get("citation_detail", ""))
                 for source_id in item["source_ids"]),
            )
        connection.executemany(
            "INSERT INTO workflow_stages VALUES (?, ?, ?, ?, ?, ?)",
            ((stage["id"], stage["sequence"], stage["title"],
              json.dumps(stage["inputs_json"], sort_keys=True), stage["gate"],
              stage["implementation_ref"]) for stage in seed["workflow_stages"]),
        )
        connection.executemany(
            "INSERT INTO limitations VALUES (?, ?, ?, ?)",
            ((item["id"], item["category"], item["description"], item["needed"])
             for item in seed["limitations"]),
        )
        counts = {
            "sources": connection.execute("SELECT count(*) FROM sources").fetchone()[0],
            "knowledge_items": connection.execute("SELECT count(*) FROM knowledge_items").fetchone()[0],
            "workflow_stages": connection.execute("SELECT count(*) FROM workflow_stages").fetchone()[0],
            "limitations": connection.execute("SELECT count(*) FROM limitations").fetchone()[0],
        }
    connection.close()
    return {"database": str(database_path), **counts}


def search_knowledge(query, database_path=DEFAULT_DATABASE, limit=20):
    database_path = Path(database_path)
    if not database_path.is_file():
        raise FileNotFoundError(f"Knowledge database not found: {database_path}. Run the build command first.")
    pattern = f"%{query}%"
    connection = sqlite3.connect(database_path)
    try:
        connection.row_factory = sqlite3.Row
        items = connection.execute(
            """SELECT DISTINCT k.* FROM knowledge_items k
               LEFT JOIN knowledge_sources ks ON ks.item_id = k.item_id
               LEFT JOIN sources s ON s.source_id = ks.source_id
               WHERE k.item_id LIKE ? OR k.domain LIKE ? OR k.title LIKE ?
                  OR k.summary LIKE ? OR k.equation LIKE ? OR k.implementation_ref LIKE ?
                  OR s.title LIKE ? OR s.citation LIKE ?
               ORDER BY k.domain, k.item_id LIMIT ?""",
            (pattern,) * 8 + (limit,),
        ).fetchall()
        results = []
        for row in items:
            item = dict(row)
            item["record_type"] = "knowledge_item"
            item["inputs"] = json.loads(item.pop("inputs_json"))
            item["units"] = json.loads(item.pop("units_json"))
            item["sources"] = [dict(source) for source in connection.execute(
                """SELECT s.source_id, s.title, s.uri, s.citation, ks.citation_detail
                   FROM knowledge_sources ks JOIN sources s USING(source_id)
                   WHERE ks.item_id=? ORDER BY s.source_id""",
                (item["item_id"],),
            )]
            results.append(item)
        for row in connection.execute(
            """SELECT * FROM limitations
               WHERE limitation_id LIKE ? OR category LIKE ? OR description LIKE ? OR needed LIKE ?
               ORDER BY category, limitation_id LIMIT ?""",
            (pattern,) * 4 + (limit,),
        ):
            results.append({"record_type": "limitation", **dict(row)})
        for row in connection.execute(
            """SELECT * FROM workflow_stages
               WHERE stage_id LIKE ? OR title LIKE ? OR gate LIKE ? OR implementation_ref LIKE ?
               ORDER BY sequence LIMIT ?""",
            (pattern,) * 4 + (limit,),
        ):
            results.append({"record_type": "workflow_stage", **dict(row),
                            "inputs": json.loads(row["inputs_json"])})
        for row in connection.execute(
            """SELECT * FROM sources
               WHERE source_id LIKE ? OR title LIKE ? OR source_type LIKE ? OR citation LIKE ? OR notes LIKE ?
               ORDER BY source_type, source_id LIMIT ?""",
            (pattern,) * 5 + (limit,),
        ):
            results.append({"record_type": "source", **dict(row)})
        return results
    finally:
        connection.close()


def workflow_stages(database_path=DEFAULT_DATABASE):
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        results = [{**dict(row), "inputs": json.loads(row["inputs_json"])}
                   for row in connection.execute("SELECT * FROM workflow_stages ORDER BY sequence")]
    connection.close()
    return results


def list_sources(database_path=DEFAULT_DATABASE):
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        results = [dict(row) for row in connection.execute(
            "SELECT source_id, title, source_type, uri, citation, notes FROM sources ORDER BY source_type, source_id"
        )]
    connection.close()
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="rebuild SQLite from the checked-in JSON seed")
    build.add_argument("--seed", default=str(DEFAULT_SEED))
    build.add_argument("--database", default=str(DEFAULT_DATABASE))
    search = subparsers.add_parser("search", help="search equations, topics, implementations, and sources")
    search.add_argument("query")
    search.add_argument("--database", default=str(DEFAULT_DATABASE))
    search.add_argument("--limit", type=int, default=20)
    stages = subparsers.add_parser("stages", help="list workflow stages and their gates")
    stages.add_argument("--database", default=str(DEFAULT_DATABASE))
    args = parser.parse_args()
    if args.command == "build":
        result = build_database(args.seed, args.database)
    elif args.command == "search":
        result = search_knowledge(args.query, args.database, args.limit)
    else:
        result = workflow_stages(args.database)
    print(json.dumps(result, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()