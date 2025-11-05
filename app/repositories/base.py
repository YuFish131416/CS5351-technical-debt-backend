# app/repositories/base.py
from typing import List, Optional, TypeVar, Generic
from sqlalchemy.orm import Session
from app.core.database import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    def __init__(self, model: type[ModelType], db: Session):
        self.model = model
        self.db = db

    def get(self, id: int) -> Optional[ModelType]:
        return self.db.query(self.model).filter(self.model.id == id).first()

    def create(self, obj_in: dict) -> ModelType:
        obj = self.model(**obj_in)
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def update(self, id: int, obj_in: dict) -> Optional[ModelType]:
        obj = self.get(id)
        if obj:
            for field, value in obj_in.items():
                setattr(obj, field, value)
            self.db.commit()
            self.db.refresh(obj)
        return obj