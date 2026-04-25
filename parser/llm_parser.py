import os
import json
import logging
from pathlib import Path

from groq import Groq, RateLimitError, APITimeoutError, APIConnectionError
from openai import OpenAI
import instructor

from lower_third.parser.prompt_schema import LowerThirdSpec
from lower_third.choreography.brand_resolver import ResolvedBrand

log = logging.getLogger(__name__)

_CONSTANTS_PATH = Path(__file__).resolve().parent.parent / "config" / "module_constants.json"
_SYSTEM_PROMPT_PATH = Path(__file__).resolve().parent / "system_prompt.txt"


def _load_constants() -> dict:
    with open(_CONSTANTS_PATH) as fh:
        return json.load(fh)


def _load_system_prompt(brand: ResolvedBrand) -> str:
    template = _SYSTEM_PROMPT_PATH.read_text()
    return template.format(
        canvas_w=brand.canvas_w,
        canvas_h=brand.canvas_h,
        bar_y=brand.bar_y,
        bar_h=brand.bar_h,
        bar_padding_left=brand.bar_padding_left,
        bar_padding_top=brand.bar_padding_top,
        font_size_headline=brand.font_size_headline,
        font_size_kicker=brand.font_size_kicker,
        font_size_name=brand.font_size_name,
        font_size_title=brand.font_size_title,
        bar_color=brand.bar_color,
        text_color=brand.text_color,
        # computed geometry for examples
        # y = TOP of text bounding box (Cairo/Pango origin is upper-left, not baseline)
        bar_below=brand.bar_y + brand.bar_h + 60,
        bar_center_headline=brand.bar_y + brand.bar_padding_top,
        bar_above_headline=brand.bar_y - brand.font_size_headline - brand.bar_padding_top,
        # example 3 geometry (two-row lower-third with circle badge)
        bar_half_h=brand.label_row_h,
        bar_y_lower=brand.bar_y_ticker,
        bar_y_mid=brand.bar_y + (brand.canvas_h - brand.bar_y) // 2,
        ticker_row_h=brand.ticker_row_h,
        bar_center_ticker=brand.bar_y_ticker + brand.bar_padding_top,
        # badge text: two lines centred vertically inside the circle
        font_size_badge=max(14, brand.bar_h // 5),
        bar_y_mid_upper=(
            brand.bar_y_ticker
            - brand.bar_h // 5  # one line above badge centre
        ),
        bar_y_mid_lower=brand.bar_y_ticker + 2,
    )


def _make_groq_client(model: str) -> instructor.Instructor:
    return instructor.from_groq(
        Groq(api_key=os.environ["GROQ_API_KEY"]),
        mode=instructor.Mode.JSON,
    )


def _make_ollama_client(base_url: str) -> instructor.Instructor:
    return instructor.from_openai(
        OpenAI(base_url=base_url, api_key="ollama"),
        mode=instructor.Mode.JSON,
    )


def parse_prompt(user_prompt: str, brand: ResolvedBrand) -> LowerThirdSpec:
    constants = _load_constants()
    system_prompt = _load_system_prompt(brand)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    groq_model = constants["groq_model"]
    ollama_model = constants["ollama_model"]
    ollama_base_url = constants["ollama_base_url"]

    log.info("Parsing via Groq")
    try:
        client = _make_groq_client(groq_model)
        spec = client.chat.completions.create(
            model=groq_model,
            response_model=LowerThirdSpec,
            max_retries=3,
            messages=messages,
        )
        log.info("Groq parse successful")
        return spec
    except (RateLimitError, APITimeoutError, APIConnectionError) as e:
        log.warning("Groq unavailable (%s: %s), falling back to Ollama", type(e).__name__, e)

    log.info("Parsing via Ollama fallback")
    try:
        client = _make_ollama_client(ollama_base_url)
        spec = client.chat.completions.create(
            model=ollama_model,
            response_model=LowerThirdSpec,
            max_retries=3,
            messages=messages,
        )
        log.info("Ollama parse successful")
        return spec
    except Exception as e:
        log.error("Ollama parse failed: %s", e)
        raise RuntimeError(f"LLM parsing failed on both Groq and Ollama: {e}") from e
