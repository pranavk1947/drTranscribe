from pydantic import BaseModel, Field, field_validator


class Patient(BaseModel):
    """Patient information model."""
    
    name: str = Field(..., min_length=1, max_length=200)
    age: int = Field(..., ge=0, le=150)
    gender: str = Field(..., min_length=1, max_length=50)
    
    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v.strip():
            raise ValueError('Name cannot be empty')
        return v.strip()
    
    @field_validator('gender')
    @classmethod
    def validate_gender(cls, v: str) -> str:
        if not v.strip():
            raise ValueError('Gender cannot be empty')
        return v.strip()
