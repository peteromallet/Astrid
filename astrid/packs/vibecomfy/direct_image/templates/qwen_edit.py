"""Pure-Python fixture for Qwen edit/style/mask templates."""

TEMPLATE_ID = "edit/qwen_image_edit"


def build(*, template_id: str, bindings: dict[str, object]) -> dict[str, object]:
    if template_id != TEMPLATE_ID:
        raise ValueError("unsupported Qwen edit template")
    return {"template_id": template_id, "bindings": dict(bindings), "output": "image/png"}
