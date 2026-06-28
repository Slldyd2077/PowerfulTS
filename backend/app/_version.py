"""单一版本真源（后端运行时）。

本文件由 commitizen 在 ``cz bump`` 时与根 ``.cz.toml`` 的 version 字段原子同步，
请勿手动修改 —— 真源是 ``.cz.toml`` 顶部的 ``version``，发版统一走 ``cz bump``。

后端 FastAPI 实例（``/docs``、OpenAPI schema）从 ``__version__`` 读取版本号。
这里故意用源码常量而非 ``importlib.metadata.version(...)``：Docker 镜像
（见 ``backend/Dockerfile``）只 ``COPY app``、后端以 ``uvicorn app.main:app``
裸源码运行、未作为包安装，dist-info 元数据不存在，importlib 拿不到版本。
"""
__version__ = "0.3.0"
