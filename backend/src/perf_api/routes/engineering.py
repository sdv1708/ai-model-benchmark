"""HTTP boundary for the engineering analysis endpoint."""

from fastapi import APIRouter

from perf_api.engineering import analyze_engineering
from perf_api.engineering_schemas import EngineeringAnalysisRequest, EngineeringAnalysisResponse

router = APIRouter(prefix="/api/v1/engineering", tags=["engineering"])


@router.post("/analyze", response_model=EngineeringAnalysisResponse)
def analyze_engineering_request(
    request: EngineeringAnalysisRequest,
) -> EngineeringAnalysisResponse:
    """Expose engineering diagnostics for normalized workbooks."""
    return analyze_engineering(request.workbooks)
