import asyncio
from threading import Lock

camera_lock = Lock()


async def camera_transaction():
    while not camera_lock.acquire(blocking=False):
        await asyncio.sleep(0.02)
    try:
        yield
    finally:
        camera_lock.release()
