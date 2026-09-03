"""Optional web layer. Requires the ``api`` extra (fastapi, uvicorn).

Nothing outside this package imports it, so the core and the CLI keep
working with zero runtime dependencies when the extra is not installed.
"""
