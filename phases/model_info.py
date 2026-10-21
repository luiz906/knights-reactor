"""
Knights Reactor — Replicate model inputs
Reads a model's own input schema from Replicate so the app knows, for ANY
image or video model picked in Settings, which clip lengths it can make,
which aspect ratios it takes, and what its start-frame / reference-image
inputs are called — instead of guessing from the model's name.

GET https://api.replicate.com/v1/models/{owner}/{name}
  → latest_version.openapi_schema.components.schemas.Input

Results are cached per model. If Replicate can't be reached, model_inputs()
returns None and callers fall back to their built-in guesses.
"""
import time

import requests

from config import Config, log

_CACHE = {}           # model -> (fetched_at, info or None)
_RETRY_AFTER = 600    # seconds before retrying a model whose schema fetch failed

# Start frame for video models, in order of preference.
_START_FIELDS = ("start_image", "first_frame_image", "image", "image_url", "input_image",
                 "first_frame", "start_frame", "first_frame_url")
# Character reference for image models (never plain "image": on image models
# that's usually an img2img starting picture, which would copy the layout).
_REF_FIELDS = ("image_input", "input_images", "reference_images", "image_prompts",
               "input_image", "reference_image", "image_reference")


def _resolve(prop: dict, schemas: dict) -> dict:
    """Merge a property with any $ref / allOf it points to (Replicate puts
    enums in components.schemas and references them)."""
    out = dict(prop)
    refs = [prop.get("$ref")] + [p.get("$ref") for p in prop.get("allOf", []) + prop.get("anyOf", [])
                                 if isinstance(p, dict)]
    for ref in refs:
        if ref and ref.startswith("#/components/schemas/"):
            target = schemas.get(ref.rsplit("/", 1)[-1], {})
            for k, v in target.items():
                out.setdefault(k, v)
    return out


def _durations(prop: dict):
    if prop.get("enum"):
        vals = sorted({int(v) for v in prop["enum"] if isinstance(v, (int, float)) and v > 0})
        return vals or None
    lo, hi = prop.get("minimum"), prop.get("maximum")
    if isinstance(lo, (int, float)) and isinstance(hi, (int, float)) and hi >= lo:
        return list(range(max(1, int(round(lo + 0.49))), int(hi) + 1)) or None
    return None


def parse_schema(schema: dict) -> dict:
    """Pull what the app needs out of a model's OpenAPI schema."""
    schemas = (schema or {}).get("components", {}).get("schemas", {})
    props = {k: _resolve(v, schemas) for k, v in schemas.get("Input", {}).get("properties", {}).items()}
    info = {"inputs": set(props), "durations": None, "default_duration": None,
            "aspect_ratios": None, "image_field": None, "ref_field": None, "ref_is_list": False,
            "enums": {k: p["enum"] for k, p in props.items() if p.get("enum")}}
    dur = props.get("duration")
    if dur:
        info["durations"] = _durations(dur)
        if isinstance(dur.get("default"), (int, float)):
            info["default_duration"] = float(dur["default"])
    ar = props.get("aspect_ratio")
    if ar:
        info["aspect_ratios"] = list(ar["enum"]) if ar.get("enum") else []   # [] = any value
    info["image_field"] = next((f for f in _START_FIELDS if f in props), None)
    ref = next((f for f in _REF_FIELDS if f in props), None)
    if ref:
        info["ref_field"] = ref
        info["ref_is_list"] = props[ref].get("type") == "array"
    return info


def model_inputs(model: str):
    """Parsed input info for a Replicate model, or None if unavailable."""
    if not model or not Config.REPLICATE_TOKEN:
        return None
    hit = _CACHE.get(model)
    if hit and (hit[1] is not None or time.time() - hit[0] < _RETRY_AFTER):
        return hit[1]
    info = None
    try:
        r = requests.get(f"https://api.replicate.com/v1/models/{model}",
                         headers={"Authorization": f"Bearer {Config.REPLICATE_TOKEN}"}, timeout=15)
        r.raise_for_status()
        schema = ((r.json().get("latest_version") or {}).get("openapi_schema")) or {}
        info = parse_schema(schema)
        if not info["inputs"]:
            raise ValueError("no input schema published")
        log.info(f"   ℹ️  {model}: durations={info['durations'] or info['default_duration'] or 'model default'}"
                 f" | aspect={'any' if info['aspect_ratios'] == [] else info['aspect_ratios']}"
                 f" | start frame={info['image_field']} | reference={info['ref_field']}")
    except Exception as e:
        log.warning(f"   ⚠️  Couldn't read {model}'s inputs from Replicate ({e}) — using built-in guesses")
    _CACHE[model] = (time.time(), info)
    return info


def pick_aspect(info: dict, target: str):
    """The aspect ratio to send: the target if the model takes it, else the
    closest one it offers. None when the model has no aspect_ratio input."""
    if not info or info.get("aspect_ratios") is None:
        return None
    allowed = info["aspect_ratios"]
    if not allowed or target in allowed:
        return target

    def ratio(v):
        try:
            w, h = str(v).split(":")
            return float(w) / float(h)
        except (ValueError, ZeroDivisionError):
            return None
    t = ratio(target)
    options = [(abs(ratio(v) - t), v) for v in allowed if ratio(v) is not None]
    return min(options)[1] if options and t else None
