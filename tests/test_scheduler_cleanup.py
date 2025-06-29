from app.utils.scheduling import scheduler


def test_start_scheduler():
    scheduler.start()
    assert scheduler.running


def test_scheduler_reset():
    assert not scheduler.running


def test_shutdown_terminates_active_jobs(monkeypatch):
    class DummyProc:
        def __init__(self):
            self.terminated = False
            self.joined = False

        def is_alive(self):
            return True

        def terminate(self):
            self.terminated = True

        def join(self, timeout=None):
            self.joined = True

    proc = DummyProc()
    from app.utils import scheduling as sched

    sched.active_jobs["cam1"] = proc
    scheduler.shutdown(wait=False)
    assert not sched.active_jobs
    assert proc.terminated and proc.joined
