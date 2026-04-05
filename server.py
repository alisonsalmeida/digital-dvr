from sanic import Sanic, Request, response
from tortoise.contrib.sanic import register_tortoise
from src.models import Camera, CameraModel, VideoChunk
from datetime import datetime, timedelta

import aioboto3

app = Sanic("Digital-Video-Recorder")


MINIO_CONFIG = {
    "endpoint_url": "http://192.168.1.111:9000",
    "aws_access_key_id": "dvr_user",
    "aws_secret_access_key": "dvr_pass",
}


@app.get("/cameras")
async def index(request: Request):
    cameras = await Camera.all()
    cameras = [CameraModel(**dict(camera)).model_dump(mode='json') for camera in cameras]

    return response.json(cameras)


@app.get("/cameras/<camera_id>")
async def show(request: Request, camera_id: int):
    start_time_str = request.args.get("start_time")

    camera = await Camera.get_or_none(id=camera_id)
    if not camera:
        return response.json({"error": "camera not found"}, status=404)

    try:
        start_time = datetime.strptime(start_time_str, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError:
        return response.json({"error": "invalid start time"}, status=400)

    start_dt = start_time.replace(minute=0, second=0, microsecond=0)
    end_dt = start_time + timedelta(hours=1)

    chunks = VideoChunk.filter(record_time__range=(start_dt, end_dt), camera=camera_id).all()
    count = await chunks.count()

    if count == 0:
        return response.text(
            "\n".join("#EXTM3U\n#EXT-X-TARGETDURATION:0\n#EXT-X-ENDLIST"),
            content_type="application/vnd.apple.mpegurl"
        )

    session = aioboto3.Session()
    max_duration = 0
    urls = []

    async for chunk in chunks:
        async with session.client('s3', **MINIO_CONFIG) as s3:
            url = await s3.generate_presigned_url(
                'get_object',
                Params={'Bucket': 'cameras', 'Key': chunk.url},
                ExpiresIn=3600  # 1 hour
            )
            print(f"Presigned URL: {url}")
            if chunk.duration > max_duration:
                max_duration = chunk.duration

            urls.append(f"#EXTINF:{(chunk.duration / 1000):.3f},")
            urls.append(url)

    lines = [
        "#EXTM3U",
        "#EXT-X-VERSION:3",
        f"#EXT-X-TARGETDURATION:{int(max_duration / 1000) + 1}",
        "#EXT-X-MEDIA-SEQUENCE:0",
        "#EXT-X-PLAYLIST-TYPE:VOD",
    ]
    lines.extend(urls)
    lines.append("#EXT-X-ENDLIST")

    return response.text(
        "\n".join(lines),
        content_type="application/vnd.apple.mpegurl"
    )


url = 'asyncpg://dvr_user:dvr_pass@192.168.1.111:5434/VIRTUAL_DVR'
register_tortoise(
    app, db_url=url, modules={"models": ["src.models"]}
)

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8000, debug=True, auto_reload=True)
