"""
Pydantic Models for Input Validation and Output Serialization.
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Any

class StudentUploadMetadata(BaseModel):
    student_id: str = Field(..., min_length=1)
    student_name: str = Field(..., min_length=1)
    batch: str = Field(..., min_length=1)
    branch: Optional[str] = ""
    designation: Optional[str] = ""
    gender: Optional[str] = ""

    @field_validator('student_id')
    @classmethod
    def validate_id(cls, v):
        if not v.isalnum() and not '-' in v:
             # Basic check, can be more complex
             pass
        return v

class BatchResponse(BaseModel):
    batch_name: str
    id: Optional[str] = None

class AttendanceResponse(BaseModel):
    success: bool
    present_count: int
    total_detected: int
    present_students: List[str]
    missing_students: List[str]

class ErrorResponse(BaseModel):
    success: bool = False
    error: dict
