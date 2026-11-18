"""Drive the real QtAsyncio loop without closing widgets between actions."""
import asyncio
import time


def run(app, coroutine):
    loop = asyncio.get_event_loop()
    task = loop.create_task(coroutine)
    def finished(_task):
        # quit_qapp=False pauses asyncio; exit() then returns from Qt's exec()
        # without sending close events to the widgets under test.
        loop.stop()
        app.exit(0)
    task.add_done_callback(finished)
    loop.run_forever()
    return task.result()


def until(app, predicate, timeout=5):
    async def poll():
        deadline = time.monotonic() + timeout
        await asyncio.sleep(0)
        while not predicate():
            if time.monotonic() >= deadline:
                raise AssertionError("QtAsyncio operation timed out")
            await asyncio.sleep(0.005)
    return run(app, poll())
