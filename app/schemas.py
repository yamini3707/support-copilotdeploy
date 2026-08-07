"""Request / response models for the API."""

from pydantic import BaseModel, Field


class TicketRequest(BaseModel):
    ticket: str = Field(..., min_length=1, max_length=8000, description="the customer's message")
    customer_id: str = Field(..., description="the AUTHENTICATED customer id (drives access control + memory)")
    plan: str | None = Field(None, description="free | pro | business | enterprise")
    region: str | None = None
    form_memory: bool = Field(True, description="write this ticket into long-term memory when it ends")


class TicketResponse(BaseModel):
    category: str
    priority: str
    requires_human: bool
    confidence: float
    answer: str
    citations: list = []
    tool_calls: list = []
    trace: dict = {}
