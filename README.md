# Action (Reaction Time Bot)

**By Fan1337**

Human Benchmark 反应测试自动化工具。

## 简介

Action 是一个针对 [Human Benchmark](https://humanbenchmark.com/tests/reactiontime) 反应测试的自动化辅助工具。程序会监测屏幕中心像素的颜色变化，当检测到绿色时立即触发点击。

## 工作原理

1. **锁定坐标** - 将鼠标移动到屏幕中心
2. **像素监测** - 持续抓取中心像素的颜色值
3. **触发点击** - 当绿色值超过阈值时，使用 Win32 API 极速点击
4. **等待恢复** - 等待颜色恢复后继续监测

## 功能特点

- 像素级颜色检测
- Win32 SendInput 极速点击
- 自动 DPI 缩放适配
- 一键开关控制
- 现代化深色 UI 界面
- 实时日志输出
- 窗口置顶显示

## 使用方法

1. 打开 Human Benchmark 反应测试页面
2. 浏览器全屏 (F11) 且缩放 100%
3. 运行本程序
4. 点击 **TRIGGERBOT** 开关启用
5. 3 秒后程序自动锁定屏幕中心并开始监测
6. 当屏幕变绿时自动点击

## 界面说明

| 组件 | 说明 |
|------|------|
| TRIGGERBOT 开关 | 控制自动点击功能的开启/关闭 |
| 状态指示 | ON (运行中) / OFF (待机) |
| 日志区域 | 显示程序运行状态和点击记录 |

## 系统要求

- Windows 10/11
- Python 3.10+ (源码运行)

## 依赖项

```bash
pip install PySide6 mss
```

## 文件结构

```
Action/
├── main.py           # 主程序
├── nl_icon.ico       # 程序图标
└── README.md         # 说明文档
```

## 编译打包

```bash
pyinstaller --onefile --windowed --icon="nl_icon.ico" --name="Action" main.py
```

## 配置参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| GREEN_THRESHOLD | 绿色触发阈值 | 170 |

如需调整灵敏度，可修改 `main.py` 中的 `GREEN_THRESHOLD` 值。

## 注意事项

- 请确保浏览器全屏且缩放为 100%
- 测试页面需要在主显示器上
- 启动后请勿移动鼠标

## 版本

Build 1337 | Reaction Bot

## 免责声明

本工具仅供学习和娱乐用途。
