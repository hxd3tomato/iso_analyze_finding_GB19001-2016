# iso_analyze_finding_GB19001-2016

DeepSeek Harness 插件（bundle）：面向 **GB/T 19001-2016（ISO 9001:2015）贯标**的审核助手。
把"现象 → 条款 → 等级 → 陈述 → 整改 → 报告"这条链路做成 6 个模型可调用的工具。

- 0 个 npm 依赖；Python 侧只用标准库，离线可跑
- 知识库随包分发：57 个条款块、34 个不符合案例、238 条检查项
- 每条结论都带条款号、逐字引文与置信度；引文必须能在标准原文中找到

---

## 1. 工具

| 工具 | 作用 | 关键参数 |
|---|---|---|
| iso_analyze_finding | 现象定性：主条款 + 严重程度 + 四段式陈述 + 待补证据 + 追问链 + 整改三件套 | text（必填）、doc_ref、top_k、record |
| iso_match_clause | 只做条款匹配：Top N + 命中词 + 候选排除理由 | text、top_k |
| iso_suggest_capa | 整改三件套（纠正 / 纠正措施 / 验证）+ 责任 + 时限 + 横向排查 | clause（必填）、severity、text、doc_ref |
| iso_clause_lookup | 条款原文 / 意图 / 应查证据 / 易混条款 / 案例 / 检查项 | clause（必填） |
| iso_audit_findings | 本会话不符合清单（list 或 clear） | action |
| iso_audit_report | 生成内审报告（Markdown 汇总 + 逐条详情 + 等级统计） | audit_id、purpose、scope、date、team |

对话中的典型触发：

~~~text
用户：查机加工车间 2 号线，4 个工位还在用 B/2 版作业指导书，受控清单是 C/0 版
模型：iso_analyze_finding(...) -> 7.5.3 成文信息的控制；MAJOR（76）；排除 7.5.2 的理由；待补：发放记录、回收记录
用户：整改怎么做？
模型：iso_suggest_capa(clause="7.5.3", severity="MAJOR")
用户：把今天这几条出个报告
模型：iso_audit_report(audit_id="IA-2026-02")
~~~

---

## 2. 安装

### 方式 A：从 GitHub（推荐）

~~~bash
dsh plugin --profile desktop add github:hxd3tomato/iso_analyze_finding_GB19001-2016
~~~

私有仓库首次安装需要该 profile 有 GitHub 访问权限（环境变量 GITHUB_TOKEN 或 git 凭据）。
锁定到某个提交，避免后续推送改变实际运行的内容：

~~~bash
dsh plugin --profile desktop add github:hxd3tomato/iso_analyze_finding_GB19001-2016#<commit-sha>
~~~

### 方式 B：从本地目录

~~~bash
dsh plugin --profile desktop add ./iso_analyze_finding_GB19001-2016
~~~

### 方式 C：tarball（无需 git、无需构建授权）

~~~bash
pnpm pack
dsh plugin --profile desktop add ./iso_analyze_finding_GB19001-2016-0.1.0.tgz
~~~

### 方式 D：手工安装（没有 dsh CLI 时）

~~~powershell
powershell -ExecutionPolicy Bypass -File scripts/install.ps1
~~~

脚本会：复制到 profile 的 plugins/ 目录、写入 dependencies、把本包追加进 docs.profile.bundles、执行 pnpm install。

> 本包是**纯 JavaScript**，没有 prepare / build 脚本，因此 git 安装不需要 pnpm 的 allowBuilds 授权。

**安装后需重启 DeepSeek Harness 桌面应用**：profile 配置只在启动时组合。

### 自检

~~~text
在会话里说：用 iso_clause_lookup 查 7.5.3
或查看加载探针：Get-Content $env:TEMPiso-audit-plugin.log
~~~

探针会记录 module-import / apply-ok / apply-error 三类事件（可用环境变量 ISO_AUDIT_MARKER 改路径）。

---

## 3. 配置

在 profile 的 cordis.patch.yml 中按 id 覆盖（patch 会替换整行 config，需重述所有键）：

~~~yaml
- id: tool-iso-audit
  name: 'iso_analyze_finding_GB19001-2016'
  config:
    python: ''            # 解释器路径；留空则自动探测
    bridge: ''            # 默认包内 engine/bridge.py
    dataDir: ''           # 默认包内 knowledge/data
    timeoutMs: 60000
    recordByDefault: true
~~~

解释器探测顺序：config.python → 环境变量 ISO_KB_PYTHON → DSH 自带 Python（~/.dsh/dsh-runtimes/...）→ PATH 中的 python / python3 / py。

---

## 4. 运行机制

~~~text
模型调用工具
   │
   ▼
lib/tools.js    组装参数、渲染文本、维护按会话隔离的不符合清单
   │
   ▼
lib/engine.js   spawn(python engine/bridge.py <cmd>)，stdin/stdout 走 JSON
   │            强制 PYTHONUTF8=1 / PYTHONIOENCODING=utf-8（避免 Windows cp936 乱码）
   ▼
engine/iso_kb   Store.load(dataDir) → matcher（词项+先验+案例）/ severity / capa / analyzer
~~~

- 结论结构：clause_main + clause_candidates（含排除理由）+ severity（5 维得分）+ statement（四段式）+ capa（三件套）
- 输出校验：条款必须存在、引文必须是原文子串、禁止 2008 版编号、禁止空泛词
- 失败策略：引擎非 0 退出或超时 → 工具报错并附 stderr 尾部，不静默返回空结论
- 依赖兜底：宿主未提供 @deepseek-ai/dsh-tools 时，使用 lib/spec.js 的本地 schema 编译（已用宿主校验器验证）

---

## 5. 测试

~~~powershell
# 纯逻辑（普通 Node 即可，21 项断言）
node test/stub.mjs

# 宿主级（需在 DSH 运行时执行：import 真实 @deepseek-ai/dsh-tools）
# 设置 DSH_TOOLS_URL 指向 dsh-tools 的 lib/index.js 后运行 test/host.mjs
~~~

---

## 6. 卸载

~~~powershell
powershell -ExecutionPolicy Bypass -File scripts/uninstall.ps1
# 或：dsh plugin --profile desktop remove iso_analyze_finding_GB19001-2016
~~~

---

## 7. 故障排查

| 现象 | 原因 | 处理 |
|---|---|---|
| 重启后没有这 6 个工具 | 依赖或 bundles 未写入 | 检查 profile 的 package.json 与 dsh.profile.bundles，再重启 |
| 未找到可用的 Python 解释器 | PATH 无 python | 在 config.python 写明路径 |
| 中文乱码 / 无法匹配到任何条款 | stdio 非 UTF-8 | 确认 engine.js 设置了 PYTHONUTF8；bridge.py 有 reconfigure |
| 结论停在父条款（7.5 而非 7.5.3） | 现象缺具体证据词 | 补对象/编号/动作（4 个工位、B/2 版、未回收） |
| 报告为空 | 清单为空 | 先 iso_analyze_finding（record=true） |

---

## 8. 数据来源与免责

- 条款原文来自 GB/T 19001-2016 扫描件 OCR 后人工校正（confidence 0.85~0.95）；**对外出具报告应以正式出版文本为准**。
- 应用指南意图摘自 GB/T 19002-2018；案例库为共性案例，落地需结合行业与规模改写。
- 本插件不替代审核员判断：条款与等级须经审核组长复核后签发。

## 9. 知识库同步

engine/ 与 knowledge/data/ 是工作区引擎与知识库的快照：

~~~powershell
Copy-Item ..\plugin\iso_kb\*.py engine\iso_kb\ -Force
Copy-Item ..\knowledge\data\*.json knowledge\data\ -Force
~~~

MIT License.
