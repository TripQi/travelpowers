# TravelPowers

**从创意到交付的结构化 AI 开发工作流框架**

TravelPowers 是一套为 大模型 设计的多阶段技能（Skill）工作流，将软件开发过程拆解为 **设计 → 计划 → 任务编译 → 闭环执行** 四个阶段，每个阶段由专属技能驱动，并通过自动化健康门（Health Gate）保障质量。核心思路借鉴了 superpowers。

---

## 工作流全景

```
 ┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────────┐
 │   designing   │────▶│   planning   │────▶│compile-plans │────▶│executing-plan-   │
 │              │     │              │     │              │     │     issues        │
 │  探索需求     │     │  编写计划     │     │  编译任务     │     │  闭环执行         │
 │  提出方案     │     │  拆分步骤     │     │  生成 JSONL   │     │  实现→审查→提交    │
 │  获取批准     │     │  定义验收     │     │  建立依赖     │     │  逐条推进         │
 └──────┬───────┘     └──────────────┘     └──────────────┘     └──────────────────┘
        │                    │                    │                       │
        │ [fast-track]       ▼                    ▼                       ▼
        ├─────────────▶ 直接执行 + 提交   计划文档 (.md)      任务快照 (.jsonl)      代码 + 提交
        │              (跳过中间阶段)     docs/plans/          docs/issues/
        ▼
   设计文档 (.md)
   docs/designs/
```

**辅助技能** 贯穿全流程：

| 技能 | 作用 |
|------|------|
| `travelpowers-workflow-status` | 自动检测当前阶段，路由到下一个技能 |
| `workflow-health-check` | 在关键节点运行自动化验证 |
| `writing-clearly-and-concisely` | 改善文档和 UI 文本的可读性 |

---

## 四个核心阶段

### Phase 1: Designing — 设计

> 任何项目都必须经过设计，哪怕它"看起来很简单"。

- 探索项目上下文（文件、文档、提交历史）
- 逐个提出澄清问题，理解真实意图
- 提出 **2-3 个方案** 并分析利弊，给出推荐
- 分段呈现设计，逐段获得用户批准
- 输出设计文档：`docs/designs/YYYY-MM-DD-<topic>-design.md`

**硬门控**：设计未获批准前，禁止任何实现动作。

**快速通道（Fast-Track）**：对于满足全部 7 项资格标准的极小变更（单文件、≤30行、无新依赖、无 API 变更、明显正确、已有测试、用户批准），可跳过后续三个阶段，直接执行并以 `[fast-track]` 标签提交。

### Phase 2: Planning — 编写计划

> 假设执行者对代码库一无所知，把一切写清楚。

- 将已批准的设计拆分为 **可独立交付的功能模块**
- 每个任务包含：优先级、依赖、验收标准、需触及的文件、测试策略
- 执行 agent 自主决定实现节奏（TDD、code-first 均可）
- 输出计划文档：`docs/plans/YYYY-MM-DD-<feature-name>.md`
- 通过健康门验证计划结构

### Phase 3: Compile Plans — 编译任务

> 从人类可读的计划到机器可执行的任务快照。

- 将计划中的每个 Task 映射为一条 JSONL issue 记录
- 自动生成结构化 ID（如 `AUTH-010`、`AUTH-020`）
- 构建拓扑排序的依赖图，检测循环依赖
- 输出任务快照：`docs/issues/YYYY-MM-DD_HH-mm-ss-<slug>.jsonl`
- 通过健康门验证 JSONL 模式

### Phase 4: Executing Plan Issues — 闭环执行

> 实现 → 审查 → 自验证 → 提交，一条都不能少。

对每条 issue 执行完整闭环：

```
选择 issue（无阻塞、依赖已完成）
    │
    ├── 实现代码 + 同步文档
    ├── 开发审查（编码标准）
    ├── 回归审查（无副作用）
    ├── 自验证（根据验收标准提供证据）
    └── Git 提交（代码 + JSONL 状态更新）
```

**状态机驱动**，每条 issue 追踪四个维度：

| 字段 | 取值 | 含义 |
|------|------|------|
| `dev_state` | pending → in_progress → done | 开发进度 |
| `review_state` | pending → in_progress → done | 审查状态 |
| `git_state` | uncommitted → committed | 提交状态 |
| `blocked` | false / true | 是否阻塞 |

**闭环完成** = 四个字段全部达到终态。

---

## 核心设计理念

### JSONL 作为唯一真相源

Issues JSONL 文件不仅是任务列表，更是整个工作流的状态数据库：
- 每条 issue 的状态实时更新
- 支持中断后恢复（重新读取 JSONL 即可继续）
- 提供完整的审计跟踪

### 健康门（Health Gate）

在关键阶段自动运行验证，拦截结构性错误：

```bash
# 计划编写后
python workflow_health_check.py --mode plan --plan <path> --fail-on error

# 任务编译后
python workflow_health_check.py --mode issues --issues <path> --fail-on error

# 最终收敛
python workflow_health_check.py --mode full --plan <plan> --issues <jsonl> --fail-on error
```

验证内容包括：JSONL 模式完整性、枚举值合法性、依赖图有效性、状态一致性。

### 反模式防护

| 反模式 | 防护机制 |
|--------|----------|
| "太简单不需要设计" | 所有项目强制经过 designing |
| 无限重试循环 | 最多 2 次重试（初始 + 1 次） |
| 跳过测试 | 验收标准和测试方法为必填字段 |
| 隐式依赖 | `depends_on` 强制显式声明 |
| 范围蔓延 | 每条 issue 严格限定在 JSONL 描述的边界内 |

### 优雅降级

当环境限制（无权限、缺依赖、CI 不可用）阻止完整验证时：
- 不阻塞交付，继续推进
- 在 `notes` 中记录：`validation_limited:<原因>`、`manual_test:<后续命令>`、`risk:<等级>`
- 移交时明确说明未测试的内容

---

## 项目结构

```
travelpowers/
├── designing/                          # Phase 1: 设计
│   └── SKILL.md
├── planning/                           # Phase 2: 编写计划
│   └── SKILL.md
├── compile-plans/                      # Phase 3: 编译任务
│   └── SKILL.md
├── executing-plan-issues/              # Phase 4: 闭环执行
│   └── SKILL.md
├── travelpowers-workflow-status/       # 辅助: 状态检测与路由
│   └── SKILL.md
├── writing-clearly-and-concisely/      # 辅助: 清晰写作
│   ├── SKILL.md
│   └── elements-of-style.md
├── workflow-health-check/              # 辅助: 自动化验证
│   ├── SKILL.md
│   ├── workflow_health_check.py
│   └── test_workflow_health_check.py
└── README.md
```

---

## 快速开始

### 1. 安装

将本仓库克隆到 Claude Code 的技能目录：

```bash
git clone <repo-url> ~/.codex/skills/travelpowers
```

### 2. 使用工作流

在 Claude Code 中直接调用技能名称即可：

```
/designing              # 开始设计，探索需求
/planning              # 将设计转化为实现计划
/compile-plans          # 将计划编译为 JSONL 任务快照
/executing-plan-issues  # 闭环执行所有任务
```

**不确定当前进度？** 使用状态检查自动路由：

```
/travelpowers-workflow-status   # 检测当前阶段，自动跳转
```

### 3. 产出物

工作流产生的文档统一存放在项目的 `docs/` 目录下：

```
your-project/
└── docs/
    ├── designs/    # 设计文档
    ├── plans/      # 实现计划
    └── issues/     # JSONL 任务快照
```

---

## 示例：添加 JWT 认证

```
1. /designing
   → 讨论认证方案：JWT vs Session vs OAuth
   → 用户批准 JWT 方案
   → 产出: docs/designs/2026-02-18-jwt-auth-design.md

2. /planning
   → Task 1: 实现 token 生成 (P0, 后端, 无依赖)
   → Task 2: 认证中间件 (P0, 后端, 依赖 Task 1)
   → Task 3: 路由集成 (P1, 后端, 依赖 Task 2)
   → 产出: docs/plans/2026-02-18-jwt-auth.md

3. /compile-plans
   → 生成 JSONL: AUTH-010, AUTH-020, AUTH-030
   → 依赖关系: AUTH-020→AUTH-010, AUTH-030→AUTH-020
   → 产出: docs/issues/2026-02-18_10-30-00-jwt-auth.jsonl

4. /executing-plan-issues
   → 执行 AUTH-010 → 实现+审查+提交
   → 执行 AUTH-020 → 实现+审查+提交
   → 执行 AUTH-030 → 实现+审查+提交
   → 全部闭环完成 ✓
```

---

## 设计原则

| 原则 | 说明 |
|------|------|
| **强制设计先行** | 不论任务大小，都必须先设计后实现 |
| **功能模块粒度** | 每个 Task 是可独立交付的功能模块 |
| **执行自主** | 执行 agent 自主决定实现节奏 |
| **闭环非妥协** | 实现+审查+验证+提交，缺一不可 |
| **KISS / YAGNI** | 只做当前任务要求的，不做假设性扩展 |
| **可中断可恢复** | JSONL 状态持久化，随时可以从断点继续 |
| **低误报验证** | 健康门只在确定性错误时报错，不制造噪音 |
| **快速通道** | 极小变更（7 项硬性标准全满足）可跳过中间阶段，避免流程开销 |

---

## License

MIT
