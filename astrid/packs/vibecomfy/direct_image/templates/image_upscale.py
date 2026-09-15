"""Pure-Python fixture for canonical image-upscale capability."""

TEMPLATE_ID = "image/basic_image_upscale"


def build(*, template_id: str, bindings: dict[str, object]) -> dict[str, object]:
    if template_id != TEMPLATE_ID:
        raise ValueError("unsupported image upscale template")
    return {"template_id": template_id, "bindings": dict(bindings), "output": "image/png"}
