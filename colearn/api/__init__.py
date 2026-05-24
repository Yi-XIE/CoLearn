"""CoLearn API entrypoints."""

__all__ = ["app"]


def __getattr__(name: str):
    if name == "app":
        from .app import app

        return app
    raise AttributeError(name)
