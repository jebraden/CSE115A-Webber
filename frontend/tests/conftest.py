import asyncio
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtAsyncio import QAsyncioEventLoop
from .async_support import run


@pytest.fixture(autouse=True)
def gui_asyncio_loop(request):
    if request.module.__name__.rsplit('.', 1)[-1] not in {
        'test_main_window', 'test_central_integration',
    }:
        yield
        return
    app = QApplication.instance() or QApplication([])
    quit_on_close = app.quitOnLastWindowClosed()
    app.setQuitOnLastWindowClosed(False)
    policy = asyncio.get_event_loop_policy()
    loop = QAsyncioEventLoop(app, quit_qapp=False)
    asyncio.set_event_loop(loop)
    try:
        yield
    finally:
        async def clean_up():
            tasks = [task for task in asyncio.all_tasks(loop) if task is not asyncio.current_task()]
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await loop.shutdown_default_executor()
        run(app, clean_up())
        loop.close()
        asyncio.set_event_loop_policy(policy)
        app.setQuitOnLastWindowClosed(quit_on_close)
