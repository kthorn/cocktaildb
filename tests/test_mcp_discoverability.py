"""The public MCP server is documented on the site and findable by agents."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "src" / "web"
MCP_URL = "https://mixology.tools/api/v1/mcp"
ABOUT_ANCHOR = "/about.html#ai-assistants"
TOOLS = ("search_recipes", "get_recipe", "find_similar_recipes", "find_ingredients")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_about_page_documents_the_mcp_server():
    about = _read(WEB / "about.html")
    assert 'id="ai-assistants"' in about
    assert MCP_URL in about
    for tool in TOOLS:
        assert tool in about


def test_llms_txt_lists_the_mcp_server():
    llms = _read(WEB / "public" / "llms.txt")
    assert "## MCP server" in llms
    assert MCP_URL in llms
    assert "https://mixology.tools" + ABOUT_ANCHOR in llms
    for tool in TOOLS:
        assert tool in llms


def test_robots_txt_points_agents_at_the_mcp_server():
    assert MCP_URL in _read(WEB / "public" / "robots.txt")


def test_homepage_noscript_links_to_mcp_docs():
    index = _read(WEB / "index.html")
    noscript = index[index.index("<noscript>") : index.index("</noscript>")]
    assert ABOUT_ANCHOR in noscript


def test_shared_footer_links_to_mcp_docs():
    assert ABOUT_ANCHOR in _read(WEB / "js" / "common.js")


def test_openapi_description_mentions_mcp():
    from core.config import Settings

    description = Settings().api_description
    assert "/api/v1/mcp" in description
    assert ABOUT_ANCHOR in description

