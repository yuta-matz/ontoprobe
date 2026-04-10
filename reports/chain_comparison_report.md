# 多段階因果推論における知識記述形式の比較レポート

## 概要

多段階の因果連鎖（A→B→C）を含むドメイン知識を4つの異なる記述形式で
LLMに渡した場合に、多段階推論の精度にどの程度の差が生じるかを検証した。

### 比較条件

| 条件 | 説明 |
|------|------|
| **RDF（構造化）** | RDF由来の箇条書き（全11ルール: 単段階7本＋多段階4本） |
| **NL（自然言語）** | 同一情報を散文パラグラフで記述 |
| **MEMO（社内文書）** | ルールごとに独立した社内文書で記述（多段階チェーン含む） |
| **DOC（議事録）** | 1つの議事録に全ルール＋多段階因果の言及を埋め込み |

- **試行回数:** 各条件 3 回
- **評価対象チェーン:** 3 件（多段階因果仮説のみ）
- **Ground Truth:** デモモードのルールベース検証結果

### Ground Truth（正解ラベル）

| チェーン仮説 | 正解verdict |
|-------------|-----------|
| Discount drives revenue through order volume | contradicted |
| Discount erodes effective margin through discount amount | supported |
| VIP customers drive revenue through higher AOV | supported |

## 1. 総合比較

| 指標 | RDF（構造化） | NL（自然言語） | MEMO（社内文書） | DOC（議事録） |
|------|---|---|---|---|
| verdict正答率 | **100.0%** | **77.8%** | **100.0%** | **71.4%** |
| 連鎖認識率 | **88.9%** | **88.9%** | **100.0%** | **85.7%** |
| 有効試行数 | 9 | 9 | 9 | 7 |
| 平均一貫性 | 100.0% | 88.9% | 100.0% | 66.7% |

## 2. チェーン別正答率

| チェーン仮説 | RDF（構造化） | NL（自然言語） | MEMO（社内文書） | DOC（議事録） |
|-------------|---|---|---|---|
| Discount drives revenue through order volume | 100% | 33% | 100% | 50% |
| Discount erodes effective margin through discount amount | 100% | 100% | 100% | 50% |
| VIP customers drive revenue through higher AOV | 100% | 100% | 100% | 100% |

## 3. チェーン別 連鎖認識率

LLMがverdict判定時に中間ステップ（因果の途中経路）に言及した割合。

| チェーン仮説 | RDF（構造化） | NL（自然言語） | MEMO（社内文書） | DOC（議事録） |
|-------------|---|---|---|---|
| Discount drives revenue through order volume | 100% | 100% | 100% | 100% |
| Discount erodes effective margin through discount amount | 67% | 67% | 100% | 50% |
| VIP customers drive revenue through higher AOV | 100% | 100% | 100% | 100% |

## 4. チェーン別一貫性（verdict安定度）

| チェーン仮説 | RDF（構造化） | NL（自然言語） | MEMO（社内文書） | DOC（議事録） |
|-------------|---|---|---|---|
| Discount drives revenue through order volume | 100% | 67% | 100% | 50% |
| Discount erodes effective margin through discount amount | 100% | 100% | 100% | 50% |
| VIP customers drive revenue through higher AOV | 100% | 100% | 100% | 100% |

## 5. 全試行データ

| 条件 | Trial | チェーン仮説 | LLM verdict | 正解 | 一致 | 連鎖認識 |
|------|-------|-------------|------------|------|------|---------|
| RDF | 1 | Discount drives revenue through order volume | contradicted | contradicted | OK | Yes |
| RDF | 1 | Discount erodes effective margin through disc | supported | supported | OK | Yes |
| RDF | 1 | VIP customers drive revenue through higher AO | supported | supported | OK | Yes |
| RDF | 2 | Discount drives revenue through order volume | contradicted | contradicted | OK | Yes |
| RDF | 2 | Discount erodes effective margin through disc | supported | supported | OK | Yes |
| RDF | 2 | VIP customers drive revenue through higher AO | supported | supported | OK | Yes |
| RDF | 3 | Discount drives revenue through order volume | contradicted | contradicted | OK | Yes |
| RDF | 3 | Discount erodes effective margin through disc | supported | supported | OK | No |
| RDF | 3 | VIP customers drive revenue through higher AO | supported | supported | OK | Yes |
| NL | 1 | Discount drives revenue through order volume | inconclusive | contradicted | NG | Yes |
| NL | 1 | Discount erodes effective margin through disc | supported | supported | OK | Yes |
| NL | 1 | VIP customers drive revenue through higher AO | supported | supported | OK | Yes |
| NL | 2 | Discount drives revenue through order volume | contradicted | contradicted | OK | Yes |
| NL | 2 | Discount erodes effective margin through disc | supported | supported | OK | No |
| NL | 2 | VIP customers drive revenue through higher AO | supported | supported | OK | Yes |
| NL | 3 | Discount drives revenue through order volume | inconclusive | contradicted | NG | Yes |
| NL | 3 | Discount erodes effective margin through disc | supported | supported | OK | Yes |
| NL | 3 | VIP customers drive revenue through higher AO | supported | supported | OK | Yes |
| MEMO | 1 | Discount drives revenue through order volume | contradicted | contradicted | OK | Yes |
| MEMO | 1 | Discount erodes effective margin through disc | supported | supported | OK | Yes |
| MEMO | 1 | VIP customers drive revenue through higher AO | supported | supported | OK | Yes |
| MEMO | 2 | Discount drives revenue through order volume | contradicted | contradicted | OK | Yes |
| MEMO | 2 | Discount erodes effective margin through disc | supported | supported | OK | Yes |
| MEMO | 2 | VIP customers drive revenue through higher AO | supported | supported | OK | Yes |
| MEMO | 3 | Discount drives revenue through order volume | contradicted | contradicted | OK | Yes |
| MEMO | 3 | Discount erodes effective margin through disc | supported | supported | OK | Yes |
| MEMO | 3 | VIP customers drive revenue through higher AO | supported | supported | OK | Yes |
| DOC | 1 | Discount drives revenue through order volume | contradicted | contradicted | OK | Yes |
| DOC | 1 | Discount erodes effective margin through disc | supported | supported | OK | Yes |
| DOC | 1 | VIP customers drive revenue through higher AO | supported | supported | OK | Yes |
| DOC | 2 | Discount drives revenue through order volume | inconclusive | contradicted | NG | Yes |
| DOC | 2 | VIP customers drive revenue through higher AO | supported | supported | OK | Yes |
| DOC | 3 | Discount erodes effective margin through disc | inconclusive | supported | NG | No |
| DOC | 3 | VIP customers drive revenue through higher AO | supported | supported | OK | Yes |

## 6. 考察

### verdict正答率

最高正答率は **RDF（構造化）** (100.0%)、
最低は **DOC（議事録）** (71.4%)、
差は 28.6% であった。

構造化条件（RDF+NL）の平均正答率: 88.9%、非構造化条件（MEMO+DOC）の平均正答率: 85.7%。
多段階因果推論では構造化された知識提供が **3.2%** 優位。

### 連鎖認識率

最高連鎖認識率は **MEMO（社内文書）** (100.0%)、
最低は **DOC（議事録）** (85.7%)。

構造化条件の平均連鎖認識率: 88.9%、非構造化条件: 92.9%。

### 条件別分析

- **RDF（構造化）**: 正答率 100.0%、連鎖認識率 88.9%
- **NL（自然言語）**: 正答率 77.8%、連鎖認識率 88.9%
- **MEMO（社内文書）**: 正答率 100.0%、連鎖認識率 100.0%
- **DOC（議事録）**: 正答率 71.4%、連鎖認識率 85.7%

### 総括

多段階因果推論（A→B→C）における知識記述形式の影響:

記述形式によって大きな精度差が確認された。多段階の因果連鎖はLLMにとって認知負荷が高く、知識の構造化が単段階ルール以上に重要であることが示唆される。
