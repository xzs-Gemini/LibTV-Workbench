# LibTV 批量创作台

基于 [Qiuxiangxiang/libtv-skill-pro](https://github.com/Qiuxiangxiang/libtv-skill-pro) 的二次开发，保留原脚本；新增本地网页和持久化任务队列，实际生成使用 LibTV 官方 CLI 1.0.2。不是 LibTV 官方产品。

## 启动与使用

本仓库发布的是 Windows 本地单用户源码原型，不包含 Python、官方 CLI、登录凭据和生成记录。首次安装请阅读 [INSTALL.md](INSTALL.md)。原版脚本说明保存在 [UPSTREAM_README.md](UPSTREAM_README.md)，其中的安装命令安装的是上游版本。

在此目录用 PowerShell 运行 `./Start-Workbench.ps1`，打开 `http://127.0.0.1:5212`。后台已启动时直接打开页面即可，不必再次启动。

1. 选择 LibTV 项目、图片或视频、模型与参数。
2. 每行输入一条需求，点击“加入队列并开始生成”。每批最多20条，顺序执行。
3. 完成后点击图片或下载链接。文件和任务参数保存在 `data/outputs/<任务ID>/`。
4. 排队任务可取消。网络异常、重启后的未决任务点击“核对云端状态”，只查询/下载，不重复扣额度生成。

登录使用 `.tools/libtv-1.0.2/libtv-win-x64/libtv.exe login web --open`。凭据由官方 CLI 保存在用户目录，工作台不读取密码，不保存密钥。账号算力不足会暂停本地队列；处理额度后点击继续，只恢复尚未提交的任务，失败任务需要重新填写提交。

关闭页面不影响后台。关闭后台后，未提交任务在下次启动时继续；已经提交的任务先核对。当前版本没有云端取消功能。

## 验证记录（2026-10-11）

- 已真实登录、列出项目与模型、创建独立测试项目。
- 已真实生成并下载一张 Z-image Turbo 图片。
- 页面提交两条图片任务，远端明确返回“算力不足”，已保留失败记录；没有充值或购买。
- 下载链路使用上述真实成功节点验证，结果可在本地工作台查看。
- 视频模型列表/参数可查询；视频生成尚未通过实测（当前账号额度不足）。
- 单元测试覆盖任务完成、下载、重启恢复、超时不重发、取消和无效批次。

## 开发

`workbench/core.py`：CLI 适配与 SQLite 队列；`workbench/server.py`：仅本机 HTTP 服务；`workbench/web/`：中文界面。

运行测试：`python -m unittest discover -s tests -p test_workbench.py -v`。

可用环境变量 `LIBTV_CLI` 指定官方 CLI 路径，`LIBTV_PROJECT` 指定默认项目。原始 Access Key 脚本仍在 `scripts/`，不用于新工作台。其旧会话轮询现在只接受明确成功状态与结果附件；文本中的“正在生成”不会再被误判完成。

后续可增加素材参考输入、分镜模板、配音、字幕与 FFmpeg 剪辑。当前版本提供批量素材生成与下载，不声称已实现全自动成片。
