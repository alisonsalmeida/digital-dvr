from tortoise.models import Model
from tortoise import fields


class VideoChunk(Model):
    id = fields.IntField(pk=True)
    record_time = fields.DatetimeField()
    duration = fields.IntField()
    url = fields.CharField(max_length=255)
    path = fields.CharField(max_length=255)
    is_saved = fields.BooleanField(default=False)

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    camera = fields.ForeignKeyField('models.Camera', related_name='chunks')

    class Meta:
        table = "video_chunks"
        indexes = (("camera", "record_time"),)
