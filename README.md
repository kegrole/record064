# neardup：商品标题近重复去重

纯 Python 标准库实现（无任何第三方依赖）。把每条文本压成 64 位 SimHash
指纹，再按指纹之间的汉明距离找出"换了标题的同款商品"。

## 运行

```bash
# 生成演示语料（可选，仓库已带一份）
python demo/generate_corpus.py --out demo/corpus

# 跑近重复检测，写报告并在 stdout 打印一行摘要
python -m neardup.cli --dir demo/corpus --out out/report.json
# 输出示例：processed=100000 near_duplicate_groups=50 buckets=202233

# 测试（两种入口等价）
cd tests && python -m unittest test_neardup -v
python -m unittest tests.test_neardup -v
```

`--dir` 指向语料目录：目录下每个 `*.txt` 文件（按文件名排序）的每个非空行
算一条记录。`--threshold` 可调汉明距离阈值，默认 3。

## 分词与加权（neardup/tokenize.py）

- 中文按字切分：每个 CJK 汉字（\u3400-\u4dbf、\u4e00-\u9fff、\uf900-\ufaff）
  独立成为一个词。
- 英文按单词切分：连续的 ASCII 字母/数字（`[A-Za-z0-9]+`）算一个词。
- 其余字符（空白、标点、符号）一律视为分隔符，不成词。
- 词频加权：每个词的权重 = 出现次数 × 词长（字符数）。汉字词长为 1，
  英文单词词长即字母数，长词对指纹的影响更大。

## SimHash 指纹（neardup/simhash.py）

1. 每个词用 SHA-256 取摘要前 8 字节，按大端读成 64 位整数作为词哈希。
2. 对 64 个位逐一累加：词哈希该位为 1 则加权重，为 0 则减权重。
3. 累加和为正的位输出 1，否则输出 0，得到 64 位指纹。

实现上把 64 个累加器打包进一个大整数（每位一个 32 位字段）做位切片累加，
结果与逐位循环完全一致，但 10 万条语料整体处理只需几秒。哈希用 SHA-256
而非内置 `hash()`，保证跨进程、跨次运行结果一致。

## 近重复判定（neardup/matcher.py）

两个指纹的汉明距离 ≤ 阈值（默认 3，`--threshold` 可配）即判为近重复。
满足条件的记录用并查集归并成组。

## 分桶加速与漏判风险（neardup/buckets.py）

- 64 位指纹从最高位起均分成 `threshold + 1` 个段（band）。默认阈值 3 时
  为 4 段 × 16 位：band 0 是第 63..48 位（高位段），band 3 是第 15..0 位。
- 每条记录按每个段的段值各进一个桶，桶键为 `(段号, 段值)`；只对共享同一
  个桶的记录对计算汉明距离，避免 O(n²) 全量两两比较。
- 不漏判的依据（鸽巢原理）：汉明距离 ≤ t 的两个指纹，差异位最多落在 t 个
  不同的段里，而段数为 t+1，因此至少有一个段完全相同，二者必然共享该段
  的桶。即使两个指纹的高位前缀不同（落在 band 0 的不同桶），它们仍会在
  其余某个完全相同的段里相遇，所以跨桶的近重复对一定能被找到。
- 漏判风险：在上述段数规则（段数 = 阈值 + 1）下不存在漏判；唯一的近似
  来自 SimHash 本身——内容差异很大的文本理论上也可能距离 ≤ t（假阳性），
  内容相近的文本也可能距离 > t（假阴性），这是局部敏感哈希的固有特性。
- 报告中的 `buckets` 是实际用到的非空桶数（所有段索引下的去重桶键总数）。

## 两种重复的区分（neardup/report.py）

- `exact`（内容完全相同）：组内至少两条记录的 SHA-256 相同，即内容逐字节
  一致。
- `fingerprint`（仅指纹接近）：组内所有记录的 SHA-256 互不相同，仅因
  SimHash 指纹距离不超过阈值而归为一组。

## 报告字段

顶层只有三个字段：

- `processed`：处理的记录总数。
- `groups`：重复组列表。每组含 `group_id`（按组内最小记录 id 排序后顺序
  编号，同一输入两次运行编号序列一致）、`size`（组内条目数）、
  `match_type`（`exact` 或 `fingerprint`）、`members`（每条记录的 `id`、
  `source`（文件:行号）、`sha256`）。
- `buckets`：分桶加速实际用到的桶数。

## 目录结构

- `neardup/`：tokenize / simhash / buckets / matcher / report / cli / __main__
- `demo/generate_corpus.py`：按固定种子生成 10 万条语料（恰好 50 对近重复）
- `demo/corpus/`：已生成的演示语料
- `tests/test_neardup.py`：覆盖判定口径的 unittest（语料在临时目录现造）
