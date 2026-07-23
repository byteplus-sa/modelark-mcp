# Model Capability Registry

The capability registry (`config/model_capabilities.py`) describes, per
configured model, what inputs the server will accept before it ever calls
the provider. It validates image sizes, output formats, video resolutions,
and durations against family-specific rules, so unsupported requests fail fast
with an actionable `ValueError`.

## Families

`ModelFamily` (`StrEnum`) has six members:

| Member | Value |
|---|---|
| `SEEDREAM_PRO` | `seedream_pro` |
| `SEEDREAM_LITE` | `seedream_lite` |
| `SEEDREAM_4X` | `seedream_4x` |
| `SEEDANCE_2` | `seedance_2` |
| `SEEDANCE_2_FAST` | `seedance_2_fast` |
| `SEEDANCE_2_MINI` | `seedance_2_mini` |

The binding enums (`config/env.py`):

- `SeedreamFamily`: `PRO = "pro"`, `LITE = "lite"`, `V4X = "4x"`.
- `SeedanceFamily`: `STANDARD = "standard"`, `FAST = "fast"`, `MINI = "mini"`.

## Image capabilities (`ImageCapabilities`)

| Field | `PRO` | `LITE` | `4X` |
|---|---|---|---|
| `max_references` | 10 | 14 | 14 |
| `supports_batch` | `False` | `True` | `True` |
| `supports_streaming` | `False` | `True` | `True` |
| `supported_output_formats` | `("png", "jpeg")` | `("png", "jpeg")` | `("jpeg",)` |
| `supported_sizes` | `None` (any) | `None` | `None` |
| `supports_watermark` | `True` | `True` | `True` |
| `supports_prompt_optimization` | `True` | `True` | `True` |

> There is **no aspect-ratio field** on image capabilities. Only
> `supported_sizes` (defaulting to `None` = unrestricted).

## Video capabilities (`VideoCapabilities`)

All three Seedance families share: `max_reference_images=9`,
`max_reference_videos=3`, `max_reference_audios=3`, `supports_seed=False`,
`supports_camera_fixed=False`, `supports_frames=False`,
`supports_service_tier_flex=False`, `duration_range=(-1, 15)`,
`priority_range=(0, 9)`, `execution_expires_after_range=(3600, 259200)`.

Only `supported_resolutions` differs:

| Family | `supported_resolutions` |
|---|---|
| `MINI` | `("480p", "720p")` |
| `FAST` | `("480p", "720p")` |
| `STANDARD` | `("480p", "720p", "1080p", "4k")` |

> There is also **no aspect-ratio field** on video capabilities — the
> `ratio` field exists only on `SeedanceTaskSettings` and the tool input
> layer; the registry does not validate ratios.

## Default model IDs

| Field | Env var | Default | Implied family |
|---|---|---|---|
| `seedream_default_model` | `SEEDREAM_DEFAULT_MODEL` | `dola-seedream-5-0-pro-260628` | `PRO` |
| `seedance_default_model` | `SEEDANCE_DEFAULT_MODEL` | `dreamina-seedance-2-0-260128` | `STANDARD` |

The "implied family" defaults are hard-coded in `Settings.validate_model_bindings`
and apply only when the default model ID equals the built-in default.

## Environment variables

| Env var | Format | Default |
|---|---|---|
| `SEEDREAM_MODEL_BINDINGS` | JSON array of `{"model_id": str, "family": "pro"\|"lite"\|"4x"}` | `[]` |
| `SEEDANCE_MODEL_BINDINGS` | JSON array of `{"model_id": str, "family": "standard"\|"fast"\|"mini"}` | `[]` |
| `SEEDREAM_MODEL_FAMILY` | single family string | `""` |
| `SEEDANCE_MODEL_FAMILY` | single family string | `""` |

Examples (from `.env.example`):

```
SEEDREAM_MODEL_BINDINGS=[{"model_id":"my-image-endpoint","family":"pro"}]
SEEDANCE_MODEL_BINDINGS=[{"model_id":"my-video-endpoint","family":"standard"}]
```

## How a `model_id` resolves to a family

Resolution is **binding-table based, not string-pattern based** (no inference
from the model ID string):

1. If `SEEDREAM_MODEL_BINDINGS` (resp. `SEEDANCE_MODEL_BINDINGS`) is set, it
   is the source of truth — each binding explicitly pairs `model_id` ↔
   `family`.
2. If the bindings list is empty and `SEEDREAM_MODEL_FAMILY` (resp.
   `SEEDANCE_MODEL_FAMILY`) is non-empty, a single binding is synthesized
   from the default model ID + that family.
3. If both are empty and the default model ID equals the built-in default,
   the built-in default family is used (`PRO` / `STANDARD`).
4. Otherwise (custom default model, no family, no bindings) → startup fails
   with `ValueError`.

## Validation rules

`CapabilityRegistry` methods (`get_image_capabilities(model_id)`,
`get_video_capabilities(model_id)`, `list_image_models()`,
`list_video_models()`, plus `validate_image_size`,
`validate_output_format`, `validate_resolution`, `validate_duration`):

| Check | Rejected when |
|---|---|
| Unknown `model_id` | not in the configured registry (`ValueError` lists allowed IDs) |
| Image `output_format` | not in `supported_output_formats` (e.g. `png` on a `4X` model, which only supports `jpeg`) |
| Image `size` | `supported_sizes` is set and `size` not in it (Seedream defaults leave this `None`, so any size passes) |
| Video `resolution` | not in `supported_resolutions` (e.g. `1080p`/`4k` on `MINI`/`FAST`) |
| Video `duration` | outside `duration_range` unless `-1` (auto) |

Settings startup additionally rejects: duplicate model IDs within a
family's bindings, a default model ID missing from bindings, a custom
default model with no family/binding, unknown family strings, non-HTTPS
provider URLs, non-positive `ARTIFACT_TTL_SECONDS` /
`MCP_INLINE_MEDIA_MAX_BYTES` / timeouts, invalid allowed origins, JWT auth
missing required fields, and non-loopback HTTP without JWT.

## Module-level singleton

- `get_capability_registry()` — returns a process-cached `CapabilityRegistry`
  (lazily built).
- `refresh_capability_registry()` — force-rebuilds after config changes (call
  `refresh_settings()` first).

## What the registry does not do

- It is **not a cost table.** Cost estimation (see
  [runtime.md](runtime.md#cost-estimation-toolscostpy)) is per product and
  per variation; families do not affect cost.
- It does **not** validate aspect ratios.
- It does **not** call the provider — it is a local, pre-flight validation
  layer built entirely from configuration.
