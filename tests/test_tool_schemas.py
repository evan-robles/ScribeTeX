import asyncio
from scribetex import server

EXPECTED = {
    "prepare_note": {"source", "ref"},
    "resolve_placement": {"course_hint", "section_hint", "subsection_hint", "date"},
    "write_section": {"course", "section_title", "subsection_title",
                      "latex_body", "date", "course_number", "on_duplicate"},
    "save_figure": {"course", "page_image", "bbox", "name"},
}


def _props(name):
    async def go():
        tool = await server.mcp.get_tool(name)
        return set(tool.parameters["properties"].keys())
    return asyncio.run(go())


def test_every_tool_exposes_expected_params():
    for name, expected in EXPECTED.items():
        props = _props(name)
        missing = expected - props
        assert not missing, f"{name} missing params: {missing} (has {props})"
