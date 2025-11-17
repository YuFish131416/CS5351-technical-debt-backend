# app/analysis/base.py
from abc import ABC, abstractmethod
from typing import Dict


class BaseAnalyzer(ABC):
    """分析器抽象基类，允许子类接收额外的上下文参数"""

    @abstractmethod
    async def analyze(self, project_path: str, **kwargs) -> Dict:
        raise NotImplementedError