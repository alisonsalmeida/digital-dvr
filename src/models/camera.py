from tortoise import fields, models
from pydantic import BaseModel
from datetime import datetime


class Camera(models.Model):
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=100)
    slug = fields.CharField(max_length=50, unique=True, index=True)
    rtsp_url = fields.CharField(max_length=255)
    is_active = fields.BooleanField(default=True)

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "cameras"

    def __str__(self):
        return f"Camera {self.slug}: {self.name}"


class CameraModel(BaseModel):
    id: int
    name: str
    slug: str
    rtsp_url: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
