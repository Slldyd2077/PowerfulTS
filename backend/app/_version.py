"""单一版本真源（后端运行时）。

本文件由 commitizen 在 ``cz bump`` 时自动维护，请勿手动修改。
后端 FastAPI 实例（/docs 页面、OpenAPI）从 ``__version__`` 读取版本号，
该文件会随 ``app/`` 一起进入 Docker 镜像，无需依赖外部的 pyproject.toml。
"""
__version__ = "0.3.0"
