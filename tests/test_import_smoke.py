def test_import_package_and_server():
    import scribetex  # noqa: F401
    from scribetex import server  # noqa: F401
    assert hasattr(server, "mcp")
    assert hasattr(server, "main")
