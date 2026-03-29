from datetime import datetime
from typing import Optional
from tortoise import Tortoise
from src.models import Camera, VideoChunk
from aioboto3 import Session

import asyncio
import uvloop
import os
import re
import aiofiles


MINIO_CONFIG = {
    "endpoint_url": "http://virtual-dvr-storage:9000",
    "aws_access_key_id": "dvr_user",
    "aws_secret_access_key": "dvr_pass",
}


async def get_chunk_duration(filepath) -> int:
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        filepath
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        print(f"Erro ao ler duração: {stderr.decode()}")
        return 10000

    try:
        duration = float(stdout.decode().strip())
        return int(duration * 1000)

    except (ValueError, TypeError):
        return 10000


async def save_video(camera: Camera, path_storage: str, filename: str, record_time_str: str):
    session = Session()

    async with session.client("s3", **MINIO_CONFIG) as s3:
        try:
            async with aiofiles.open(filename, mode='rb') as fd:
                content = await fd.read()

            await s3.put_object(
                Bucket='cameras',
                Key=path_storage,
                Body=content,
                ContentType="video/mp4"
            )

            print(f"✅ Upload concluído: {filename}")

        except Exception as e:
            print(f"❌ Erro no upload de {filename}: {e}")
            return

    duration = await get_chunk_duration(filename)

    await VideoChunk.create(
        record_time=datetime.strptime(record_time_str.replace('.mp4', ''), "%Y-%m-%d_%H-%M-%S"),
        duration=duration,
        path=filename,
        url=path_storage,
        is_saved=True,
        camera=camera
    )

    os.remove(filename)

async def task_monitor_output(camera: Camera, stdout: asyncio.StreamReader):
    pattern = re.compile(r"Opening '(.+?)' for writing")
    first = True
    last_video_chunk: Optional[str] = None

    while True:
        line = await stdout.readline()
        if not line:
            break

        text = line.decode().strip()
        search = pattern.search(text)

        if search:
            path_file = search.group(1)
            print(f"[{camera.name}] New chunk detected: {path_file}")

            if first:
                last_video_chunk = path_file
                first = False
                continue

            camera_slug, record_time_str = os.path.split(last_video_chunk)
            record_time = datetime.strptime(record_time_str[:13], "%Y-%m-%d_%H")

            new_path = os.path.join(
                camera_slug,
                record_time.strftime("%Y"),
                record_time.strftime("%m"),
                record_time.strftime("%d"),
                record_time.strftime("%H"),
                record_time_str[14:]
            )

            print(f"save file: {new_path}")
            asyncio.create_task(save_video(camera, new_path, last_video_chunk, record_time_str))
            last_video_chunk = path_file

async def task_camera_manager(camera: Camera, chunk_size: int = 10):
    path = f'records/{camera.slug}'
    name = camera.name

    if not os.path.isdir(path):
        os.makedirs(path)

    """
    ffmpeg -rtsp_transport udp -buffer_size 1024000 -i "rtsp://admin:27121414As@192.168.1.8:554/onvif1" \
    -c:v copy -c:a aac -f segment -segment_time 15 -strftime 1 \
    "gravacoes/%Y-%m-%d_%H-%M-%S.mp4"
    """

    cmd = [
        "ffmpeg", "-rtsp_transport", "udp", "-buffer_size", "1024000",  "-i", camera.rtsp_url,
        "-c:v", "copy", "-c:a", "aac", "-f", "segment", "-segment_time", str(chunk_size), "-strftime", "1",
        f"{path}/%Y-%m-%d_%H-%M-%S.mp4"
    ]

    while True:
        process = await asyncio.create_subprocess_exec(
            *cmd, stderr=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.DEVNULL)

        print(f"[{name}] FFmpeg stream reader started.")

        task_monitor = asyncio.create_task(task_monitor_output(camera, process.stderr))
        await process.wait()

        print(f"[{name}] FFmpeg stream reader ended, restarted")
        task_monitor.cancel()
        await asyncio.sleep(2)


async def main():
    url = 'asyncpg://dvr_user:dvr_pass@virtual-dvr-database:5432/VIRTUAL_DVR'
    await Tortoise.init(db_url=url, modules={"models": ["src.models"]})
    await Tortoise.generate_schemas()

    cameras = await Camera.filter(is_active=True)

    tasks = [task_camera_manager(camera) for camera in cameras]
    await asyncio.gather(*tasks)


if __name__ == '__main__':
    uvloop.run(main(), debug=True)
