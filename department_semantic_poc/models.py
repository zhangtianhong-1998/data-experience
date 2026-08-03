from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


ConceptType = Literal[
    "business_entity",
    "business_event",
    "metric",
    "measure",
    "dimension",
    "attribute",
    "business_term",
    "enum",
    "business_rule",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MetricDefinitionCandidate(StrictModel):
    expression: str | None = None
    aggregation: str | None = None
    numerator: str | None = None
    denominator: str | None = None
    filters: list[str] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)
    grain: list[str] = Field(default_factory=list)
    unit: str | None = None
    time_semantics: str | None = None


class LocalConcept(StrictModel):
    local_ref: str = Field(pattern=r"^C\d{2,3}$")
    concept_type: ConceptType
    label: str = Field(min_length=1)
    normalized_label: str | None = None
    definition: str | None = None
    observed_labels: list[str] = Field(default_factory=list)
    qualifiers: list[str] = Field(default_factory=list)
    asset_refs: list[str] = Field(min_length=1)
    evidence_refs: list[str] = Field(min_length=1)
    metric_definition: MetricDefinitionCandidate | None = None
    missing_information: list[str] = Field(default_factory=list)


RelationPredicate = Literal[
    "measures_entity",
    "analyzed_by",
    "attribute_of",
    "event_involves_entity",
    "calculated_from",
    "filtered_by",
    "synonym_candidate",
    "variant_candidate",
    "broader_candidate",
    "related_candidate",
    "conflict_candidate",
]


class LocalRelation(StrictModel):
    relation_ref: str = Field(pattern=r"^R\d{2,3}$")
    subject_ref: str = Field(pattern=r"^C\d{2,3}$")
    predicate: RelationPredicate
    object_ref: str = Field(pattern=r"^C\d{2,3}$")
    rationale: str
    evidence_refs: list[str] = Field(min_length=1)
    limitations: list[str] = Field(default_factory=list)


class UnresolvedItem(StrictModel):
    item_ref: str = Field(pattern=r"^U\d{2,3}$")
    question: str
    related_asset_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


class ReportSummary(StrictModel):
    title: str | None = None
    business_purpose: str | None = None
    analysis_objects: list[str] = Field(default_factory=list)
    organization_candidates: list[str] = Field(default_factory=list)
    time_scope_candidates: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class ReportExtraction(StrictModel):
    schema_version: Literal["report-extraction-v1"]
    package_ref: str
    report_ref: str
    summary: ReportSummary
    concepts: list[LocalConcept] = Field(default_factory=list, max_length=60)
    relations: list[LocalRelation] = Field(default_factory=list, max_length=80)
    unresolved: list[UnresolvedItem] = Field(default_factory=list, max_length=30)


AlignmentRelation = Literal[
    "equivalent",
    "variant",
    "broader",
    "narrower",
    "related",
    "conflict",
    "insufficient",
]


class AlignmentDecision(StrictModel):
    candidate_ref: str
    relation: AlignmentRelation
    explanation: str
    matching_evidence: list[str] = Field(default_factory=list)
    important_differences: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    recommended_action: Literal[
        "keep_separate",
        "record_relation_only",
        "eligible_for_department_merge",
        "needs_review",
    ]


class AlignmentBatchResult(StrictModel):
    schema_version: Literal["department-alignment-v1"]
    batch_ref: str
    department_ref: str
    decisions: list[AlignmentDecision] = Field(default_factory=list)


class AgentMetricPlan(StrictModel):
    metric_label: str | None = None
    expression: str | None = None
    aggregation: str | None = None
    numerator: str | None = None
    denominator: str | None = None
    filters: list[str] = Field(default_factory=list)
    group_by: list[str] = Field(default_factory=list)
    unit: str | None = None


class AgentAnswer(StrictModel):
    schema_version: Literal["agent-answer-v1"]
    question_id: str
    decision: Literal["answer", "clarify", "insufficient"]
    answer: str
    report_refs: list[str] = Field(default_factory=list)
    component_refs: list[str] = Field(default_factory=list)
    dataset_refs: list[str] = Field(default_factory=list)
    tables: list[str] = Field(default_factory=list)
    fields: list[str] = Field(default_factory=list)
    metric_plan: AgentMetricPlan | None = None
    sql: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)

