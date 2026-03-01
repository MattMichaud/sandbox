import json
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

GALLERY_DIR = Path(__file__).parent / "gallery"
METADATA_FILE = GALLERY_DIR / "metadata.json"


@dataclass
class GalleryEntry:
    id: str
    plan_name: str
    plan_title: str
    prompt: str | None
    mode: str
    image_file: str
    published_at: str
    style: str | None = None


def publish_image(
    img_bytes: bytes,
    plan_name: str,
    plan_title: str,
    prompt: str | None,
    mode: str,
    style: str | None = None,
) -> GalleryEntry:
    GALLERY_DIR.mkdir(exist_ok=True)
    entry_id = uuid.uuid4().hex[:8]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    image_file = f"{plan_name}_{timestamp}_{entry_id}.png"
    (GALLERY_DIR / image_file).write_bytes(img_bytes)

    entry = GalleryEntry(
        id=entry_id,
        plan_name=plan_name,
        plan_title=plan_title,
        prompt=prompt,
        mode=mode,
        image_file=image_file,
        published_at=datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        style=style,
    )

    metadata = _load_metadata()
    metadata.append(asdict(entry))
    METADATA_FILE.write_text(json.dumps(metadata, indent=2))
    return entry


def delete_entry(entry_id: str) -> None:
    metadata = _load_metadata()
    new_metadata = []
    for item in metadata:
        if item["id"] == entry_id:
            image_path = GALLERY_DIR / item["image_file"]
            if image_path.exists():
                image_path.unlink()
        else:
            new_metadata.append(item)
    METADATA_FILE.write_text(json.dumps(new_metadata, indent=2))


def load_gallery() -> list[GalleryEntry]:
    metadata = _load_metadata()
    entries = []
    known = {f for f in GalleryEntry.__dataclass_fields__}
    for item in reversed(metadata):
        image_path = GALLERY_DIR / item["image_file"]
        if image_path.exists():
            entries.append(GalleryEntry(**{k: v for k, v in item.items() if k in known}))
    return entries


def _load_metadata() -> list[dict]:
    if not METADATA_FILE.exists():
        return []
    try:
        return json.loads(METADATA_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return []
