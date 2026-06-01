# 直播录屏 v2.0

多平台直播录制工具，支持抖音、B站、微信视频号。

## 功能特性

- 多平台支持：抖音、B站、微信视频号
- FFmpeg 录制，零编码损耗（`-c copy`）
- 无并发录制数量限制
- 微信视频号自动嗅探
- Webhook 消息推送通知
- 深色主题 GUI

## 下载

前往 [Releases](https://github.com/RainsClear3/liverec/releases) 页面下载对应平台的可执行文件：

| 平台 | 架构 | 文件 |
|------|------|------|
| Windows | x64 | `live-recorder-windows-x64.exe` |
| Windows | ARM64 | `live-recorder-windows-arm64.exe` |
| Linux | x64 | `live-recorder-linux-x64` |
| Linux | ARM64 | `live-recorder-linux-arm64` |
| macOS | Intel (x64) | `live-recorder-macos-x64` |
| macOS | Apple Silicon (ARM64) | `live-recorder-macos-arm64` |

## 安装使用

### Windows
直接双击 `live-recorder-windows.exe` 运行。

### Linux
```bash
chmod +x live-recorder-linux
./live-recorder-linux
```

### macOS
首次运行会提示"无法验证开发者"，请按以下步骤操作：

**方法一（推荐）：右键打开**
1. 右键点击下载的文件（如 `live-recorder-macos-arm64`）
2. 选择"打开"
3. 弹窗中再次点击"打开"

**方法二：终端移除隔离标记**
```bash
xattr -d com.apple.quarantine live-recorder-macos-arm64
./live-recorder-macos-arm64
```

## 从源码运行

```bash
git clone https://github.com/RainsClear3/liverec.git
cd liverec
pip install -r requirements.txt
python main.py
```

## 配置说明

首次运行会自动生成 `config.json`，可在 GUI 中通过"设置"修改：

- **清晰度**：流畅 / 标清 / 高清 / 超清
- **输出格式**：ts / mp4 / flv
- **检查间隔**：默认 15 秒
- **保存路径**：录制文件保存位置
- **Webhook 推送**：支持开播、录制开始/结束通知

## 依赖

- Python 3.10+
- FFmpeg（已内置 Windows 版本）
- ttkbootstrap / pystray / Pillow / aiohttp / mitmproxy

## License

MIT
