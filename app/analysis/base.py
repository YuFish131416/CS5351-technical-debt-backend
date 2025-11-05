# app/analysis/base.py
from abc import ABC, abstractmethod
from typing import Dict, List
import asyncio

class BaseAnalyzer(ABC):
    @abstractmethod
    async def analyze(self, project_path: str) -> Dict:
        pass