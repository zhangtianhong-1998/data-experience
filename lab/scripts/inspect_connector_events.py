"""把连接器产生的 MCP 事件压缩成便于人工阅读的证据文件。"""

import json
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "output" / "datahub_connector_events.json"
OUTPUT = ROOT / "output" / "datahub_connector_event_summary.json"


def main() -> None:
    records = json.loads(INPUT.read_text(encoding="utf-8"))
    by_entity = defaultdict(list)
    aspect_counts = Counter()
    selected_examples = []

    for record in records:
        if "proposedSnapshot" in record:
            snapshot = next(iter(record["proposedSnapshot"].values()))
            urn = snapshot["urn"]
            aspects = []
            for wrapped_aspect in snapshot["aspects"]:
                full_name = next(iter(wrapped_aspect))
                aspect = full_name.rsplit(".", 1)[-1]
                aspects.append(aspect)
                aspect_counts[aspect] += 1
            by_entity[urn].extend(aspects)
            selected_examples.append(record)
            continue

        urn = record.get("entityUrn")
        aspect = record.get("aspectName")
        by_entity[urn].append(aspect)
        aspect_counts[aspect] += 1
        if aspect in {"upstreamLineage", "queryProperties"}:
            selected_examples.append(record)

    result = {
        "record_count": len(records),
        "entity_count": len(by_entity),
        "aspect_counts": dict(aspect_counts),
        "entities": dict(by_entity),
        "selected_event_examples": selected_examples,
    }
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("record_count", "entity_count", "aspect_counts")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
