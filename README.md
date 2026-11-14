# gov-report-atlas

> 政策概念在中央—省—市三级文本中的扩散与转译：以「新质生产力」「人工智能+」为例

采集 2023–2026 年中央、31 个省级、333 个地级行政区的政府工作报告，约 1,400 份，
构建可复用的政策文本语料库，测量概念扩散的时滞、地方转译的相似度与先导性。

**数据不随仓库分发**：`data/manifest.csv` 记录每份文件的来源与 SHA256，
`make fetch` 可按清单重建语料。原始文本版权归各政府门户所有。

## 快速开始

```bash
pip install -e ".[dev]"
make test
make regions          # 校验并合并地区名单
make fetch LIMIT=30   # 先跑 30 份验证管道
```

## 三个研究问题

1. **扩散**：概念从中央提出到市级采纳用了多久？地理上有什么规律？
2. **转译**：地方是照抄还是改写？句级相似度测「复制率」，新增搭配测「地方化」。
3. **先导**：有没有地区在中央提出之前就用了？它们有什么共同特征？

## 数据来源与合规

- 全部为政府门户**公开**发布的政府工作报告；
- 不模拟登录、不绕验证码、不采集个人信息；
- 限速 1–2 req/s，遵守 robots；
- 仓库只放清单与衍生指标，不转发原文。

## 目录

```
config/     regions.yaml（样本框）、concepts.yaml（概念词典）
data/       manifest.csv（唯一事实来源）、regions_seed.csv
src/gra/    fetch / parse / attention / report
scripts/    build_regions.py（名单校验与合并）
docs/       concept_dict.md、qc_protocol.md
```

## 复现

```bash
make regions     # 地区名单校验
make fetch       # 按清单下载
make parse       # HTML/PDF -> 纯文本
make attention   # 注意力份额、首次出现、复制率
make test        # 不联网的单元测试
```

## 已知局限

- 时序仅四年，做不了长周期 S 曲线，只能做「提出前/后」的阶梯对比。
- 报告长度差异大，一律用「份额」而非「次数」。
- 概念词典有主观性，必须做敏感性分析。
- 部分市级报告为扫描件，OCR 误差会污染计数。

## 许可

代码 MIT；衍生数据 CC-BY-4.0。
