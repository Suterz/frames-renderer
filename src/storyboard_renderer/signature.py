"""Explicitly prevent graphic design instructions from leaking into diffusion prompts."""

def art_only(signature: str) -> str:
    before="\n".join(
        line for line in signature.split("## Renderer-only graphics",1)[0].splitlines()
        if line.strip() and not line.startswith("#")
    ).strip()
    if not before:
        raise ValueError("visual signature has no illustration instructions")
    return before
