# Tool Output Enrichment

对 ToolMessage 中的 JSON 数组内容进行自动字段分析，注入摘要前缀，消除 LLM 幻觉。

## 目录结构

```
tool_output_enrichment/
├── __init__.py                # enrich_result (ToolMessage/Command + config → enriched)
├── auto_json_analyzer.py      # AutoJsonAnalyzer: 采样 + 自动类型推断 + 10 层防护
├── enrichment_pipeline.py     # 插件链管理器 (当前仅 JSON，预留扩展点)
├── startup.py                 # monkey-patch 注入 _enrich_result (Level 3)
├── tests/
│   └── test_auto_json_analyzer.py  # 18 个单元测试 (10 层保护全覆盖)
└── README.md                  # 本文件
```

## 核心文件职责

| 文件 | 职责 |
|------|------|
| `auto_json_analyzer.py` | `_summarise_json_array(text, max_size)` — 自动检测 JSON 数组，注入摘要（项数、字段列表、类型分布）。10 层保护防止 OOM/crash |
| `enrichment_pipeline.py` | 轻量插件链，`enrich(text)` — 第一个匹配的插件胜出。当前仅 AutoJsonAnalyzer |
| `__init__.py` | `enrich_result(result, config)` — 兼容原 `_enrich_result` 签名，供 monkey-patch 替换 |
| `startup.py` | `install_tool_output_enrichment()` — monkey-patch 注入 + `_installed` 守卫 |

## 使用方式

**自动注入（推荐）：** 通过 `boot.py` 注册后，gateway 启动时自动 monkey-patch。
无需任何配置即可工作。

**手动测试：**
```python
from deerflow_extensions.tool_output_enrichment.auto_json_analyzer import _summarise_json_array
result = _summarise_json_array('[{"name": "test", "type": 0, "os": "linux"}]')
print(result)
# [Summary: 1 items fields: name, type, os type: all=0 os: linux=1]\n[...]
```

## 依赖

- `deerflow.config.tool_output_config.ToolOutputConfig` (读取 `preprocess_json` 等配置)
- `langchain_core.messages.ToolMessage` (消息类型)

## 侵入等级

**Level 3 (monkey-patch)** — 对标 `data_collection` / `topic_guardrail` 模式。
替换 `_enrich_result` 模块级函数，通过 LOAD_GLOBAL 在调用时解析。

## 防护层清单

1. len(text) > max_size → bail (防 OOM)
2. lstrip → 容忍前导空格
3. first char != '[' → bail (快速路径)
4. try json.loads → bail on parse error
5. isinstance list check → bail on non-array JSON
6. empty array → 返回空摘要
7. data[0] isinstance dict → 跳过原始类型数组
8. keys[:15] truncation → 防止超宽 schema
9. random.sample for distribution stats → O(1000) not O(N)
10. top-10 distribution cap → 摘要大小有界
