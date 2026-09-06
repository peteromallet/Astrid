"""Pure-Python fixture for the checked-in Z Image templates."""

TEMPLATE_IDS = {"t2i": "image/z_image", "i2i": "image/z_image_img2img"}


def build(*, template_id: str, bindings: dict[str, object]) -> dict[str, object]:
    if template_id not in TEMPLATE_IDS.values():
        raise ValueError("unsupported Z Image template")
    return {"template_id": template_id, "bindings": dict(bindings), "output": "image/png"}
