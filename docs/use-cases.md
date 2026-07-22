# Use Cases

The ModelArk Seed MCP server exposes BytePlus multimodal generation through
nine MCP tools. Here are common scenarios and how to achieve them.

## 1. Text-to-Image Generation

Generate a single image from a text prompt.

**Tool:** `seedream_generate_image`

```json
{
  "prompt": "A serene mountain landscape at sunset, digital art",
  "size": "1024x1024",
  "output_format": "jpeg",
  "persist": true
}
```

The tool returns a durable `ArtifactRef` that survives the 24-hour provider
URL expiry. The artifact is retrievable via
`seed-media://artifacts/{artifact_id}`.

## 2. Image Editing

Edit an existing image using a text prompt and reference image.

**Tool:** `seedream_generate_image`

```json
{
  "prompt": "Change the background to a beach scene while keeping the subject",
  "images": [
    {
      "kind": "url",
      "url": "https://cdn.example.com/original.png"
    }
  ],
  "size": "1024x1024",
  "persist": true
}
```

## 3. Reproducible Image Generation

Generate an image with a fixed seed for reproducibility.

**Tool:** `seedream_generate_image`

```json
{
  "prompt": "A cat sitting on a windowsill",
  "seed": 42,
  "size": "1024x1024"
}
```

Using the same seed and prompt produces the same image.

## 4. Parallel Image Variations

Generate multiple distinct image variations in a single call to give the
user choices. Each variation gets a distinct seed.

**Tool:** `seedream_generate_image_variations`

```json
{
  "prompt": "A futuristic city skyline, cyberpunk aesthetic",
  "variations": 5,
  "base_seed": 100,
  "size": "1024x1024",
  "persist": true
}
```

This produces 5 images with seeds [100, 101, 102, 103, 104]. Each is an
independent generation. Partial failures are captured — if 4 of 5 succeed,
the tool returns 4 artifacts and 1 error.

## 5. Per-Variation Prompts

Generate variations with different prompts for each.

**Tool:** `seedream_generate_image_variations`

```json
{
  "variation_prompts": [
    "A cat in spring, cherry blossoms",
    "A cat in summer, sunny garden",
    "A cat in autumn, fallen leaves",
    "A cat in winter, snow"
  ],
  "variations": 4,
  "persist": true
}
```

## 6. Audio Generation (Text-to-Speech)

Generate speech from a text prompt.

**Tool:** `seed_audio_generate`

```json
{
  "text_prompt": "Welcome to the ModelArk Seed Multimodal MCP Server.",
  "output": {
    "format": "wav",
    "sample_rate": 44100
  },
  "persist": true
}
```

## 7. Voice Cloning with References

Generate audio that mimics a reference voice.

**Tool:** `seed_audio_generate`

```json
{
  "text_prompt": "Hello, this is a cloned voice test.",
  "audio_references": [
    {
      "kind": "url",
      "url": "https://cdn.example.com/voice-sample.wav",
      "mime_type": "audio/wav"
    }
  ],
  "persist": true
}
```

## 8. Parallel Audio Variations

Generate multiple audio takes to choose from.

**Tool:** `seed_audio_generate_variations`

```json
{
  "text_prompt": "The quick brown fox jumps over the lazy dog.",
  "variations": 3,
  "persist": true
}
```

## 9. Video Generation (Text-to-Video)

Create an async video generation task.

**Tool:** `seedance_create_task`

```json
{
  "prompt": "A cat walking through a garden, warm sunlight",
  "images": [
    {
      "kind": "url",
      "url": "https://cdn.example.com/reference.png",
      "role": "reference_image"
    }
  ],
  "resolution": "480p",
  "duration": 5
}
```

Returns a task ID. Poll for completion with `seedance_get_task`.

## 10. Polling for Video Completion

Check the status of a video generation task.

**Tool:** `seedance_get_task`

```json
{
  "task_id": "cgt-20260721134956-h5cz9",
  "persist_output": true
}
```

On first successful retrieval, the video is automatically downloaded and
persisted as a durable artifact. Subsequent polls return the cached
artifact without re-downloading.

## 11. First/Last Frame Video Generation

Generate a video that starts with one image and ends with another.

**Tool:** `seedance_create_task`

```json
{
  "prompt": "Flowers blooming from bud to full bloom",
  "images": [
    {
      "kind": "url",
      "url": "https://cdn.example.com/bud.png",
      "role": "first_frame"
    },
    {
      "kind": "url",
      "url": "https://cdn.example.com/full-bloom.png",
      "role": "last_frame"
    }
  ],
  "resolution": "720p",
  "duration": 5
}
```

## 12. Parallel Video Task Variations

Create multiple video tasks with different prompts.

**Tool:** `seedance_create_task_variations`

```json
{
  "variation_prompts": [
    "The cat walks forward slowly through the garden",
    "The cat looks around curiously, then jumps playfully"
  ],
  "variations": 2,
  "images": [
    {
      "kind": "base64",
      "data": "base64-encoded-png-data",
      "mime_type": "image/png",
      "role": "reference_image"
    }
  ],
  "resolution": "480p",
  "duration": 5
}
```

Returns multiple task IDs. Poll each with `seedance_get_task`.

## 13. List Recent Video Tasks

List video generation tasks from the last 7 days.

**Tool:** `seedance_list_tasks`

```json
{
  "page": 1,
  "page_size": 20,
  "status": "succeeded"
}
```

## 14. Cancel or Delete a Video Task

Cancel a queued task or delete a completed one.

**Tool:** `seedance_cancel_or_delete_task`

Cancel (queued):

```json
{
  "task_id": "cgt-20260721134956-h5cz9",
  "mode": "cancel",
  "expected_status": "queued"
}
```

Delete (terminal):

```json
{
  "task_id": "cgt-20260721134956-h5cz9",
  "mode": "delete",
  "expected_status": "succeeded"
}
```

## 15. End-to-End: Image-to-Video Pipeline

Generate a reference image, then use it as input for video generation.

1. Generate an image:

```
seedream_generate_image({
  "prompt": "A fluffy orange cat on a garden path",
  "size": "1024x1024",
  "response_format": "b64_json",
  "persist": true
})
```

2. Use the generated image (as base64) for video:

```
seedance_create_task({
  "prompt": "The cat walks forward through the garden",
  "images": [{
    "kind": "base64",
    "data": "<base64 from step 1>",
    "mime_type": "image/png",
    "role": "reference_image"
  }],
  "resolution": "480p",
  "duration": 5
})
```

3. Poll for video completion:

```
seedance_get_task({"task_id": "<task_id from step 2>"})
```

## 16. Batch Storyboard with Seedream

Generate a coherent set of related images using the provider's native batch
mode (not parallel variations — these share visual continuity).

**Tool:** `seedream_generate_image`

```json
{
  "prompt": "A set of four seasons landscape illustrations: spring, summer, autumn, winter",
  "max_images": 4,
  "size": "1024x1024",
  "persist": true
}
```

This uses `sequential_image_generation: "auto"` — the provider generates a
coherent storyboard, not independent variations.