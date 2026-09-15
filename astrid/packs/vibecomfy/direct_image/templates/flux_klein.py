"""Pure-Python fixture for the distinct Flux Klein edit model."""

TEMPLATE_ID = "edit/flux2_klein_4b_image_edit_distilled"


def build(*, template_id: str, bindings: dict[str, object]) -> dict[str, object]:
    if template_id != TEMPLATE_ID:
        raise ValueError("unsupported Flux Klein template")
    return {"template_id": template_id, "bindings": dict(bindings), "output": "image/png"}
