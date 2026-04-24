def list_supported_sources() -> list[str]:
    from .registry import list_supported_sources as _list_supported_sources

    return _list_supported_sources()


__all__ = ["list_supported_sources"]
