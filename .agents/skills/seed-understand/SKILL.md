---
name: seed-understand
description: Guide for using the seed_understand MCP tool for multimodal image and video understanding through Seed 2.1. Use when the user wants to extract text from images (OCR), analyze video content, compare visuals, review UI/UX, or use a multimodal reasoning sub-agent for tasks that require visual context. Supports deep-thinking chain-of-thought reasoning.
---

# Seed 2.1 Multimodal Understanding

The `seed_understand` MCP tool wraps BytePlus Seed 2.1 multimodal model via
ModelArk Chat Completions. It accepts a natural-language prompt plus optional
images and videos, and returns the model's text answer with optional
chain-of-thought reasoning.

## When to Use

Invoke this skill when the user wants to:

- **Extract text from images (OCR)** — read text in screenshots, documents,
  signs, labels, or UI elements
- **Understand video content** — summarize, describe, or answer questions about
  what happens in a video
- **Analyze UI/UX** — review screenshots for design issues, compare against
  specs, identify bugs or inconsistencies
- **Compare multiple images** — diff two designs, spot differences, evaluate
  consistency across screens
- **Reason about visual content** — combine text + images + videos for complex
  analysis that requires both visual understanding and logical reasoning
- **Use as a multimodal reasoning sub-agent** — delegate analysis tasks that
  need visual context to the model and get back structured answers

## Tool Reference

### `seed_understand`

**Auth scope:** `understanding:read`
**Requires:** `BYTEPLUS_MODELARK_API_KEY`

| Parameter | Type | Required | Description |
|---|---|---|---|
| `prompt` | `str` | Yes | 1–32,000 characters. The question or task. |
| `images` | `list[UnderstandingImageInput]` | No | Up to 32 images (URL or Base64) |
| `videos` | `list[UnderstandingVideoInput]` | No | Up to 32 videos (URL only, no Base64) |
| `system` | `str` | No | Optional system instruction (max 32,000 chars) |
| `model` | `str` | No | Override the configured Seed 2.1 model ID |
| `thinking` | `bool` | No (default `false`) | Enable deep-thinking chain-of-thought reasoning |
| `reasoning_effort` | `"low"` \| `"medium"` \| `"high"` | No | Only when `thinking=true` |
| `temperature` | `float` | No | 0.0–2.0. Lower = more deterministic |
| `max_tokens` | `int` | No | 1–32,768 |
| `top_p` | `float` | No | 0.0–1.0 nucleus sampling |
| `repetition_penalty` | `float` | No | 0.0–2.0 (Ark-only parameter) |

**Returns** `SeedUnderstandOutput` with:
- `model` — model ID used
- `completion_id` — provider completion ID for tracing
- `choices` — list of `UnderstandingChoice`, each with `content` and optional
  `reasoning_content` (when `thinking=true`)
- `usage` — `prompt_tokens`, `completion_tokens`, `total_tokens`
- `request_id` — provider request ID

## Input Formats

### Images

Images can be provided as URLs or Base64:

```json
{ "kind": "url", "url": "https://cdn.example.com/photo.png" }
```

```json
{ "kind": "base64", "data": "iVBORw0KGgo...", "mime_type": "image/png" }
```

- URLs are validated for SSRF safety (HTTPS only, public IPs, no metadata
  endpoints).
- Base64 is limited to 10 MiB per image (`MCP_INLINE_MEDIA_MAX_BYTES`).
- For local files, upload via `media_upload` first to get an HTTPS URL.

### Videos

Videos **must be HTTPS URLs** — Base64 is not supported by the chat endpoint:

```json
{ "kind": "url", "url": "https://cdn.example.com/clip.mp4" }
```

To use a local video file:
1. Upload via `media_upload` with `media_type: "video"`, `mime_type: "video/mp4"`.
2. Pass the returned presigned URL to `seed_understand`.

## Deep-Thinking Mode

When `thinking=true`, the model produces chain-of-thought reasoning visible in
`choices[].reasoning_content`. This is useful for:

- Complex analysis requiring step-by-step reasoning
- Multi-step comparisons (e.g., "compare these 5 screenshots and rank them")
- Tasks where the reasoning process matters as much as the answer

Use `reasoning_effort` to control thinking depth:

| Level | When to Use | Latency |
|---|---|---|
| `low` | Quick checks, simple OCR, basic descriptions | Fastest |
| `medium` | Balanced analysis, moderate comparisons | Moderate |
| `high` | Deep analysis, complex reasoning, detailed reviews | Slowest |

## Common Use Cases

### Image OCR (Text Extraction)

Extract visible text from screenshots, documents, signs, or UI:

```json
{
  "prompt": "Extract all text visible in this image, preserving the layout structure. Return as structured markdown.",
  "images": [
    { "kind": "url", "url": "https://cdn.example.com/document.png" }
  ]
}
```

**Tips for OCR:**
- Specify the output format (markdown, JSON, plain text)
- Ask for layout preservation if structure matters
- For multi-language text, mention the expected languages in the prompt
- For handwriting, add context about expected content

### Video Content Analysis

Summarize, describe, or answer questions about video content:

```json
{
  "prompt": "Summarize this product demo video. What are the 3 key features shown? Note any visible bugs or UI issues with timestamps.",
  "videos": [
    { "kind": "url", "url": "https://cdn.example.com/demo.mp4" }
  ],
  "thinking": true,
  "reasoning_effort": "medium",
  "max_tokens": 4096
}
```

**Tips for video analysis:**
- Ask for timestamps when referencing specific moments
- Use `thinking=true` for complex analysis
- Break long videos into segments if the model struggles with context
- Ask for structured output (bullet points, numbered lists) for readability

### UI/UX Review

Analyze screenshots for design issues and compare against specs:

```json
{
  "prompt": "Compare the UI in screenshot 1 with the design spec in screenshot 2. List all differences in: spacing, color, typography, icon usage, and alignment. Be specific about pixel-level differences.",
  "images": [
    { "kind": "url", "url": "https://cdn.example.com/implementation.png" },
    { "kind": "url", "url": "https://cdn.example.com/design-spec.png" }
  ],
  "system": "You are a meticulous UI/UX reviewer. Report differences with exact values. Do not skip minor issues.",
  "thinking": true,
  "reasoning_effort": "high",
  "max_tokens": 8192
}
```

### Multi-Image Comparison

Compare multiple images for consistency, differences, or ranking:

```json
{
  "prompt": "Here are 4 product photo variations. Rank them by visual appeal and brand consistency. Explain your reasoning for each ranking position.",
  "images": [
    { "kind": "url", "url": "https://cdn.example.com/variant-a.jpg" },
    { "kind": "url", "url": "https://cdn.example.com/variant-b.jpg" },
    { "kind": "url", "url": "https://cdn.example.com/variant-c.jpg" },
    { "kind": "url", "url": "https://cdn.example.com/variant-d.jpg" }
  ],
  "thinking": true,
  "reasoning_effort": "high"
}
```

### Reasoning Sub-Agent

Use as a multimodal reasoning sub-agent for complex analysis tasks:

```json
{
  "prompt": "This is a screenshot of our dashboard analytics page. The user reported that the 'Revenue' chart shows incorrect data for Q3. Analyze: 1) What data is displayed? 2) Are there any visible anomalies? 3) What could cause a discrepancy between displayed and expected values? 4) What steps should we take to debug?",
  "images": [
    { "kind": "url", "url": "https://cdn.example.com/dashboard.png" }
  ],
  "system": "You are a senior data analyst. Be thorough and systematic. Consider data pipeline issues, caching, timezone handling, and UI rendering bugs.",
  "thinking": true,
  "reasoning_effort": "high",
  "max_tokens": 8192
}
```

## Model Selection

The server uses `SEED_UNDERSTANDING_DEFAULT_MODEL` (default:
`dola-seed-2-1-turbo-260628`). Override per-call with the `model` parameter.

| Family | Default Model ID | Key Traits |
|---|---|---|
| **Seed 2.1 Turbo** | `dola-seed-2-1-turbo-260628` | 256K context, images + videos, deep-thinking |
| **Seed 2.1 Pro** | *(configured via `SEED_UNDERSTANDING_MODEL_BINDINGS`)* | 256K context, images + videos, deep-thinking |

Both models support:
- Up to 32 media parts (images + videos combined)
- Deep-thinking mode with `low`, `medium`, `high` reasoning effort
- 256K token context window
- Temperature, top_p, max_tokens, and repetition_penalty controls

## Prompt Engineering Tips

### Be Specific About Output Format

```json
{
  "prompt": "Extract the text from this receipt and return as JSON with fields: merchant, date, items (array of {name, price}), subtotal, tax, total."
}
```

### Use System Instructions for Role and Constraints

```json
{
  "prompt": "Review this landing page screenshot for conversion optimization issues.",
  "system": "You are a CRO expert with 10 years of experience. Focus on: above-the-fold content, CTA clarity, trust signals, visual hierarchy, and mobile responsiveness indicators. Be concise but actionable."
}
```

### Break Complex Tasks into Steps

Instead of one massive prompt, make focused calls:

1. **Call 1:** "Extract all text from this image."
2. **Call 2:** "Given this text: [paste], identify the key entities and their relationships."
3. **Call 3:** "Summarize these entity relationships in a table."

This gives better results than a single "extract, analyze, and summarize" prompt.

### Use Thinking for Complex Reasoning

Enable `thinking=true` when the task involves:
- Multi-step reasoning
- Comparisons or rankings
- Causal analysis
- Debugging or root-cause analysis
- Creative interpretation

Keep `thinking=false` for simple extraction, description, or lookup tasks where
speed matters more than reasoning depth.

## Limitations

1. **Video Base64 is not supported.** Upload via `media_upload` first.
2. **32 media parts max** (images + videos combined).
3. **Synchronous call.** The tool blocks until the model responds. Long videos
   with deep-thinking can take 30+ seconds. Set an appropriate `max_tokens`.
4. **No streaming.** The full response is returned at once.
5. **No artifact persistence.** Understanding returns text, not media. No
   artifact store needed.

## Related Tools

- `media_upload` — upload local media to get HTTPS URLs for video inputs
- `seedream_generate_image` — generate images from text prompts
- `seedance_create_task` — generate videos (results can be analyzed with
  `seed_understand`)
- `speech_to_text` — transcribe audio to text (complementary to visual
  understanding)
