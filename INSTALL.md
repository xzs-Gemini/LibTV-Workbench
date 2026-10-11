# 安装与账号

这是本地单用户源码版本，不是免安装程序或多人网站。已验证 Windows、Python 3.12 和 LibTV 官方 CLI 1.0.2。新工作台仅依赖 Python 标准库。

1. 安装 Git 和 Python 3.12（将 Python 加入 PATH），克隆本仓库并进入目录。
2. 从 LibTV 官方渠道安装 CLI。本仓库不重新分发 CLI 二进制文件。执行 `libtv --version` 检查版本；验证版本为 1.0.2，其他版本接口兼容性需要自行确认。
3. 执行 `libtv login web --open`，在官方网页登录自己的账号。无需向本仓库维护者提供密码或手动填写 API Key。
4. 执行以下命令，然后双击 `Start-Workbench.cmd`，或在 PowerShell 运行 `./Start-Workbench.ps1`。

```powershell
python -m venv .venv
```

若 CLI 未加入 PATH，可在启动前指定实际路径：

```powershell
$env:LIBTV_CLI = 'C:\path\to\libtv.exe'
& $env:LIBTV_CLI login web --open
./Start-Workbench.ps1
```

`LIBTV_PYTHON` 可指定 Python 可执行文件；否则启动脚本优先使用 `.venv`，再查找 PATH 中的 Python。CLI 优先使用 `LIBTV_CLI`，其次是本机 `.tools/libtv-1.0.2/libtv-win-x64/libtv.exe`，最后查找 PATH。

打开本机 `http://127.0.0.1:5212`，选择已有的 LibTV 项目、模型和参数后提交。账号必须有可用算力；具体模型与额度以平台返回为准。若账号没有项目，先在官方平台创建。

## 登录与数据边界

官方 CLI 在当前操作系统用户目录保存登录凭据；工作台通过 CLI 使用该登录状态。不要把凭据、`.tools/`、`.env` 或 `data/` 上传到仓库。多人共用一个后台会共用同一登录账号和额度；当前没有网站注册、用户隔离或权限系统，也不应直接对公网开放。

本地队列和结果在 `data/`，关闭网页不会停止后台任务。异常任务先核对云端状态，避免重复生成。视频生成还没有完成真实端到端验证；目前验证通过的是图片生成和下载。

## 测试

```powershell
python -m unittest discover -s tests -p test_workbench.py -v
```

此命令运行离线测试，不使用真实账号、不消耗平台算力。`scripts/` 中保留的是上游旧 Access Key 路径，详见原版说明，新工作台不使用它。
