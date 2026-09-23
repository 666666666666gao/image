# Ryomc Image for Codex Desktop

在 Codex Desktop 对话中用自己的 [Ryomc API](https://api.ryomc.top) 密钥文生图或图生图。Codex 调用本地 Skill，Skill 向 `/v1/responses` 发送图片工具请求，生成的 PNG 保存到本机并可在对话里显示。它**不是**修改 Codex 内置图片工具的计费线路。

## 使用前

1. 在 Ryomc API 网站创建一个用户 API 密钥，选择可用的 **image 分组**，并给该密钥设置合适的额度。不要使用 CPA 管理密钥。
2. 安装 Python 3.10 或更新版本，并确认 Codex Desktop 可以执行本机命令。
3. 每台电脑只需配置一次密钥。每次生成会消耗站点余额；工具不会自动重试。

## 安装 Skill

先下载仓库：

```text
git clone https://github.com/666666666666gao/image.git
```

Windows PowerShell（在下载仓库的上级目录执行）：

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.codex\skills" | Out-Null
Copy-Item -Recurse ".\image\plugins\ryomc-image\skills\ryomc-image" "$env:USERPROFILE\.codex\skills\ryomc-image"
py -3 "$env:USERPROFILE\.codex\skills\ryomc-image\scripts\ryomc_image.py" configure
```

macOS / Linux（在下载仓库的上级目录执行）：

```bash
mkdir -p "$HOME/.codex/skills"
cp -R ./image/plugins/ryomc-image/skills/ryomc-image "$HOME/.codex/skills/ryomc-image"
python3 "$HOME/.codex/skills/ryomc-image/scripts/ryomc_image.py" configure
```

`configure` 默认使用 `https://api.ryomc.top/v1`，会在终端隐藏输入密钥；需要自定义站点时可加 `--base-url https://你的站点/v1`。图片工具模型为 `gpt-image-2`。聊天主模型不再保存在此配置中，而是在每次生成时通过 `--model` 指定。

密钥保存在本机用户目录的 `~/.config/ryomc-image/config.json`，**不是加密文件**；请仅使用自己创建的限额密钥，不要把该文件上传或发给别人。macOS / Linux 文件权限设为仅当前用户可读写。

安装或更新后，重启 Codex Desktop 并开启新对话。
如果你自定义了 `CODEX_HOME`，请把上面安装路径中的 `~/.codex` 换成该目录。

## 在对话中使用

- “用 Ryomc Image 生成一张雨夜咖啡店的插画。”
- “用 Ryomc Image 把我附上的照片改成水彩风格。”（附上本机 PNG、JPEG 或 WebP；若 Codex 无法取得附件的本机路径，提供路径。）
- 如果自动识别不到，明确写 `$ryomc-image`，例如：“`$ryomc-image` 生成一张横版海报。”

Skill 会把当前对话的聊天模型 ID 作为 `--model` 传给脚本，例如当前选用 `gpt-6-sol` 时传 `--model gpt-6-sol`。Codex Desktop 没有向这个本地脚本提供可依赖的“当前对话模型”接口；如果 Skill 无法获知准确 ID，它会先问你，不会擅自使用安装时的旧模型。手动运行示例：

```text
python ryomc_image.py generate --model gpt-6-sol --prompt "雨夜咖啡店的插画"
```

生成图默认保存在本机 `~/Pictures/RyomcImages`。每次调用只生成一张；多张图片是多次请求。实际扣费请以站点使用日志为准。

## 可选：通过插件市场安装

仓库也包含 Codex 插件清单 `.agents/plugins/marketplace.json`。支持插件市场的 Codex 客户端可以运行 `codex plugin marketplace add 666666666666gao/image`，然后在 Desktop 的插件目录中选择 **Ryomc Image** 安装。插件安装后仍要在自己的终端运行 Skill 中的 `configure`，且本机必须有 Python 3.10+。直接复制 Skill 是最简单、最可控的安装方式。

## 本地验证

```text
python -m unittest discover -s tests -v
```

测试使用模拟响应，不发送真实生图请求，也不会扣费。
