import asyncio
from scribetex import server

EXPECTED = {
    "prepare_note": {"source", "ref"},
    "resolve_placement": {"course_hint", "date", "source_name"},
    "write_section": {"course", "latex_body", "date", "source_name",
                      "course_number", "on_duplicate"},
    "save_figure": {"course", "page_image", "bbox", "name"},
    "compile_course": {"course"},
    "patch_note_region": {"course", "note_key", "new_body"},
    "read_course": {"course"},
    "write_study_aid": {"course", "kind", "content"},
}


def _props(name):
    async def go():
        tool = await server.mcp.get_tool(name)
        return set(tool.parameters["properties"].keys())
    return asyncio.run(go())


def test_every_tool_exposes_expected_params():
    # Exact equality (not a subset check) so a renamed/added/dropped param is
    # caught, not silently tolerated.
    for name, expected in EXPECTED.items():
        props = _props(name)
        assert props == expected, f"{name} params {props} != expected {expected}"
