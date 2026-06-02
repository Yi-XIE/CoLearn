"""Tests for host adapter contract surfaces."""
import asyncio


class FakeLoop:
    def __init__(self):
        self.calls = []

    async def process_direct(self, content, **kwargs):
        self.calls.append((content, kwargs))
        return {"content": content, "kwargs": kwargs}


def test_process_direct_turn_runner_maps_arguments():
    """ProcessDirectTurnRunner should map run_turn to process_direct."""
    from colearn.colearn_adapters.colearn_turn_runner import ProcessDirectTurnRunner

    async def run_test():
        loop = FakeLoop()
        runner = ProcessDirectTurnRunner(loop)

        result = await runner.run_turn(
            content="hello",
            session_key="s1",
            channel="cli",
            chat_id="direct",
            media=["image.png"],
        )

        assert result["content"] == "hello"
        assert loop.calls[0][1]["session_key"] == "s1"
        assert loop.calls[0][1]["media"] == ["image.png"]

    asyncio.run(run_test())


def test_host_session_adapter_projects_metadata():
    """HostSessionAdapter should wrap session manager and project metadata."""
    from colearn.colearn_adapters.colearn_session import (
        HostSessionAdapter,
        project_colearn_session_metadata,
    )

    class Manager:
        def __init__(self):
            self.saved = None
            self.session = type("Session", (), {"metadata": {}})()

        def get_or_create(self, key):
            self.session.key = key
            return self.session

        def save(self, session, *, fsync=False):
            self.saved = (session, fsync)

    manager = Manager()
    adapter = HostSessionAdapter(manager)
    session = adapter.get_or_create("host-session")
    project_colearn_session_metadata(session, "colearn-session")
    adapter.save(session, fsync=True)

    assert session.metadata["colearn_session_id"] == "colearn-session"
    assert manager.saved == (session, True)


def test_message_adapter_reads_and_injects_context():
    """Message adapter should read messages and append system context."""
    from colearn.colearn_adapters.colearn_messages import append_system_context, read_messages

    source = {"messages": [{"role": "user", "content": "hi"}]}
    append_system_context(source, "CoLearn context")

    messages = read_messages(source)
    assert messages[-1] == {
        "role": "system",
        "content": "CoLearn context",
        "source": "colearn",
    }


def test_stream_observer_collects_and_forwards():
    """StreamObserver should collect deltas while forwarding callbacks."""
    from colearn.colearn_adapters.colearn_stream import StreamObserver

    forwarded = []
    observer = StreamObserver(on_stream=lambda delta: forwarded.append(delta))

    observer.handle_delta("你")
    observer.handle_delta("好")

    assert observer.text == "你好"
    assert forwarded == ["你", "好"]
