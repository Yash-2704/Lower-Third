import pytest


def _cairo_available() -> bool:
    try:
        import cairocffi  # noqa: F401
        import pangocffi  # noqa: F401
        return True
    except (ImportError, OSError):
        return False


# ── Non-Cairo tests (always run) ─────────────────────────────────────────────

def test_empty_string_returns_zero():
    from lower_third.renderer.text_measurer import measure_text_width
    assert measure_text_width("") == 0.0


def test_none_returns_zero():
    from lower_third.renderer.text_measurer import measure_text_width
    assert measure_text_width(None) == 0.0


def test_invalid_font_size_raises():
    from lower_third.renderer.text_measurer import measure_text_width
    with pytest.raises(ValueError, match="font_size must be > 0"):
        measure_text_width("Hello", font_size=0)

    with pytest.raises(ValueError, match="font_size must be > 0"):
        measure_text_width("Hello", font_size=-1)


def test_scroll_speed_importable():
    from lower_third.renderer.text_measurer import SCROLL_SPEED_PX_S
    assert SCROLL_SPEED_PX_S == 150.0


def test_return_type_is_float():
    from lower_third.renderer.text_measurer import measure_text_width
    result = measure_text_width("Hello")
    assert isinstance(result, float)


# ── Cairo-dependent tests ─────────────────────────────────────────────────────

def test_hello_returns_positive():
    if not _cairo_available():
        pytest.skip("cairocffi/pangocffi not installed")
    from lower_third.renderer.text_measurer import measure_text_width
    assert measure_text_width("Hello") > 0.0


def test_wide_chars_wider_than_narrow():
    if not _cairo_available():
        pytest.skip("cairocffi/pangocffi not installed")
    from lower_third.renderer.text_measurer import measure_text_width
    assert measure_text_width("WWW", font_size=32) > measure_text_width("iii", font_size=32)


def test_larger_font_gives_wider_result():
    if not _cairo_available():
        pytest.skip("cairocffi/pangocffi not installed")
    from lower_third.renderer.text_measurer import measure_text_width
    assert measure_text_width("Hello", font_size=64) > measure_text_width("Hello", font_size=32)


def test_bold_not_narrower_than_regular():
    if not _cairo_available():
        pytest.skip("cairocffi/pangocffi not installed")
    from lower_third.renderer.text_measurer import measure_text_width
    assert measure_text_width("Hello", font_weight="bold") >= measure_text_width("Hello", font_weight="regular")
