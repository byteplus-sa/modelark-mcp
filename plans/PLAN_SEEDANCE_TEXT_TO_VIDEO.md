---
title: "Seedance Text-to-Video Support"
type: plan
status: shipped
created: 2026-07-27
updated: 2026-07-27
tags: [seedance, text-to-video, video-generation]
source: []
related:
  - plans/PLAN_MODELARK_SEED_MULTIMODAL_MCP.md
---

# Seedance Text-to-Video Support

## Goal

Allow the `seedance_create_task` tool to accept **text-only** input (prompt with
no reference images, videos, or audios) for pure text-to-video generation.

## Background

Seedance 2.0 supports text-to-video natively — the ModelArk API accepts a content
array with a single `{"type": "text"}` item. The previous validator
(`validate_media_required`) rejected prompt-only input with the error
`"At least one media input (image, video) is required."`, which was overly
restrictive.

## Changes

### 1. Validator modification (`src/modelark_mcp/tools/seedance_create_task.py`)

Replace the `validate_media_required` validator logic:

**Before:** reject when no images and no videos (regardless of prompt).

**After:**
- Allow text-only (prompt with no images/videos/audios).
- Still reject audio-only (no images/videos but has audios).
- Still reject completely empty (no prompt, no images, no videos).

The `has_prompt` check accounts for `variation_prompts` so the inherited
validator works correctly for `SeedanceVariationsInput`.

### 2. Test updates

| File | Change |
|------|--------|
| `tests/unit/test_tool_validators.py` | `test_no_media_raises` → `test_text_only_valid`; add `test_prompt_with_video_and_audio_valid` |
| `tests/integration/test_seedance_tool.py` | `test_create_task_no_media_raises` → `test_text_only_create_task_succeeds`; add `test_create_task_prompt_with_video_and_audio_succeeds` |
| `tests/integration/test_seedance_variations_tool.py` | `test_no_media_raises` → `test_text_only_variations_succeeds` |
| `tests/contract/test_seedance_adapter.py` | Add `test_prompt_with_video_and_audio` |

## Input Modality Matrix

| Input combination | Supported? |
|---|---|
| Prompt only (text-to-video) | ✅ |
| Prompt + image | ✅ |
| Prompt + video | ✅ |
| Prompt + video + audio | ✅ |
| Prompt + image + video + audio | ✅ |
| Audio only (no image/video) | ❌ |
| Empty request | ❌ |
