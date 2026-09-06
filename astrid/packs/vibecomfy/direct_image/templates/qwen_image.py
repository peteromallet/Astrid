"""Pure-Python fixture for Qwen text-to-image templates."""

TEMPLATE_ID = "image/qwen_image_2512"


def build(*, template_id: str, bindings: dict[str, object]) -> dict[str, object]:
    if template_id != TEMPLATE_ID:
        raise ValueError("unsupported Qwen image template")
    return {"template_id": template_id, "bindings": dict(bindings), "output": "image/png"}
