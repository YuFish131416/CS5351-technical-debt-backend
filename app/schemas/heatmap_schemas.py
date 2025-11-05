# app/schemas/heatmap_schemas.py
from typing import Dict, Any, List, Optional
from pydantic import BaseModel


class HeatmapData(BaseModel):
    """热点图数据模式"""
    file_path: str
    heat_score: float
    change_count: int
    author_count: int
    last_modified: str


class ComplexityData(BaseModel):
    """复杂度数据模式"""
    file_path: str
    avg_complexity: float
    maintainability_index: float
    lines_of_code: int
    comment_density: float
    function_count: int


class DebtScoreData(BaseModel):
    """债务分数数据模式"""
    file_path: str
    debt_score: float
    severity: str
    estimated_effort: int
    heat_metrics: Optional[Dict[str, Any]] = None
    complexity_metrics: Optional[Dict[str, Any]] = None


class AnalysisResultResponse(BaseModel):
    """分析结果响应模式"""
    git_analysis: Dict[str, HeatmapData]
    complexity_analysis: Dict[str, ComplexityData]
    debt_scores: Dict[str, DebtScoreData]
    timestamp: str
