from pydantic import BaseModel, Field
from uuid import UUID
from datetime import date, datetime
from typing import Optional, List, Any

class PrescriptionItemBase(BaseModel):
    medication_name: str
    active_ingredient: Optional[str] = None
    dosage: str
    form: Optional[str] = None
    frequency: str
    frequency_per_day: Optional[int] = None
    scheduled_times: Optional[List[str]] = None
    duration_days: Optional[int] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    instructions: Optional[str] = None
    before_food: Optional[bool] = None
    doctor_notes: Optional[str] = None
    quantity_prescribed: Optional[int] = None
    refills_remaining: Optional[int] = None
    stock_remaining: Optional[int] = None
    stock_reminder_enabled: bool = False
    stock_reminder_threshold: int = 10

class MedicationStockUpdate(BaseModel):
    stock_remaining: Optional[int] = Field(default=None, ge=0, le=100000)
    stock_reminder_enabled: bool = False
    stock_reminder_threshold: int = Field(default=10, ge=1, le=100000)

class PrescriptionItemResponse(PrescriptionItemBase):
    id: UUID
    prescription_id: UUID
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
