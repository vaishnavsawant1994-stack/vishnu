from __future__ import annotations

import base64
import io
import json

import pytest
from PIL import Image

from onboarding.owner_avatar import read_owner_avatar, store_owner_avatar

OWNER = "OWNER-" + "A" * 32
OTHER_OWNER = "OWNER-" + "B" * 32


def encoded_image(fmt="PNG", size=(24, 24)) -> str:
    output = io.BytesIO()
    Image.new("RGB", size, (26, 133, 220)).save(output, format=fmt)
    return base64.b64encode(output.getvalue()).decode("ascii")


def test_preset_avatar_is_durable_and_owner_bound(tmp_path):
    stored = store_owner_avatar(tmp_path, OWNER, source="preset", preset_id="forest")
    assert stored == {"saved": True, "source": "preset", "preset_id": "forest"}
    assert read_owner_avatar(tmp_path, OWNER) == ({"source": "preset", "preset_id": "forest"}, None)
    assert (tmp_path / "owner-profile" / "avatar.json").stat().st_mode & 0o077 == 0
    assert (tmp_path / "owner-profile").stat().st_mode & 0o077 == 0
    with pytest.raises(ValueError, match="another owner"):
        read_owner_avatar(tmp_path, OTHER_OWNER)


def test_upload_reencodes_pixels_and_is_retry_safe(tmp_path):
    photo = encoded_image("JPEG")
    for _ in range(2):
        result = store_owner_avatar(tmp_path, OWNER, source="upload", image_b64=photo)
        assert result["saved"]
    meta, content = read_owner_avatar(tmp_path, OWNER)
    assert meta == {"source": "upload", "preset_id": ""}
    with Image.open(io.BytesIO(content)) as img:
        assert img.format == "PNG"
        assert img.size == (24, 24)
        assert not img.info.get("exif")
    assert (tmp_path / "owner-profile" / "avatar.png").stat().st_mode & 0o077 == 0
    store_owner_avatar(tmp_path, OWNER, source="none")
    assert read_owner_avatar(tmp_path, OWNER) == ({"source": "none", "preset_id": ""}, None)
    assert not (tmp_path / "owner-profile" / "avatar.png").exists()


@pytest.mark.parametrize("source,preset,image", [
    ("preset", "invalid", ""),
    ("none", "blue", ""),
    ("preset", "blue", "leak"),
    ("upload", "blue", encoded_image()),
    ("upload", "", "!!!"),
    ("upload", "", base64.b64encode(b"<svg/>").decode("ascii")),
    ("upload", "", ""),
])
def test_invalid_selection_rejected_without_changing_saved_profile(tmp_path, source, preset, image):
    store_owner_avatar(tmp_path, OWNER, source="preset", preset_id="blue")
    with pytest.raises(ValueError):
        store_owner_avatar(tmp_path, OWNER, source=source, preset_id=preset, image_b64=image)
    assert read_owner_avatar(tmp_path, OWNER)[0]["preset_id"] == "blue"


def test_large_image_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="2 MB"):
        store_owner_avatar(tmp_path, OWNER, source="upload", image_b64="A" * (2_800_000))


def test_source_cannot_select_arbitrary_path(tmp_path):
    with pytest.raises(ValueError, match="canonical"):
        store_owner_avatar(tmp_path, "../private", source="preset", preset_id="blue")
    assert not (tmp_path / "owner-profile").exists()


def test_avatar_metadata_never_exposes_encoded_photo(tmp_path):
    raw = encoded_image()
    store_owner_avatar(tmp_path, OWNER, source="upload", image_b64=raw)
    metadata = json.loads((tmp_path / "owner-profile" / "avatar.json").read_text())
    assert metadata["owner_id"] == OWNER
    assert raw not in json.dumps(metadata)
