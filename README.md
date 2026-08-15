# Sharp Shooter

[![CI](https://github.com/peter8614/sharp-shooter/actions/workflows/ci.yml/badge.svg)](https://github.com/peter8614/sharp-shooter/actions/workflows/ci.yml)

Sharp Shooter 是一个篮球投篮姿势分析原型。Flutter 客户端负责录制或选择视频，Flask 后端提取 MediaPipe 上肢关键点和 YOLO 篮球轨迹，随后生成姿势/轨迹分类、处理后的视频，以及可选的 NBA 参考动作和 LLM 教练建议。

> 本项目处理视频和人体关键点，属于敏感的个人数据。部署前必须配置隐私政策、用户明确同意、数据保留期限和删除机制。

## 目录结构

- `mobile/`：当前 Flutter 客户端。
- `BackendServer/`：Flask API、视频分析管线和训练脚本。
- `BackendServer/data/`：训练索引和本地训练数据（不应直接发布含个人视频的数据）。
- `frontend/`：不连接真实 API 的静态展示页面。
- `PRIVACY.md` 与 `SECURITY.md`：数据处理和安全报告说明。

## 已落实的安全与正确性措施

- 服务端从 Firebase ID Token 取得 UID，不信任请求正文中的 `user_id`。
- 上传限制为可配置的 200 MiB，并检查扩展名、清理文件名和实际视频可解码性。
- 每个分析任务拥有独立工作目录；有界线程池避免无限创建线程。
- 所有处理视频统一转换为 H.264 MP4，兼容 Android 和 iOS。
- 分类器以“整段视频”为一个样本，避免同一视频的帧同时进入训练集和验证集。
- 模型文件包含版本和特征顺序；旧版模型不会被静默加载。
- 客户端不再绕过 TLS 证书验证，API 地址通过构建参数注入。
- 密钥、运行产物、上传视频、模型和本地数据目录已加入 `.gitignore`。

## 后端环境

要求：Python 3.11、`ffmpeg`、可运行项目自定义 YOLOv5 模型的环境，以及 Firebase 项目。

```powershell
cd BackendServer
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

编辑 `.env`：

- `FIREBASE_STORAGE_BUCKET`：Firebase Storage bucket。
- `FIREBASE_WEB_API_KEY`：仅用于 Firebase 邮箱登录 REST API。
- `GOOGLE_APPLICATION_CREDENTIALS`：仓库外的服务账号 JSON 绝对路径；云环境优先使用 Application Default Credentials。
- `OPENAI_API_KEY`、`OPENAI_MODEL` 与随机的 `SAFETY_IDENTIFIER_SALT`：仅在启用 LLM 建议时需要。LLM 请求使用不可逆用户伪标识并设置 `store=False`。
- `MAX_UPLOAD_BYTES`、`ANALYSIS_WORKERS`、`PORT`：可选运行参数。

不要把 `.env` 或服务账号 JSON 放入仓库。此前若密钥曾进入文件或 Git 历史，应立即在相应控制台撤销/轮换；仅从当前目录删除并不能使已泄露的密钥失效。

## 重新训练模型

旧的 `.pkl` 模型按帧拆分数据，验证结果存在泄漏，因此新版服务会拒绝加载。还应使用修正后的 MediaPipe 索引重新生成训练关键点，再执行：

```powershell
python landmark_classification.py
python trajectory_classification.py
```

训练索引 CSV 必须包含 `file_path,classification`，可从两个 `.example.csv` 文件复制。真实索引已清理重复项和指向缺失文件的记录，但因其文件名也可能包含个人信息，已被 Git 忽略。分类标签需由可靠的篮球教练或明确规则标注。当前小数据集只适合原型验证，不能将模型输出描述为专业诊断。

### 当前模型评价（2026-08-15）

每次训练固定执行 5 折、10 次重复分层交叉验证，报告 Accuracy、Balanced Accuracy、Macro Precision/Recall、Macro F1、混淆矩阵、各类别召回率及录像级 bootstrap 95% 置信区间。

- 姿势模型：Accuracy `81.7%`（95% CI `71.4%–90.6%`），Balanced Accuracy `66.4%`（`51.7%–82.0%`），Macro F1 `67.9%`（`51.1%–83.2%`）。重点指标 `bad_form` 召回率仅为 `41.4%`（`14.3%–71.4%`），坏姿势误判为好姿势的比例为 `58.6%`。
- 轨迹模型：Accuracy `95.6%`（`88.9%–100.0%`），Balanced Accuracy `90.0%`（`75.0%–100.0%`），Macro F1 `93.1%`（`80.0%–100.0%`）；`bad_trajectory` 召回率为 `80.0%`（`50.0%–100.0%`）。

完整报告见 [姿势模型评价](BackendServer/reports/landmark-evaluation.md) 和 [轨迹模型评价](BackendServer/reports/trajectory-evaluation.md)，评价方法见 [模型评价协议](docs/model-evaluation.md)。[2026-08-13 的旧指标和训练图](docs/training-results-2026-08-13.md) 已移入历史记录，没有被覆盖或删除。

这些结果属于小规模内部验证，不构成对新用户泛化能力的证明。后续应优先增加经过教练复核的坏姿势样本，按投篮者和拍摄场次分组切分，并使用完全独立的测试集验证。原始视频、私有索引和训练模型继续排除在 Git 之外。

## 启动 API

```powershell
python server.py
```

开发服务器仅监听 `127.0.0.1`。生产环境应使用 WSGI 服务、反向代理和有效 HTTPS 证书，并为 Firebase Storage/Firestore 配置最小权限规则。任务状态可通过带 Token 的 `GET /jobs/{job_id}` 查询。

## Flutter 客户端

```powershell
cd mobile
flutter pub get
flutter run --dart-define=BACKEND_URL=https://your-api.example.com
```

生产构建必须传入有效 HTTPS 地址。Android 和 iOS 权限说明已配置；若不需要录音，应同时关闭相机音频采集并移除麦克风权限。

## 测试

```powershell
cd BackendServer
python -m unittest discover -s tests -v
python -m compileall .

cd ..\mobile
flutter analyze
flutter test
```

完整端到端测试还需要 Firebase Emulator（或隔离测试项目）、`ffmpeg`、模型权重及一组没有隐私风险的短视频夹具。

GitHub Actions 会在向 `main` 推送或提交 Pull Request 时自动执行后端测试、Python 编译检查、Flutter 测试、Dart 静态分析和 Android Debug APK 构建。当前静态分析中的 warning 与 info 会显示在日志中但暂不阻断 CI；真正的分析 error、测试失败或构建失败仍会使检查失败。

## 发布前检查

1. 轮换任何曾经写入本地项目或 Git 历史的服务账号/OpenAI 密钥。
2. 不要提交 `uploads/`、`server_data/`、原始视频、关键点 CSV、模型或个人数据。
3. 重新生成关键点数据并训练新版模型，记录按拍摄者/场次隔离的评估指标。
4. 部署 HTTPS、最小权限 Firebase Rules、日志脱敏、持久化任务队列和数据删除流程。
5. 替换客户端内存态登录信息为安全会话持久化，并实现 Token 自动刷新。

详细的数据处理原则和漏洞报告方式分别参见 [PRIVACY.md](PRIVACY.md) 与 [SECURITY.md](SECURITY.md)。
