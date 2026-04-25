import pytest
from lower_third.motion.motion_ir import (
    AnimationTrack, ElementDef, EasingConfig, EasingType,
    Keyframe, LoopConfig, MotionIR, TickerItem,
)
from lower_third.motion.ticker_corrector import correct_ticker_widths, CANVAS_WIDTH_PX
from lower_third.renderer.text_measurer import SCROLL_SPEED_PX_S


def _bar() -> ElementDef:
    return ElementDef(id="bar", type="rect", x=0, y=960, w=1920, h=60, fill="#1A1A2E")


def _ticker_element(content: str = "Breaking News  •  More updates here  •  ") -> ElementDef:
    return ElementDef(
        id="ticker", type="text",
        content=content,
        repeat_content=False,
        x=1920, y=972,
        fill="#FFFFFF", font_size=32,
        clip_to="bar",
    )


def _non_ticker_element() -> ElementDef:
    return ElementDef(
        id="h1", type="text",
        content="Regular headline",
        repeat_content=False,
        x=24, y=972,
        fill="#FFFFFF", font_size=32,
        clip_to="bar",
    )


def _ticker_track(endpoint: float = -9999.0) -> AnimationTrack:
    return AnimationTrack(
        element_id="ticker",
        property="text_x_offset",
        keyframes=[
            Keyframe(t_ms=0, value=0.0, easing=EasingConfig(type=EasingType.linear)),
            Keyframe(t_ms=99000, value=endpoint),
        ],
    )


def _make_ir(
    include_ticker: bool = True,
    include_non_ticker: bool = False,
    include_ticker_track: bool = True,
    ticker_content: str = "Breaking News  •  More updates here  •  ",
    total_ms: int = 3600000,
    loop_after_ms: int | None = None,
) -> MotionIR:
    elements = [_bar()]
    tracks = []

    if include_non_ticker:
        elements.append(_non_ticker_element())

    if include_ticker:
        elements.append(_ticker_element(ticker_content))
        if include_ticker_track:
            tracks.append(_ticker_track())

    return MotionIR(
        elements=elements,
        tracks=tracks,
        total_ms=total_ms,
        loop=LoopConfig(enabled=True, count=0, type="restart", loop_after_ms=loop_after_ms),
    )


# ── Basic contract ────────────────────────────────────────────────────────────

def test_returns_motion_ir():
    ir = _make_ir()
    result = correct_ticker_widths(ir)
    assert isinstance(result, MotionIR)


def test_no_ticker_elements_returns_unchanged():
    ir = _make_ir(include_ticker=False)
    result = correct_ticker_widths(ir)
    assert result is ir


def test_non_ticker_element_unchanged():
    ir = _make_ir(include_non_ticker=True)
    result = correct_ticker_widths(ir)
    non_ticker_before = next(e for e in ir.elements if e.id == "h1")
    non_ticker_after = next(e for e in result.elements if e.id == "h1")
    assert non_ticker_before == non_ticker_after


def test_total_ms_unchanged():
    ir = _make_ir(total_ms=3600000)
    result = correct_ticker_widths(ir)
    assert result.total_ms == 3600000


# ── text_x_offset track patching ─────────────────────────────────────────────

def test_final_keyframe_value_is_negative():
    ir = _make_ir()
    result = correct_ticker_widths(ir)
    track = next(t for t in result.tracks if t.property == "text_x_offset")
    final_kf = max(track.keyframes, key=lambda k: k.t_ms)
    assert final_kf.value < 0.0


def test_final_keyframe_value_is_patched():
    ir = _make_ir()
    result = correct_ticker_widths(ir)
    track = next(t for t in result.tracks if t.property == "text_x_offset")
    final_kf = max(track.keyframes, key=lambda k: k.t_ms)
    assert final_kf.value != -9999.0


# ── Loop timing ───────────────────────────────────────────────────────────────

def test_loop_after_ms_is_set():
    ir = _make_ir()
    result = correct_ticker_widths(ir)
    assert result.loop.loop_after_ms is not None


def test_loop_after_ms_matches_scroll_duration():
    ir = _make_ir()
    result = correct_ticker_widths(ir)
    track = next(t for t in result.tracks if t.property == "text_x_offset")
    final_kf = max(track.keyframes, key=lambda k: k.t_ms)
    true_width = abs(final_kf.value)
    expected_scroll_ms = max(1000, int((true_width / SCROLL_SPEED_PX_S) * 1000))
    assert abs(result.loop.loop_after_ms - expected_scroll_ms) <= 10


def test_loop_after_ms_not_equal_to_total_ms():
    ir = _make_ir(total_ms=3600000)
    result = correct_ticker_widths(ir)
    assert result.loop.loop_after_ms != result.total_ms


# ── Edge cases ────────────────────────────────────────────────────────────────

def test_repeat_content_false_not_treated_as_ticker():
    elements = [_bar(), _non_ticker_element()]
    ir = MotionIR(
        elements=elements,
        tracks=[],
        total_ms=5000,
    )
    result = correct_ticker_widths(ir)
    assert result is ir


def test_ticker_element_no_offset_track_no_crash():
    # Element with no text_x_offset track is not detected as a ticker; no processing occurs.
    ir = _make_ir(include_ticker_track=False)
    result = correct_ticker_widths(ir)
    assert isinstance(result, MotionIR)
    assert result is ir


def test_idempotent():
    ir = _make_ir()
    result1 = correct_ticker_widths(ir)
    result2 = correct_ticker_widths(result1)
    track1 = next(t for t in result1.tracks if t.property == "text_x_offset")
    track2 = next(t for t in result2.tracks if t.property == "text_x_offset")
    final1 = max(track1.keyframes, key=lambda k: k.t_ms)
    final2 = max(track2.keyframes, key=lambda k: k.t_ms)
    assert abs(final1.value - final2.value) < 0.01
    assert result1.loop.loop_after_ms == result2.loop.loop_after_ms


# ── x alignment to clip bar right edge ───────────────────────────────────────

def test_ticker_x_aligned_to_clip_bar_right():
    bar = ElementDef(id="bar", type="rect", x=100, y=960, w=1500, h=60, fill="#1A1A2E")
    ticker = ElementDef(
        id="ticker", type="text",
        content="News line  •  ",
        repeat_content=False,
        x=1920, y=972,
        fill="#FFFFFF", font_size=32,
        clip_to="bar",
    )
    track = AnimationTrack(
        element_id="ticker", property="text_x_offset",
        keyframes=[
            Keyframe(t_ms=0, value=0.0, easing=EasingConfig(type=EasingType.linear)),
            Keyframe(t_ms=10000, value=-999.0),
        ],
    )
    ir = MotionIR(
        elements=[bar, ticker], tracks=[track], total_ms=3600000,
        loop=LoopConfig(enabled=True, count=0, type="restart"),
    )
    result = correct_ticker_widths(ir)
    ticker_out = next(e for e in result.elements if e.id == "ticker")
    # bar_right = 100 + 1500 = 1600; x should be corrected to 1600
    assert ticker_out.x == pytest.approx(1600.0)


def test_ticker_x_unchanged_when_no_clip_bar():
    ticker = ElementDef(
        id="ticker", type="text",
        content="News line  •  ",
        repeat_content=False,
        x=1920, y=972,
        fill="#FFFFFF", font_size=32,
    )
    track = AnimationTrack(
        element_id="ticker", property="text_x_offset",
        keyframes=[
            Keyframe(t_ms=0, value=0.0, easing=EasingConfig(type=EasingType.linear)),
            Keyframe(t_ms=10000, value=-999.0),
        ],
    )
    ir = MotionIR(
        elements=[ticker], tracks=[track], total_ms=3600000,
        loop=LoopConfig(enabled=True, count=0, type="restart"),
    )
    result = correct_ticker_widths(ir)
    ticker_out = next(e for e in result.elements if e.id == "ticker")
    assert ticker_out.x == pytest.approx(1920.0)


# ── ticker_items pre-processing ───────────────────────────────────────────────

def _make_ticker_items_ir(pause_ms: int = 1000) -> MotionIR:
    bar = _bar()
    ticker = ElementDef(
        id="ticker", type="text",
        ticker_items=[
            TickerItem(text="First headline", pause_after_ms=pause_ms),
            TickerItem(text="Second headline", pause_after_ms=pause_ms),
            TickerItem(text="Third headline", pause_after_ms=pause_ms),
        ],
        x=1920, y=972,
        fill="#FFFFFF", font_size=32,
        clip_to="bar",
    )
    track = AnimationTrack(
        element_id="ticker", property="text_x_offset",
        keyframes=[
            Keyframe(t_ms=0, value=0.0, easing=EasingConfig(type=EasingType.linear)),
            Keyframe(t_ms=99000, value=-9999.0),
        ],
    )
    return MotionIR(
        elements=[bar, ticker], tracks=[track], total_ms=3600000,
        loop=LoopConfig(enabled=True, count=0, type="restart"),
    )


def test_ticker_items_produces_content():
    ir = _make_ticker_items_ir()
    result = correct_ticker_widths(ir)
    ticker_out = next(e for e in result.elements if e.id == "ticker")
    assert ticker_out.content is not None
    assert "First headline" in ticker_out.content
    assert "Second headline" in ticker_out.content
    assert "Third headline" in ticker_out.content


def test_ticker_items_sets_repeat_content_false():
    ir = _make_ticker_items_ir()
    result = correct_ticker_widths(ir)
    ticker_out = next(e for e in result.elements if e.id == "ticker")
    assert ticker_out.repeat_content is False


def test_ticker_items_clears_ticker_items_field():
    ir = _make_ticker_items_ir()
    result = correct_ticker_widths(ir)
    ticker_out = next(e for e in result.elements if e.id == "ticker")
    assert ticker_out.ticker_items is None


def test_ticker_items_gap_increases_with_pause():
    ir_short = _make_ticker_items_ir(pause_ms=500)
    ir_long = _make_ticker_items_ir(pause_ms=2000)
    r_short = correct_ticker_widths(ir_short)
    r_long = correct_ticker_widths(ir_long)
    c_short = next(e for e in r_short.elements if e.id == "ticker").content
    c_long = next(e for e in r_long.elements if e.id == "ticker").content
    assert len(c_long) > len(c_short)


def test_ticker_items_loop_after_ms_set():
    ir = _make_ticker_items_ir()
    result = correct_ticker_widths(ir)
    assert result.loop.loop_after_ms is not None
    assert result.loop.loop_after_ms > 0


def test_ticker_corrector_works_with_repeat_content_false():
    """Ticker identified by text_x_offset track presence, not repeat_content flag."""
    ticker = ElementDef(
        id="ticker", type="text",
        content="Alpha  •  Beta  •  Gamma  •  ",
        repeat_content=False,
        x=1920, y=972,
        fill="#FFFFFF", font_size=32,
    )
    track = AnimationTrack(
        element_id="ticker", property="text_x_offset",
        keyframes=[
            Keyframe(t_ms=0, value=0.0, easing=EasingConfig(type=EasingType.linear)),
            Keyframe(t_ms=99000, value=-9999.0),
        ],
    )
    ir = MotionIR(
        elements=[ticker], tracks=[track], total_ms=3600000,
        loop=LoopConfig(enabled=True, count=0, type="restart"),
    )
    result = correct_ticker_widths(ir)
    assert isinstance(result, MotionIR)
    out_track = next(t for t in result.tracks if t.property == "text_x_offset")
    final_kf = max(out_track.keyframes, key=lambda k: k.t_ms)
    # Final value must be negative and larger in magnitude than text width alone
    # (proving CANVAS_WIDTH_PX=1920 is included in the travel calculation)
    assert final_kf.value < 0.0
    assert abs(final_kf.value) > CANVAS_WIDTH_PX
