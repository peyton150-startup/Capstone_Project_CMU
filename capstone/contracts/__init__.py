"""Shared observable data and research artifacts; never simulator truth."""

from pydantic import BaseModel, ConfigDict


class Contract(BaseModel):
    """Immutable, explicit fields; unknown data cannot silently cross boundaries."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
