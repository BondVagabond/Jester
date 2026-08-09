from pydantic import BaseModel, ConfigDict, Field


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    version: int = Field(default=2, ge=1)
