import pytest
from lower_third.choreography.brand_resolver import (
    resolve_brand, clamp_to_broadcast_safe,
    ResolvedBrand, DEFAULT_BAR_COLOUR, DEFAULT_TEXT_COLOUR
)


def test_resolve_brand_returns_resolved_brand():
    result = resolve_brand({})
    assert isinstance(result, ResolvedBrand)


def test_canvas_dimensions_always_1920_1080():
    result = resolve_brand({})
    assert result.canvas_w == 1920
    assert result.canvas_h == 1080


def test_bar_height_one_line():
    result = resolve_brand({}, estimated_lines=1)
    # bar_h = LABEL_ROW_H + TICKER_ROW_H = 56 + 80 = 136 (fixed, independent of estimated_lines)
    assert result.bar_h == 136


def test_bar_height_two_lines():
    result = resolve_brand({}, estimated_lines=2)
    # bar_h is fixed at LABEL_ROW_H + TICKER_ROW_H = 136
    assert result.bar_h == 136


def test_bar_height_three_lines():
    result = resolve_brand({}, estimated_lines=3)
    # bar_h is fixed at LABEL_ROW_H + TICKER_ROW_H = 136
    assert result.bar_h == 136


def test_bar_y_no_avoid_zone():
    result = resolve_brand({}, estimated_lines=1)
    # bar_h=136, no bottom margin: bar_y = max(1080 - 136, 20) = 944
    assert result.bar_y == 944


def test_bar_y_respects_anchor_avoid_zone():
    upstream = {"anchor_avoid_zone": {"x": 0, "y": 800, "w": 1920, "h": 200}}
    result = resolve_brand(upstream, estimated_lines=1)
    # anchor_avoid_zone_bottom = 800 + 200 = 1000
    # normal bar_y = 1080 - 136 = 944, but 944 < 1000 + 20 = 1020
    # so bar_y = max(944, 1020) = 1020
    assert result.bar_y == 1020


def test_bar_y_uses_larger_of_two_values():
    upstream = {"anchor_avoid_zone": {"x": 0, "y": 100, "w": 200, "h": 50}}
    result = resolve_brand(upstream, estimated_lines=1)
    # anchor_avoid_zone_bottom = 150, 150+20=170
    # normal bar_y = 1080 - 136 = 944
    # max(944, 170) = 944
    assert result.bar_y == 944


def test_style_token_resolves_bar_colour():
    upstream = {"lower_third_style": "bold_red_bar"}
    result = resolve_brand(upstream)
    # bold_red_bar → #CC0000 → after clamping should be close to red
    assert result.bar_color.startswith("#")
    r = int(result.bar_color[1:3], 16)
    g = int(result.bar_color[3:5], 16)
    b = int(result.bar_color[5:7], 16)
    assert r > g and r > b   # red channel dominant


def test_unknown_style_token_uses_default():
    upstream = {"lower_third_style": "nonexistent_style"}
    result = resolve_brand(upstream)
    assert result.bar_color is not None
    assert len(result.bar_color) == 7
    assert result.bar_color.startswith("#")


def test_missing_upstream_signals_uses_defaults():
    result = resolve_brand({})
    assert result.bar_color is not None
    assert result.text_color is not None


def test_clamp_pure_white_stays_near_white():
    result = clamp_to_broadcast_safe("#FFFFFF")
    r = int(result[1:3], 16)
    g = int(result[3:5], 16)
    b = int(result[5:7], 16)
    assert r == 235 and g == 235 and b == 235


def test_clamp_pure_black_maps_to_luma_min():
    result = clamp_to_broadcast_safe("#000000")
    r = int(result[1:3], 16)
    g = int(result[3:5], 16)
    b = int(result[5:7], 16)
    assert r == 16 and g == 16 and b == 16


def test_clamp_output_is_valid_hex():
    result = clamp_to_broadcast_safe("#CC0000")
    assert result.startswith("#")
    assert len(result) == 7
    int(result[1:], 16)   # must not raise


def test_clamp_invalid_input_returns_default():
    result = clamp_to_broadcast_safe("not-a-color")
    assert result == DEFAULT_BAR_COLOUR


def test_clamp_preserves_colour_channel_ordering():
    # A colour with high R, low G, low B should stay R > G, R > B after clamping
    result = clamp_to_broadcast_safe("#FF1010")
    r = int(result[1:3], 16)
    g = int(result[3:5], 16)
    b = int(result[5:7], 16)
    assert r > g and r > b


def test_resolved_brand_colours_are_broadcast_safe():
    result = resolve_brand({"lower_third_style": "bold_red_bar"})
    for hex_color in [result.bar_color, result.text_color]:
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
        for ch in [r, g, b]:
            assert 16 <= ch <= 235, f"Channel {ch} out of broadcast range in {hex_color}"


def test_font_sizes_loaded_from_constants():
    result = resolve_brand({})
    assert result.font_size_headline == 32
    assert result.font_size_kicker   == 22
    assert result.font_size_name     == 38
    assert result.font_size_title    == 28
