# Ryomc Image MCP

在 Codex Desktop 对话中通过 [Ryomc API](https://api.ryomc.top) 文生图或编辑本机图片。这个版本使用本地 MCP 工具，向 Ryomc 的 **Images API** 发起请求；不再把图片工具塞进聊天模型的 `/v1/responses` 请求。

受 [micu-image-mcp](https://github.com/Subaru486desuwa/micu-image-mcp) 的工具设计启发，本仓库针对 Ryomc 独立实现了三个工具：`image_generate`、`image_edit`、`server_info`。没有移植原项目特有的米醋模型路由、自动重试、批量编辑或多图融合，因为这些行为尚未在 Ryomc 上验证。

## 使用前

1. 在 Ryomc 网站创建自己的**用户 API 密钥**，给它开放 `image` 分组、`gpt-image-2` 模型和适当的额度。不要使用 CPA 管理密钥。
2. 安装 Python 3.10+ 与 Codex Desktop/CLI。需要本机能够运行 `codex mcp add`。
3. 每次生成或编辑只请求一张，不自动重试。图片请求可能收费；具体金额请以 Ryomc 使用日志为准。

> 当前只验证了 Ryomc 的 `/v1/images/generations`、`/v1/images/edits` 路由能到达 New API；**尚未用有效密钥完成真实 `gpt-image-2` 出图测试**。如果服务端拒绝该模型，需先在 Ryomc 的 New API/上游渠道开放 Images API，不能仅修改本地 MCP。

## Windows 安装

在 PowerShell 中执行：

```powershell
git clone https://github.com/666666666666gao/image.git
Set-Location image
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe .\plugins\ryomc-image\server.py configure
$py = (Resolve-Path .\.venv\Scripts\python.exe).Path
$server = (Resolve-Path .\plugins\ryomc-image\server.py).Path
codex mcp add ryomc-image -- $py $server
codex mcp list
```

`configure` 会在终端隐藏输入密钥。不要把密钥粘贴到聊天、`config.toml` 或 GitHub。

## macOS / Linux 安装

在终端中执行：

```bash
git clone https://github.com/666666666666gao/image.git
cd image
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python plugins/ryomc-image/server.py configure
codex mcp add ryomc-image -- "$(pwd)/.venv/bin/python" "$(pwd)/plugins/ryomc-image/server.py"
codex mcp list
```

安装后重启 Codex Desktop，开启新对话。仓库与 `.venv` 需要留在原位置；如果移动它们，应先执行 `codex mcp remove ryomc-image`，再用新路径重新添加。

密钥保存在当前用户的 `~/.config/ryomc-image/config.json`（与旧版 Skill 相同）；这是本机明文配置，**不在 Git 仓库里**。macOS/Linux 上脚本将其权限设为仅当前用户可读写。如需更换密钥，再运行一次 `configure`。如需更换 API 站点，可运行 `configure --base-url https://你的站点/v1`。

## 在 Codex Desktop 中使用

- 文生图：“调用 `ryomc-image` 的 `image_generate`，画一张雨夜咖啡店插画。”
- 图生图：“调用 `ryomc-image` 的 `image_edit`，把 `C:\Pictures\photo.jpg` 改成水彩风格。” macOS/Linux 使用本机实际绝对路径。
- 局部编辑：给 `image_edit` 传 `mask_path`，必须是 PNG。透明区域是希望修改的位置。
- 检查连接配置：“调用 `ryomc-image` 的 `server_info`。”它只报告是否找到本机配置，不会显示密钥。

生成图保存在当前用户的 `Pictures/RyomcImages`，工具结果同时返回图片预览和本机绝对路径。图片工具模型固定为 `gpt-image-2`，**不依赖当前聊天选中的 `gpt-6-sol` 等模型**。

## 插件市场安装（可选）

仓库保留了 `.agents/plugins/marketplace.json`，也可作为 Codex 插件市场来源。该方式仍需要你在本机的 `python` 环境安装 `mcp>=2.2,<3`，并运行 `configure` 保存用户密钥。若系统上的 `python` 不是刚才创建的虚拟环境，建议使用上面的 `codex mcp add` 手动方式，以免插件启动时找不到依赖。

## 常见问题

- `401 Invalid token`：检查本机密钥是否为 Ryomc 创建的用户密钥，重新运行 `configure`；不要在聊天里发密钥。
- `403`：检查密钥的 `image` 分组和模型权限，也可能是站点/上游拒绝 Images API。查看错误中的 request id，并请管理员查 New API/CPA 日志。
- 结果提示“没有返回 base64 图片”：本 MCP 为避免下载不可信 URL，固定请求 `b64_json`；请先查 Ryomc 使用日志确认是否扣费，不要直接重试。
- 看不到 MCP 工具：执行 `codex mcp list`，确认 Python 依赖已安装、仓库路径未移动，然后重启 Codex Desktop。

## 开发验证

```text
python -m unittest discover -s tests -v
```

测试使用模拟 HTTP 响应，不发起收费生图请求。仓库没有附带任何 API 密钥。
