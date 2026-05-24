# WhiteoutSurvivalAutoScript

针对《无尽冬日》的雷电模拟器自动化脚本工具，基于 PyQt5 桌面界面、ADB 输入、OpenCV 模板识别实现。当前版本支持多模拟器选择、任务配置编辑、分批上线调度、模拟器间串行动作节流、被顶号重登恢复、任务乱序执行和单文件打包。

> 自动化脚本可能违反游戏规则或平台条款。请自行承担账号、设备和使用风险。

## 功能概览

- 雷电模拟器列表读取、启动、关闭和任务绑定。
- 任务配置可视化编辑，并保存为 `configs/*.json`。
- 配置级任务乱序执行，不修改原任务列表顺序。
- 最大同时在线模拟器数量控制：达到上限后，某个模拟器完成并下线，调度器再启动下一个。
- 模拟器间 ADB 输入动作串行节流，可配置任意两次真实输入动作的最小间隔。
- 被顶号后自动等待、点击重新登录，并恢复到当前任务的初始可识别页面后重跑任务。
- 模拟器列表展示当前正在运行的任务。
- 单文件 PyInstaller 打包，运行配置写入用户目录。

## 环境要求

- Windows
- Conda 环境：`WhiteoutSurvivalAutoScript`
- Python 3.11
- 雷电模拟器 9
- 雷电 `ldconsole.exe` 与 `adb.exe`
- 依赖见 [requirements.txt](requirements.txt)

创建或进入环境后安装依赖：

```powershell
conda activate WhiteoutSurvivalAutoScript
pip install -r requirements.txt
```

如果需要重新打包，还需要安装 PyInstaller：

```powershell
pip install pyinstaller
```

## 运行

源码运行：

```powershell
conda activate WhiteoutSurvivalAutoScript
python main.py
```

单文件发布版运行：

```powershell
dist\闪电模拟器.exe
```

首次运行会初始化用户数据目录，并把默认配置复制过去。

## 用户配置目录

运行时可变配置不会写在 exe 同目录，而是写入用户目录：

```text
C:\Users\<用户名>\AppData\Roaming\WhiteoutSurvivalAutoScript
```

主要文件：

- `config.json`：全局配置、模拟器绑定、执行设置、雷电路径。
- `configs/*.json`：任务配置文件。

可以通过环境变量覆盖用户数据目录，便于测试或多套配置隔离：

```powershell
$env:WHITEOUT_AUTO_DATA_DIR = "D:\whiteout-auto-data"
python main.py
```

## 雷电模拟器路径配置

界面中有 `模拟器路径` Tab：

- `ldconsole.exe`：雷电命令行工具路径。
- `adb.exe`：雷电自带 ADB 路径。
- 可以分别选择两个 exe，也可以选择雷电安装目录自动填充。

保存后会写入用户目录下的 `config.json`，并刷新模拟器列表。默认路径在 [config_manager.py](config_manager.py) 中：

```text
E:\leidian\LDPlayer9\ldconsole.exe
E:\leidian\LDPlayer9\adb.exe
```

## 基本使用流程

1. 打开程序。
2. 在 `模拟器路径` 中确认或选择雷电安装路径。
3. 在 `配置` Tab 创建或修改任务配置。
4. 保存配置名称。
5. 在 `模拟器列表` 中勾选要执行的模拟器，并绑定配置。
6. 在 `执行设置` 中设置分批、串行动作、重登等待等参数。
7. 点击 `开始执行`。

## 执行设置

全局执行设置保存在用户目录 `config.json`：

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `batch_enabled` | `false` | 是否启用分批调度。 |
| `batch_size` | `1` | 最多同时在线的模拟器数量。 |
| `batch_cycle_mode` | `loop` | 所有模拟器跑完后继续循环。 |
| `serial_actions_enabled` | `false` | 是否启用模拟器间 ADB 输入串行动作。 |
| `serial_action_interval_sec` | `1.0` | 任意两次真实输入动作开始时间的最小间隔，可为小数。 |
| `relogin_interval_sec` | `0.0` | 检测到被顶号后，点击重新登录前等待的秒数。 |
| `batch_start_timeout_sec` | `180` | 启动模拟器并等待 ADB 可用的超时时间。 |
| `batch_between_delay_sec` | `3.0` | 模拟器完成关闭后，启动下一个模拟器前的等待时间。 |
| `session_retry_limit` | `3` | 被顶号恢复后，当前任务最多重试次数。 |

`batch_size` 的语义是“最多同时在线数量”，不是固定批次一起完成。某个模拟器完成一轮配置后会立即下线，调度器再补下一个模拟器上线。

## 任务配置

任务配置保存在用户目录的 `configs/*.json`。示例：

```json
{
  "name": "test",
  "shuffle_tasks": true,
  "tasks": [
    {
      "name": "自动集结冰原巨兽",
      "params": {
        "beast_level": 8,
        "formation_indices": "8",
        "rally_duration_minutes": 5
      }
    },
    {
      "name": "自动挖矿",
      "params": {
        "queue1_enabled": true,
        "queue1_resource_type": "生肉",
        "queue1_resource_level": 8
      }
    }
  ]
}
```

`shuffle_tasks` 是绑定在任务配置文件上的开关。启用后，每轮执行时复制任务列表并随机打乱，不会改写配置文件中的原始顺序。

## 内置任务

当前任务由 Python 模块和 YAML 共同注册，启动时自动加载：

- `自动打开游戏`
- `重新登录`
- `返回主页`
- `打开联盟`
- `建棋`
- `自动洗练`
- `自动集结冰原巨兽`
- `自动挖矿`

任务开始前会根据注册的 `initial_state` 尝试恢复页面：

- `any`：不强制恢复页面。
- `wild`：确保游戏打开并回到野外可识别状态。
- `home`：尝试回到主页。
- `manual`：保留手动入口要求，只记录日志提示。

## 模板资源

模板图片位于 `buttons/`：

- `buttons/beast_rally/`：冰原巨兽集结相关模板。
- `buttons/gather/`：采集相关模板。
- `buttons/march_queue/`：行军队列识别模板。

打包为单文件 exe 后，这些模板会内置到 exe 中。运行时程序会通过 PyInstaller 解包目录读取模板，不需要把 `buttons/` 放在 exe 旁边。

## 打包

当前 [main.spec](main.spec) 使用 PyInstaller 单文件模式，并内置：

- `buttons/`
- `configs/`
- `tasks/*.yaml`
- `tasks` Python 子模块

打包命令：

```powershell
conda activate WhiteoutSurvivalAutoScript
python -m PyInstaller --noconfirm --clean main.spec
```

输出：

```text
dist\闪电模拟器.exe
```

`build/` 和 `dist/` 已在 `.gitignore` 中忽略。

## 常见问题

### 模拟器列表刷新失败

先检查 `模拟器路径` Tab 中的 `ldconsole.exe` 和 `adb.exe` 是否存在。路径保存后会立即重建模拟器管理器并刷新列表。

### 任务提示游戏未打开或无法识别页面

确认：

- 模拟器分辨率和模板采集时一致。
- 游戏已经安装且桌面图标模板 `buttons/button1.png` 能识别。
- 当前任务的初始状态是否需要手动进入页面，例如 `自动洗练`。

### 行军队列显示未识别

行军队列识别依赖模板和绿色进度条启发式判断。若游戏 UI 变化导致误判，需要补充 `buttons/march_queue/` 下的模板。

### 单文件启动较慢

PyInstaller onefile 会先解包运行时和资源，首次启动会比源码运行或 onedir 模式慢，这是正常现象。

## 开发建议

- 搜索文件优先使用 `rg`。
- 修改任务参数时同步检查 `TaskConfigEditor.py` 和任务的 `param_defs`。
- 新增模板时尽量裁剪稳定区域，避免包含动态文字、倒计时和玩家名称。
- 新增任务时使用 `@register_task(..., initial_state=...)` 明确任务初始页面要求。
