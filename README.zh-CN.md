# quotegate

[![Tests](https://github.com/Waldo0926/quotegate/actions/workflows/test.yml/badge.svg?branch=main)](https://github.com/Waldo0926/quotegate/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Dependencies: none](https://img.shields.io/badge/dependencies-none-brightgreen)

中文 · [English](README.md)

让大模型只能用你资料里原样摘出的句子回答，每一句在发给用户之前都由程序核对。

模型被要求按 `[2] 原样摘的句子` 的格式回复。`quotegate.check()` 只留下真的出现在第 2 段资料里、而且单独拿出来也不会被看错的句子，其余的都删掉并写明原因。不用第二个模型，不联网，没有依赖：纯字符串处理，每次结果都一样。

它是从[马莫百科公众号机器人](https://github.com/Waldo0926/mumguide-wechat-bot)里抽出来的。那个机器人给 Monash 的学生和家长回答签证、选课、考试的问题，多编一步比不回答更糟。

## 为什么不让模型自己写、再附上出处？

| 做法 | 能得到什么 | 挡不住什么 |
| --- | --- | --- |
| 模型自己写，附上来源 | 通顺的回复和链接 | 来源里没有的句子。一项对四个生成式搜索引擎的人工核查（[Liu、Zhang、Liang，EMNLP 2023 Findings](https://aclanthology.org/2023.findings-emnlp.467/)）发现，生成的句子只有 51.5% 能被它引用的来源完全支持 |
| 再用一个模型检查，比如 [Ragas faithfulness](https://docs.ragas.io/en/v0.2.0/concepts/metrics/available_metrics/faithfulness/) | 一个分数：裁判认为有依据的说法占多少 | 裁判本身会错，两个方向都会；而且是事后打分，不是发之前把关 |
| 模型厂商的引用功能，比如 [Claude 的 citations](https://docs.anthropic.com/en/docs/build-with-claude/citations) | 引用的原文保证指向你给的文档 | 引用之间的文字仍然是模型自己写的；而且绑定一家收费的 API |
| **quotegate** | 只有资料里真的有的句子，完整的一句，带资料编号 | 句子是真的、但回答的是别的问题。这要靠提示词和检索 |

在原来的机器人里，免费模型自己组织语言时，加了资料里没有的步骤（“老师会替你申请特殊考虑”），还把“ISP 在贴纸剩 14 天或更少时收护照”改成了“过期后有 14 天宽限期”。再用一个模型去检查，有的漏掉了，有的把对的句子删了。改成只许摘原句、程序逐字核对之后，这两个问题都没有了。

## 哪些会被删掉

摘句先扩展成它所在的完整句子，遇到下面的情况就删掉：

| 原因 | 例子 |
| --- | --- |
| `not found` | 改写过的、标错了资料编号的、编号不存在的 |
| `too short` | `[1] 上传`：不到 6 个字，说明不了什么 |
| `needs context` | 以“此流程”“不，”“但”“This must...”开头；以“：”“；并且”“and”结尾 |
| `list item` | “如果你没有满足上述任何一项要求：”下面的“· 你必须联系 ISP” |
| `a question` | 资料自己的 FAQ 问题 |
| `table row` | “10 月入学 \| OCT-MY-01 \| 2025年1月6日”：表头不在 |
| `past year` | 2026 年还发“自 2022 年起改为线上考试”。“过渡期到 2026 年 12 月 31 日”会保留 |
| `too long` | 扩展后超过 180 个字：其实是一整段没有句号 |
| `duplicate`、`over the limit` | 同一句出现两次，或超过 4 句 |

换行默认就是句子结束，除非资料设了 `soft_breaks=True`（公众号文章、PDF 抽出来的文字会在句子中间换行）。英文句号只有后面是空白时才算句子结束，所以“50.0”“monash.edu”不会被截断。

## 用法

```sh
pip install quotegate
```

```python
from quotegate import Passage, check
from quotegate.prompts import ZH, user_message

passages = [
    Passage("特殊考虑\n截止日期后两个工作日内在网上申请。此流程需要附上证明材料。", title="特殊考虑"),
    Passage("考试\n期末考试在第 13 和 14 周。"),
]
messages = [
    {"role": "system", "content": ZH},
    {"role": "user", "content": user_message("要多久之内申请？", [p.text for p in passages])},
]
reply = call_your_model(messages)   # 任何聊天模型都行，比如免费额度的
# reply == "[1] 截止日期后两个工作日内在网上申请\n[1] 此流程需要附上证明材料"

result = check(reply, passages)
result.status    # "ok"
result.kept      # [Quote(passage=1, text="截止日期后两个工作日内在网上申请。", start=5, end=22)]
result.dropped   # [Dropped(passage=1, quote="此流程需要附上证明材料。", reason="needs context")]
```

`result.status` 不是 `"ok"` 时，模型的回复一句都别发：`"unsure"`（模型说不确定）、`"uncited"`（没有摘句的行）、`"unsupported"`（没有一句在它标的资料里）、`"fragment"`（找到了，但没有一句能单独看）。原来的机器人会把这些问题转给人工。

`start` 和 `end` 是这句话在资料里的位置，可以拿来加链接或高亮。发出去时把 `kept` 和它们来自的页面一起列出，并写一句“以上是原文摘录”。

### 规则

`check(reply, passages, Rules(...))`：

| 字段 | 默认 | |
| --- | --- | --- |
| `min_chars`、`max_chars`、`max_quotes` | 6、180、4 | |
| `leans_back`、`leans_on` | 中英文的承接词 | 正则：开头或结尾要靠没给出的上下文才读得懂。`quotegate.core` 里中文和英文是分开的 |
| `stops` | `✓✔｜` | 没有句号也算句子结束的字符 |
| `current_year` | 今年 | 给 `past year` 用；设成 `0` 就不检查 |
| `unsure` | 不确定、不知道、not sure 等 | 很短的回复里有这些就是 `"unsure"` |
| `checks` | 无 | 你自己的检查：`fn(句子, 资料) -> 原因或 None` |

`Passage(text, title=None, soft_breaks=False, qa=False)`：以 `title` 那一行开头的资料，句子不会往前扩展到标题里；`qa=True` 表示这段资料是在回答标题里的问题，所以“答：”后面紧跟的“可以，……”不算承接上文。

## 数字

来自原来那个机器人的评测（[docs/EVAL.md](https://github.com/Waldo0926/mumguide-wechat-bot/blob/main/docs/EVAL.md)，50 题，2026-10-25，Groq 免费的 `qwen/qwen3.8-27b`）：

| | 只用规则 | 规则 + 只许摘原句的模型 |
| --- | --- | --- |
| 资料里没有答案的题，没有乱答、转给人工 | 7 题里 1 题 | 7 题里 6 题 |
| 核对删掉了至少一句摘句的模型调用 | - | 29 次里 8 次 |
| 一句都不能发的模型调用 | - | 29 次里 2 次 |

核对本身很快：4 句摘句对 5 段各 500 字的资料，一次约 0.3 毫秒（2026-10-26 在云端容器的一个 CPU 核上测的）。

## 不适合

- 需要跨资料推理或计算的回答。摘句只能说资料里说过的话。
- 判断一句话是不是在回答这个问题。检索不好，摘出来的就是真的但无关的句子。
- 翻译：用资料本身的语言摘，资料提前翻译好。

## 开发

```sh
uv venv && uv pip install -e . pytest ruff
.venv/bin/pytest -q && .venv/bin/ruff check .
```

发版：改 `src/quotegate/__init__.py` 里的 `__version__`，在 `CHANGELOG.md` 加一节，合并，然后推 `v<版本>` 标签。`release.yml` 会核对标签和版本号、跑测试，再用 Trusted Publishing 发到 PyPI。

## 许可

[MIT](LICENSE) © Waldo
