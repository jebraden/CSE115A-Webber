"""Archive submission UI and backend error presentation for task 2.3.1."""
def __getattr__(name):
    # API/service consumers can import errors without importing Qt widgets.
    if name == "ArchiveRequestDialog":
        from .dialog import ArchiveRequestDialog
        return ArchiveRequestDialog
    raise AttributeError(name)

__all__ = ["ArchiveRequestDialog"]
