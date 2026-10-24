"""Public contract for engineering diagnostics.

These shapes describe evidence, not a judgment that a projection is correct.
See backend/README.md for the calculations and their interpretation.
"""

from typing import Literal

from pydantic import BaseModel, Field

from perf_api.schemas import PerformanceRecord, WorkbookNormalizationResponse


class EngineeringAnalysisRequest(BaseModel):
    """Analyze one or more workbooks from the normalization pipeline."""

    workbooks: list[WorkbookNormalizationResponse] = Field(min_length=1)


class SourceReference(BaseModel):
    """Locate a row; optional workbook coordinates require upstream provenance."""

    model_name: str
    profile_id: str
    workbook_index: int = Field(
        ge=0, description="Zero-based index after deterministic workbook sorting"
    )
    record_index: int = Field(ge=0, description="Zero-based index in normalized records")
    filename: str | None = None
    worksheet: str | None = None
    sheet_row: int | None = Field(default=None, ge=1)


class EngineeringMetric(BaseModel):
    """A reported value with its unit and a reproducible derivation or source."""

    name: str
    value: float
    unit: str
    explanation: str


class ConfigurationDiagnostic(BaseModel):
    """Source projection and engineering observations for one configuration."""

    source: SourceReference
    record: PerformanceRecord
    metrics: list[EngineeringMetric]


class TrendDiagnostic(BaseModel):
    """A comparison between two configurations that differ on a stated dimension."""

    dimension: Literal["batch_size", "cache_percentage", "configuration"]
    baseline: SourceReference
    candidate: SourceReference
    metric_name: str
    baseline_value: float
    candidate_value: float
    unit: str
    explanation: str


class AnomalyFlag(BaseModel):
    """A review signal with the rule and source rows needed to reproduce it."""

    code: str
    rule: str
    explanation: str
    sources: list[SourceReference] = Field(min_length=1)


class EngineeringAnalysisResponse(BaseModel):
    """Engineering evidence across normalized sweeps; flags do not discard rows."""

    configurations: list[ConfigurationDiagnostic]
    trends: list[TrendDiagnostic]
    anomalies: list[AnomalyFlag]
    limitations: list[str]
