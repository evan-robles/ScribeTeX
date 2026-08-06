def test_automation_package_imports():
    import automation
    assert hasattr(automation, "__version__")
