"""Unit tests for Seed3D tool inputs and the provider adapter."""

from __future__ import annotations

import pytest

from ark_mcp.providers.modelark.seed3d import Seed3DService
from ark_mcp.tools.hitem3d_create_task import Hitem3dCreateTaskInput
from ark_mcp.tools.hyper3d_create_task import Hyper3DCreateTaskInput


class TestSeed3DCommandBuilding:
    def test_text_command_renders_flags_and_booleans(self) -> None:
        command = Seed3DService.build_text_command(
            {
                "material": "PBR",
                "use_original_alpha": True,
                "hd_texture": False,
                "bbox_condition": [100, 100, 100],
                "ignored": None,
                "empty": "",
            }
        )
        assert "--material PBR" in command
        assert "--use_original_alpha true" in command
        assert "--hd_texture false" in command
        assert "--bbox_condition [100,100,100]" in command
        assert "ignored" not in command
        assert "empty" not in command

    def test_build_content_prompts_then_images(self) -> None:
        content = Seed3DService.build_content(
            prompt="a robot",
            command_params={"fileformat": "glb"},
            images=[{"kind": "url", "url": "https://img.example.com/a.png"}],
        )
        assert content[0].type == "text"
        assert "a robot" in content[0].text
        assert "--fileformat glb" in content[0].text
        assert content[1].type == "image_url"
        assert content[1].image_url == {"url": "https://img.example.com/a.png"}


class TestHyper3DCreateTaskInput:
    def test_requires_prompt_or_images(self) -> None:
        with pytest.raises(ValueError, match="At least one of prompt or images"):
            Hyper3DCreateTaskInput()

    def test_prompt_only_is_valid(self) -> None:
        model = Hyper3DCreateTaskInput(prompt="a teapot")
        assert model.prompt == "a teapot"

    def test_command_params_map(self) -> None:
        model = Hyper3DCreateTaskInput(prompt="x", ta_pose=True, mesh_mode="Raw")
        params = model.command_params()
        assert params["TAPose"] is True
        assert params["mesh_mode"] == "Raw"


class TestHitem3dCreateTaskInput:
    def test_images_required(self) -> None:
        with pytest.raises(ValueError):
            Hitem3dCreateTaskInput()

    def test_multi_images_bit_rejects_bad_chars(self) -> None:
        with pytest.raises(ValueError, match="only 0 and 1"):
            Hitem3dCreateTaskInput(
                images=[{"kind": "url", "url": "https://img.example.com/a.png"}],
                multi_images_bit="10x0",
            )

    def test_file_format_maps_to_provider_int(self) -> None:
        model = Hitem3dCreateTaskInput(
            images=[{"kind": "url", "url": "https://img.example.com/a.png"}],
            file_format="glb",
        )
        assert model.command_params()["fileformat"] == 2
