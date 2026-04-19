import os
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from lower_third.parser.prompt_schema import LowerThirdSpec, ContentMode
from lower_third.motion.motion_ir import MotionIR, ElementDef, LoopConfig
from lower_third.choreography.brand_resolver import resolve_brand

BRAND = resolve_brand({}, estimated_lines=2)


def _minimal_spec() -> LowerThirdSpec:
    elem = ElementDef(id="bar", type="rect", x=0, y=960, w=1920, h=60, fill="#1a1a2e")
    ir   = MotionIR(elements=[elem], tracks=[], total_ms=5000)
    return LowerThirdSpec(motion=ir)


def test_system_prompt_file_exists():
    path = Path(__file__).resolve().parent.parent / "parser" / "system_prompt.txt"
    assert path.exists(), "system_prompt.txt not found"


def test_system_prompt_contains_required_sections():
    path = Path(__file__).resolve().parent.parent / "parser" / "system_prompt.txt"
    text = path.read_text()
    for keyword in ["CANVAS", "BAR", "EASING", "LOOP", "NEVER GENERATE", "OUTPUT SCHEMA"]:
        assert keyword in text, f"system_prompt.txt missing section: {keyword}"


def test_system_prompt_has_format_placeholders():
    path = Path(__file__).resolve().parent.parent / "parser" / "system_prompt.txt"
    text = path.read_text()
    for placeholder in ["{canvas_w}", "{canvas_h}", "{bar_y}", "{bar_h}",
                         "{bar_color}", "{text_color}", "{font_size_headline}"]:
        assert placeholder in text, f"Missing placeholder: {placeholder}"


def test_load_system_prompt_formats_without_error():
    from lower_third.parser.llm_parser import _load_system_prompt
    result = _load_system_prompt(BRAND)
    assert isinstance(result, str)
    assert len(result) > 100
    assert "{bar_y}" not in result    # placeholders must be replaced
    assert "{canvas_w}" not in result


def test_load_system_prompt_injects_bar_y():
    from lower_third.parser.llm_parser import _load_system_prompt
    result = _load_system_prompt(BRAND)
    assert str(BRAND.bar_y) in result


def test_parse_prompt_calls_groq_first():
    from lower_third.parser import llm_parser
    mock_spec = _minimal_spec()
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_spec
    with patch.object(llm_parser, "_make_groq_client", return_value=mock_client):
        result = llm_parser.parse_prompt("test prompt", BRAND)
    mock_client.chat.completions.create.assert_called_once()
    assert isinstance(result, LowerThirdSpec)


def test_parse_prompt_falls_back_to_ollama_on_rate_limit():
    from lower_third.parser import llm_parser
    from groq import RateLimitError
    mock_spec = _minimal_spec()
    mock_groq   = MagicMock()
    mock_ollama = MagicMock()
    mock_groq.chat.completions.create.side_effect = RateLimitError(
        message="rate limited", response=MagicMock(status_code=429), body={}
    )
    mock_ollama.chat.completions.create.return_value = mock_spec
    with patch.object(llm_parser, "_make_groq_client",   return_value=mock_groq), \
         patch.object(llm_parser, "_make_ollama_client", return_value=mock_ollama):
        result = llm_parser.parse_prompt("test prompt", BRAND)
    assert isinstance(result, LowerThirdSpec)
    mock_ollama.chat.completions.create.assert_called_once()


def test_parse_prompt_raises_when_both_fail():
    from lower_third.parser import llm_parser
    from groq import RateLimitError
    mock_groq   = MagicMock()
    mock_ollama = MagicMock()
    mock_groq.chat.completions.create.side_effect = RateLimitError(
        message="rate limited", response=MagicMock(status_code=429), body={}
    )
    mock_ollama.chat.completions.create.side_effect = Exception("Ollama down")
    with patch.object(llm_parser, "_make_groq_client",   return_value=mock_groq), \
         patch.object(llm_parser, "_make_ollama_client", return_value=mock_ollama):
        with pytest.raises(RuntimeError, match="LLM parsing failed"):
            llm_parser.parse_prompt("test prompt", BRAND)


def test_parse_prompt_does_not_set_instance_id():
    from lower_third.parser import llm_parser
    mock_spec = _minimal_spec()
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_spec
    with patch.object(llm_parser, "_make_groq_client", return_value=mock_client):
        result = llm_parser.parse_prompt("test prompt", BRAND)
    assert result.instance_id is None


def test_parse_prompt_does_not_set_schema_version_explicitly():
    from lower_third.parser import llm_parser
    mock_spec = _minimal_spec()
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_spec
    with patch.object(llm_parser, "_make_groq_client", return_value=mock_client):
        result = llm_parser.parse_prompt("test prompt", BRAND)
    assert result.schema_version == "2.0"


def test_make_groq_client_requires_api_key():
    from lower_third.parser.llm_parser import _make_groq_client
    with patch.dict(os.environ, {}, clear=True):
        if "GROQ_API_KEY" in os.environ:
            del os.environ["GROQ_API_KEY"]
        with pytest.raises(Exception):
            _make_groq_client("llama-3.3-70b-versatile")


def test_make_ollama_client_returns_instructor():
    from lower_third.parser.llm_parser import _make_ollama_client
    import instructor
    client = _make_ollama_client("http://localhost:11434/v1")
    assert hasattr(client, "chat")
