# Publishing to PyPI / 发布到 PyPI

This guide explains how to package and publish `docu-fluent` to PyPI so that others can install it using `pip` or `uv`.

本指南说明如何打包 `docu-fluent` 并将其发布到 PyPI，以便其他人可以使用 `pip` 或 `uv` 安装它。

## Prerequisites / 先决条件

1.  **PyPI Account**: You need an account on [PyPI](https://pypi.org/).
    **PyPI 账号**: 您需要在 [PyPI](https://pypi.org/) 上拥有一个账号。

2.  **API Token**: Create an API token in your PyPI account settings.
    **API Token**: 在您的 PyPI 账号设置中创建一个 API Token。

3.  **Build Tools**: Ensure you have `uv` installed.
    **构建工具**: 确保您已安装 `uv`。

## Configuration / 配置

The `pyproject.toml` file has been configured with the necessary metadata.
`pyproject.toml` 文件已配置了必要的元数据。

**Important**: Before publishing, please update the following fields in `pyproject.toml`:
**重要**: 发布前，请更新 `pyproject.toml` 中的以下字段：

-   `authors`: Your name and email. (您的姓名和邮箱)
-   `version`: The version number (e.g., `0.1.0`). (版本号)

## Build / 构建

Run the following command to build the package (Source Distribution and Wheel):
运行以下命令构建包（源码包和 Wheel 包）：

```bash
uv build
```

This will create a `dist/` directory containing the `.tar.gz` and `.whl` files.
这将在 `dist/` 目录下生成 `.tar.gz` 和 `.whl` 文件。

## Publish / 发布

### Using `uv` (Recommended) / 使用 `uv` (推荐)

You can publish directly using `uv`:
您可以直接使用 `uv` 发布：

```bash
uv publish
```

You will be prompted for your PyPI API token (use `__token__` as username).
系统会提示您输入 PyPI API Token（用户名为 `__token__`）。

### Using `twine` (Alternative) / 使用 `twine` (备选)

If you prefer `twine`:
如果您更喜欢使用 `twine`：

1.  Install twine:
    安装 twine:
    ```bash
    uv pip install twine
    ```

2.  Upload to PyPI:
    上传到 PyPI:
    ```bash
    uv run twine upload dist/*
    ```

## Installation by Others / 其他人如何安装

Once published, anyone can install your package using:
发布后，任何人都可以通过以下命令安装您的包：

```bash
# Using pip
pip install docu-fluent

# Using uv
uv pip install docu-fluent
```
