import hashlib
import shutil
from pathlib import Path

from lower_third.parser.prompt_schema import LowerThirdSpec

CACHE_DIR = Path(__file__).resolve().parent / "assets"


def cache_key(spec: LowerThirdSpec) -> str:
    payload = spec.model_dump_json(exclude={"instance_id", "schema_version"})
    return hashlib.sha256(payload.encode()).hexdigest()


def cache_hit(spec: LowerThirdSpec) -> Path | None:
    import lower_third.cache.template_cache as _self
    dest = _self.CACHE_DIR / f"{cache_key(spec)}.webm"
    return dest if dest.exists() else None


def cache_write(spec: LowerThirdSpec, rendered_webm: Path) -> Path:
    import lower_third.cache.template_cache as _self
    _self.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    dest = _self.CACHE_DIR / f"{cache_key(spec)}.webm"
    shutil.copy(rendered_webm, dest)
    return dest
