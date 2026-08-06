"""Readable, dependency-free implementations of the four DbCC operators.

The paper uses one formula for all layers.  This module keeps that formula visible:

    gain = support * width - (support + width)

`support * width` is the repeated information we pay for before compression.
`width` is the one-time component definition and `support` is one reference per carrier.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Set, Tuple
import re


ColumnSignature = Tuple[str, str]


@dataclass(frozen=True)
class Column:
    name: str
    data_type: str
    description: str
    tags: Tuple[str, ...]

    @property
    def signature(self) -> ColumnSignature:
        return (self.name.lower(), self.data_type.lower())


@dataclass(frozen=True)
class Table:
    name: str
    columns: Tuple[Column, ...]


@dataclass(frozen=True)
class Database:
    database_id: str
    tables: Tuple[Table, ...]


def load_database(payload: Mapping[str, Any]) -> Database:
    tables: List[Table] = []
    for raw_table in payload["tables"]:
        columns = tuple(
            Column(
                name=raw_column["name"],
                data_type=raw_column["type"],
                description=raw_column.get("description", ""),
                tags=tuple(raw_column.get("tags", [])),
            )
            for raw_column in raw_table["columns"]
        )
        tables.append(Table(name=raw_table["name"], columns=columns))
    return Database(database_id=payload["id"], tables=tuple(tables))


def sgcf_gain(support: int, width: int) -> int:
    """Return the paper's simplified Support-Gain score."""
    return support * width - (support + width)


def raw_schema_units(database: Database) -> int:
    """Count one information unit per repeated physical column definition."""
    return sum(len(table.columns) for table in database.tables)


def render_raw(database: Database) -> str:
    lines = ["[RAW_SCHEMA]"]
    for table in database.tables:
        lines.append(f"## {table.name}")
        for column in table.columns:
            lines.append(
                f"- {column.name}: {column.data_type} | {column.description} | tags={list(column.tags)}"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def factorize_column_groups(
    database: Database,
    min_support: int = 2,
    min_width: int = 2,
    min_gain: int = 1,
) -> Dict[str, Any]:
    """Factor repeated column groups using Algorithm 1's inverted-index idea.

    Columns with the same set of carrier tables form one equivalence class.  This is the
    practical pruning trick from the paper and official implementation: it avoids enumerating
    every possible subset of a wide table.
    """

    signature_to_tables: Dict[ColumnSignature, Set[int]] = {}
    signature_to_column: Dict[ColumnSignature, Column] = {}
    for table_index, table in enumerate(database.tables):
        for column in table.columns:
            signature_to_tables.setdefault(column.signature, set()).add(table_index)
            signature_to_column.setdefault(column.signature, column)

    support_set_to_signatures: Dict[frozenset[int], List[ColumnSignature]] = {}
    for signature, table_indices in signature_to_tables.items():
        if len(table_indices) >= min_support:
            support_set_to_signatures.setdefault(frozenset(table_indices), []).append(signature)

    candidates: List[Dict[str, Any]] = []
    for table_indices, signatures in support_set_to_signatures.items():
        support = len(table_indices)
        width = len(signatures)
        gain = sgcf_gain(support, width)
        if width >= min_width and gain >= min_gain:
            candidates.append(
                {
                    "table_indices": set(table_indices),
                    "signatures": sorted(signatures),
                    "support": support,
                    "width": width,
                    "gain": gain,
                }
            )

    candidates.sort(key=lambda item: (item["gain"], item["support"], item["width"]), reverse=True)

    signature_to_component: Dict[ColumnSignature, str] = {}
    components: Dict[str, Dict[str, Any]] = {}
    for index, candidate in enumerate(candidates, start=1):
        component_id = f"C{index}"
        columns = [signature_to_column[signature] for signature in candidate["signatures"]]
        components[component_id] = {
            "support": candidate["support"],
            "width": candidate["width"],
            "gain": candidate["gain"],
            "columns": [column_to_dict(column) for column in columns],
        }
        for signature in candidate["signatures"]:
            signature_to_component[signature] = component_id

    rewritten_tables: List[Dict[str, Any]] = []
    for table in database.tables:
        references = sorted(
            {
                signature_to_component[column.signature]
                for column in table.columns
                if column.signature in signature_to_component
            }
        )
        residual = [
            column_to_dict(column)
            for column in table.columns
            if column.signature not in signature_to_component
        ]
        rewritten_tables.append(
            {"name": table.name, "component_refs": references, "residual_columns": residual}
        )

    component_definition_units = sum(component["width"] for component in components.values())
    reference_units = sum(len(table["component_refs"]) for table in rewritten_tables)
    residual_units = sum(len(table["residual_columns"]) for table in rewritten_tables)

    return {
        "components": components,
        "tables": rewritten_tables,
        "estimated_units": component_definition_units + reference_units + residual_units,
        "unit_breakdown": {
            "component_definitions": component_definition_units,
            "references": reference_units,
            "residual_columns": residual_units,
        },
    }


def recover_factorized_schema(artifacts: Mapping[str, Any]) -> Dict[str, Set[ColumnSignature]]:
    """Expand references and prove that no table or column was discarded."""
    components = {
        component_id: {
            (column["name"].lower(), column["type"].lower())
            for column in component["columns"]
        }
        for component_id, component in artifacts["components"].items()
    }
    recovered: Dict[str, Set[ColumnSignature]] = {}
    for table in artifacts["tables"]:
        signatures = {
            (column["name"].lower(), column["type"].lower())
            for column in table["residual_columns"]
        }
        for component_id in table["component_refs"]:
            signatures.update(components[component_id])
        recovered[table["name"]] = signatures
    return recovered


def original_schema(database: Database) -> Dict[str, Set[ColumnSignature]]:
    return {table.name: {column.signature for column in table.columns} for table in database.tables}


def render_factorized(artifacts: Mapping[str, Any]) -> str:
    lines = ["[COMPONENTS]"]
    for component_id, component in artifacts["components"].items():
        lines.append(
            f"<{component_id}> support={component['support']} width={component['width']} gain={component['gain']}"
        )
        for column in component["columns"]:
            lines.append(f"- {column['name']}: {column['type']}")
    lines.append("\n[TABLES]")
    for table in artifacts["tables"]:
        lines.append(f"## {table['name']} uses={table['component_refs']}")
        for column in table["residual_columns"]:
            lines.append(f"- {column['name']}: {column['type']}")
    return "\n".join(lines).rstrip() + "\n"


def build_template_hierarchy(
    database: Database,
    min_parent_width: int = 3,
    min_gain: int = 2,
    max_delta_ratio: float = 0.45,
) -> Dict[str, Any]:
    """Group identical schemas and let slightly larger templates extend a smaller parent."""

    signature_to_tables: Dict[frozenset[ColumnSignature], List[str]] = {}
    signature_to_columns: Dict[frozenset[ColumnSignature], Tuple[Column, ...]] = {}
    for table in database.tables:
        signature = frozenset(column.signature for column in table.columns)
        signature_to_tables.setdefault(signature, []).append(table.name)
        signature_to_columns.setdefault(signature, table.columns)

    templates: List[Dict[str, Any]] = []
    for index, signature in enumerate(sorted(signature_to_tables, key=lambda item: (len(item), sorted(item))), start=1):
        templates.append(
            {
                "id": f"T{index}",
                "signature": set(signature),
                "instances": sorted(signature_to_tables[signature]),
                "columns": [column_to_dict(column) for column in signature_to_columns[signature]],
                "parent": None,
                "delta_columns": [],
            }
        )

    for current_index, current in enumerate(templates):
        possible_parents = [
            parent
            for parent in templates[:current_index]
            if len(parent["signature"]) >= min_parent_width
            and parent["signature"].issubset(current["signature"])
        ]
        if not possible_parents:
            continue
        parent = max(possible_parents, key=lambda item: len(item["signature"]))
        delta = current["signature"] - parent["signature"]
        gain = len(current["signature"]) - (1 + len(delta))
        if gain < min_gain or len(delta) / len(current["signature"]) > max_delta_ratio:
            continue
        current["parent"] = parent["id"]
        current["gain"] = gain
        current["delta_columns"] = [
            column for column in current["columns"]
            if (column["name"].lower(), column["type"].lower()) in delta
        ]

    serializable = []
    for template in templates:
        clean = {key: value for key, value in template.items() if key != "signature"}
        serializable.append(clean)
    return {"templates": serializable}


def render_templates(artifacts: Mapping[str, Any]) -> str:
    lines = ["[TEMPLATES]"]
    for template in artifacts["templates"]:
        parent = f" extends <{template['parent']}>" if template["parent"] else ""
        lines.append(f"<{template['id']}>{parent} tables={template['instances']}")
        columns = template["delta_columns"] if template["parent"] else template["columns"]
        for column in columns:
            lines.append(f"- {column['name']}: {column['type']}")
    return "\n".join(lines).rstrip() + "\n"


def componentize_semantic_tags(
    database: Database,
    max_width: int = 2,
    min_support: int = 3,
    min_gain: int = 1,
) -> Dict[str, Any]:
    """Extract repeated tag subsets, mirroring Algorithm 3's frequency-first sweep."""

    carriers: Dict[str, Set[str]] = {
        f"{table.name}.{column.name}": set(column.tags)
        for table in database.tables
        for column in table.columns
    }
    candidate_to_carriers: Dict[Tuple[str, ...], Set[str]] = {}
    for carrier, tags in carriers.items():
        ordered = sorted(tags)
        for width in range(1, min(max_width, len(ordered)) + 1):
            for candidate in combinations(ordered, width):
                candidate_to_carriers.setdefault(candidate, set()).add(carrier)

    candidates: List[Dict[str, Any]] = []
    for tags, tag_carriers in candidate_to_carriers.items():
        support = len(tag_carriers)
        width = len(tags)
        gain = sgcf_gain(support, width)
        if support >= min_support and gain >= min_gain:
            candidates.append(
                {"tags": tags, "carriers": tag_carriers, "support": support, "width": width, "gain": gain}
            )
    candidates.sort(key=lambda item: (item["support"], item["gain"], item["width"]), reverse=True)

    selected: List[Dict[str, Any]] = []
    used_tags: Set[str] = set()
    for candidate in candidates:
        if used_tags.intersection(candidate["tags"]):
            continue
        selected.append(candidate)
        used_tags.update(candidate["tags"])

    components: Dict[str, Any] = {}
    carrier_refs: Dict[str, List[str]] = {carrier: [] for carrier in carriers}
    for index, candidate in enumerate(selected, start=1):
        component_id = f"S{index}"
        components[component_id] = {
            "tags": list(candidate["tags"]),
            "support": candidate["support"],
            "width": candidate["width"],
            "gain": candidate["gain"],
        }
        for carrier in candidate["carriers"]:
            carrier_refs[carrier].append(component_id)

    residuals: Dict[str, List[str]] = {}
    for carrier, tags in carriers.items():
        referenced_tags = {
            tag
            for component_id in carrier_refs[carrier]
            for tag in components[component_id]["tags"]
        }
        residuals[carrier] = sorted(tags - referenced_tags)

    return {"components": components, "carrier_refs": carrier_refs, "residual_tags": residuals}


def render_semantic(artifacts: Mapping[str, Any]) -> str:
    lines = ["[SEMANTIC_COMPONENTS]"]
    for component_id, component in artifacts["components"].items():
        lines.append(
            f"<{component_id}> tags={component['tags']} support={component['support']} gain={component['gain']}"
        )
    lines.append("\n[COLUMN_TAG_REFERENCES]")
    for carrier, refs in artifacts["carrier_refs"].items():
        residual = artifacts["residual_tags"][carrier]
        lines.append(f"- {carrier}: refs={refs}, residual={residual}")
    return "\n".join(lines).rstrip() + "\n"


def purify_evidence(question: str, entries: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Select typed evidence atoms using explicit triggers.

    The paper uses an LLM for this step.  A deterministic trigger scorer is used here so that
    anyone can reproduce the data flow without an API key.  It preserves the important output
    contract: small typed atoms anchored to concrete schema elements.
    """

    normalized_question = " ".join(tokenize(question))
    selected: List[Dict[str, Any]] = []
    rejected: List[str] = []
    for entry in entries:
        matched = [trigger for trigger in entry["triggers"] if trigger.lower() in normalized_question]
        if not matched:
            rejected.append(entry["id"])
            continue
        selected.append(
            {
                "id": entry["id"],
                "type": entry["type"],
                "matched_triggers": matched,
                "text": entry["text"],
                "bindings": entry["bindings"],
            }
        )
    return {
        "question": question,
        "source_count": len(entries),
        "selected_count": len(selected),
        "selected": selected,
        "rejected_ids": rejected,
        "implementation_note": "deterministic stand-in for the paper's LLM evidence purifier",
    }


def tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9_]+", text.lower())


def column_to_dict(column: Column) -> Dict[str, Any]:
    return {
        "name": column.name,
        "type": column.data_type,
        "description": column.description,
        "tags": list(column.tags),
    }
