# 知識記述形式 x 因果チェーン段数の交差比較レポート

## 概要

知識記述形式（RDF/NL/MEMO/DOC）と因果チェーンの段数（1〜5段）の
両方を変化させた場合に、LLMの仮説検証精度がどう変動するかを検証した。

- **試行回数:** 各セル 3 回
- **組み合わせ:** 4 形式 x 5 段数 = 20 セル

### 1-hop Ground Truth (7件)

| 仮説 | 正解 |
|------|------|
| Q4 has highest overall revenue | supported |
| Discount increases order volume | supported |
| VIP customers have higher AOV | supported |
| Seasonal products spike in Q4 | supported |
| Free shipping increases order volume | contradicted |
| Repeat purchases correlate with CLV | inconclusive |
| Discounts reduce effective margin | supported |

### 2-hop Ground Truth (3件)

| 仮説 | 正解 |
|------|------|
| Discount drives revenue through order volume | contradicted |
| Discount erodes effective margin through discount amount | supported |
| VIP customers drive revenue through higher AOV | supported |

### 3-hop Ground Truth (3件)

| 仮説 | 正解 |
|------|------|
| Seasonal spike concentrates annual revenue in Q4 | supported |
| VIP revenue drives concentration risk | supported |
| Discount revenue impact limits profit growth | contradicted |

### 4-hop Ground Truth (3件)

| 仮説 | 正解 |
|------|------|
| Q4 concentration creates seasonal dependency risk | supported |
| VIP concentration creates segment dependency risk | supported |
| Negative profit growth indicates poor campaign efficiency | supported |

### 5-hop Ground Truth (3件)

| 仮説 | 正解 |
|------|------|
| Seasonal dependency creates strategic vulnerability | supported |
| Segment dependency demands VIP retention priority | supported |
| Poor campaign efficiency demands strategy revision | supported |

## 1. verdict正答率マトリクス

| 形式 | 1-hop | 2-hop | 3-hop | 4-hop | 5-hop | 平均 |
|------|---|---|---|---|---|------|
| **RDF** | 76.2% | 88.9% | 77.8% | 66.7% | 66.7% | **75.2%** |
| **NL** | 64.7% | 100.0% | 66.7% | 100.0% | 100.0% | **86.3%** |
| **MEMO** | 50.0% | 100.0% | 0.0% | 100.0% | 0.0% | **50.0%** |
| **DOC** | 72.7% | 77.8% | 100.0% | 87.5% | 83.3% | **84.3%** |
| **平均** | **65.9%** | **91.7%** | **61.1%** | **88.5%** | **62.5%** | 73.9% |

## 2. 仮説カバレッジマトリクス

| 形式 | 1-hop | 2-hop | 3-hop | 4-hop | 5-hop |
|------|---|---|---|---|---|
| **RDF** | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| **NL** | 85.7% | 100.0% | 100.0% | 100.0% | 100.0% |
| **MEMO** | 85.7% | 100.0% | 0.0% | 66.7% | 0.0% |
| **DOC** | 71.4% | 100.0% | 66.7% | 100.0% | 100.0% |

## 3. 一貫性マトリクス

| 形式 | 1-hop | 2-hop | 3-hop | 4-hop | 5-hop |
|------|---|---|---|---|---|
| **RDF** | 95.2% | 88.9% | 88.9% | 77.8% | 77.8% |
| **NL** | 88.9% | 100.0% | 100.0% | 100.0% | 100.0% |
| **MEMO** | 94.4% | 100.0% | 0.0% | 100.0% | 0.0% |
| **DOC** | 93.3% | 77.8% | 100.0% | 83.3% | 83.3% |

## 4. 有効試行数マトリクス

| 形式 | 1-hop | 2-hop | 3-hop | 4-hop | 5-hop |
|------|---|---|---|---|---|
| **RDF** | 21 | 9 | 9 | 9 | 9 |
| **NL** | 17 | 9 | 9 | 8 | 9 |
| **MEMO** | 16 | 9 | 0 | 6 | 0 |
| **DOC** | 11 | 9 | 5 | 8 | 6 |

## 5. 全試行データ

| 形式 | 段数 | Trial | 仮説 | LLM | 正解 | 一致 |
|------|------|-------|------|-----|------|------|
| RDF | 1-hop | 1 | Discount increases order volume | supported | supported | OK |
| RDF | 1-hop | 1 | Discounts reduce effective margin | supported | supported | OK |
| RDF | 1-hop | 1 | Free shipping increases order volum | contradicted | contradicted | OK |
| RDF | 1-hop | 1 | Q4 has highest overall revenue | supported | supported | OK |
| RDF | 1-hop | 1 | Repeat purchases correlate with CLV | supported | inconclusive | NG |
| RDF | 1-hop | 1 | Seasonal products spike in Q4 | supported | supported | OK |
| RDF | 1-hop | 1 | VIP customers have higher AOV | supported | supported | OK |
| RDF | 1-hop | 2 | Discount increases order volume | contradicted | supported | NG |
| RDF | 1-hop | 2 | Discounts reduce effective margin | supported | supported | OK |
| RDF | 1-hop | 2 | Free shipping increases order volum | contradicted | contradicted | OK |
| RDF | 1-hop | 2 | Q4 has highest overall revenue | supported | supported | OK |
| RDF | 1-hop | 2 | Repeat purchases correlate with CLV | supported | inconclusive | NG |
| RDF | 1-hop | 2 | Seasonal products spike in Q4 | supported | supported | OK |
| RDF | 1-hop | 2 | VIP customers have higher AOV | supported | supported | OK |
| RDF | 1-hop | 3 | Discount increases order volume | contradicted | supported | NG |
| RDF | 1-hop | 3 | Discounts reduce effective margin | supported | supported | OK |
| RDF | 1-hop | 3 | Free shipping increases order volum | contradicted | contradicted | OK |
| RDF | 1-hop | 3 | Q4 has highest overall revenue | supported | supported | OK |
| RDF | 1-hop | 3 | Repeat purchases correlate with CLV | supported | inconclusive | NG |
| RDF | 1-hop | 3 | Seasonal products spike in Q4 | supported | supported | OK |
| RDF | 1-hop | 3 | VIP customers have higher AOV | supported | supported | OK |
| RDF | 2-hop | 1 | Discount drives revenue through ord | supported | contradicted | NG |
| RDF | 2-hop | 1 | Discount erodes effective margin th | supported | supported | OK |
| RDF | 2-hop | 1 | VIP customers drive revenue through | supported | supported | OK |
| RDF | 2-hop | 2 | Discount drives revenue through ord | contradicted | contradicted | OK |
| RDF | 2-hop | 2 | Discount erodes effective margin th | supported | supported | OK |
| RDF | 2-hop | 2 | VIP customers drive revenue through | supported | supported | OK |
| RDF | 2-hop | 3 | Discount drives revenue through ord | contradicted | contradicted | OK |
| RDF | 2-hop | 3 | Discount erodes effective margin th | supported | supported | OK |
| RDF | 2-hop | 3 | VIP customers drive revenue through | supported | supported | OK |
| RDF | 3-hop | 1 | Discount revenue impact limits prof | contradicted | contradicted | OK |
| RDF | 3-hop | 1 | Seasonal spike concentrates annual  | supported | supported | OK |
| RDF | 3-hop | 1 | VIP revenue drives concentration ri | supported | supported | OK |
| RDF | 3-hop | 2 | Discount revenue impact limits prof | supported | contradicted | NG |
| RDF | 3-hop | 2 | Seasonal spike concentrates annual  | supported | supported | OK |
| RDF | 3-hop | 2 | VIP revenue drives concentration ri | supported | supported | OK |
| RDF | 3-hop | 3 | Discount revenue impact limits prof | supported | contradicted | NG |
| RDF | 3-hop | 3 | Seasonal spike concentrates annual  | supported | supported | OK |
| RDF | 3-hop | 3 | VIP revenue drives concentration ri | supported | supported | OK |
| RDF | 4-hop | 1 | Negative profit growth indicates po | contradicted | supported | NG |
| RDF | 4-hop | 1 | Q4 concentration creates seasonal d | supported | supported | OK |
| RDF | 4-hop | 1 | VIP concentration creates segment d | supported | supported | OK |
| RDF | 4-hop | 2 | Negative profit growth indicates po | supported | supported | OK |
| RDF | 4-hop | 2 | Q4 concentration creates seasonal d | supported | supported | OK |
| RDF | 4-hop | 2 | VIP concentration creates segment d | contradicted | supported | NG |
| RDF | 4-hop | 3 | Negative profit growth indicates po | supported | supported | OK |
| RDF | 4-hop | 3 | Q4 concentration creates seasonal d | supported | supported | OK |
| RDF | 4-hop | 3 | VIP concentration creates segment d | contradicted | supported | NG |
| RDF | 5-hop | 1 | Poor campaign efficiency demands st | contradicted | supported | NG |
| RDF | 5-hop | 1 | Seasonal dependency creates strateg | supported | supported | OK |
| RDF | 5-hop | 1 | Segment dependency demands VIP rete | supported | supported | OK |
| RDF | 5-hop | 2 | Poor campaign efficiency demands st | supported | supported | OK |
| RDF | 5-hop | 2 | Seasonal dependency creates strateg | supported | supported | OK |
| RDF | 5-hop | 2 | Segment dependency demands VIP rete | contradicted | supported | NG |
| RDF | 5-hop | 3 | Poor campaign efficiency demands st | supported | supported | OK |
| RDF | 5-hop | 3 | Seasonal dependency creates strateg | supported | supported | OK |
| RDF | 5-hop | 3 | Segment dependency demands VIP rete | contradicted | supported | NG |
| NL | 1-hop | 1 | Discount increases order volume | supported | supported | OK |
| NL | 1-hop | 1 | Discounts reduce effective margin | supported | supported | OK |
| NL | 1-hop | 1 | Free shipping increases order volum | contradicted | contradicted | OK |
| NL | 1-hop | 1 | Repeat purchases correlate with CLV | supported | inconclusive | NG |
| NL | 1-hop | 1 | VIP customers have higher AOV | supported | supported | OK |
| NL | 1-hop | 2 | Discount increases order volume | inconclusive | supported | NG |
| NL | 1-hop | 2 | Discounts reduce effective margin | supported | supported | OK |
| NL | 1-hop | 2 | Free shipping increases order volum | contradicted | contradicted | OK |
| NL | 1-hop | 2 | Repeat purchases correlate with CLV | supported | inconclusive | NG |
| NL | 1-hop | 2 | Seasonal products spike in Q4 | supported | supported | OK |
| NL | 1-hop | 2 | VIP customers have higher AOV | contradicted | supported | NG |
| NL | 1-hop | 3 | Discount increases order volume | inconclusive | supported | NG |
| NL | 1-hop | 3 | Discounts reduce effective margin | supported | supported | OK |
| NL | 1-hop | 3 | Free shipping increases order volum | contradicted | contradicted | OK |
| NL | 1-hop | 3 | Repeat purchases correlate with CLV | supported | inconclusive | NG |
| NL | 1-hop | 3 | Seasonal products spike in Q4 | supported | supported | OK |
| NL | 1-hop | 3 | VIP customers have higher AOV | supported | supported | OK |
| NL | 2-hop | 1 | Discount drives revenue through ord | contradicted | contradicted | OK |
| NL | 2-hop | 1 | Discount erodes effective margin th | supported | supported | OK |
| NL | 2-hop | 1 | VIP customers drive revenue through | supported | supported | OK |
| NL | 2-hop | 2 | Discount drives revenue through ord | contradicted | contradicted | OK |
| NL | 2-hop | 2 | Discount erodes effective margin th | supported | supported | OK |
| NL | 2-hop | 2 | VIP customers drive revenue through | supported | supported | OK |
| NL | 2-hop | 3 | Discount drives revenue through ord | contradicted | contradicted | OK |
| NL | 2-hop | 3 | Discount erodes effective margin th | supported | supported | OK |
| NL | 2-hop | 3 | VIP customers drive revenue through | supported | supported | OK |
| NL | 3-hop | 1 | Discount revenue impact limits prof | supported | contradicted | NG |
| NL | 3-hop | 1 | Seasonal spike concentrates annual  | supported | supported | OK |
| NL | 3-hop | 1 | VIP revenue drives concentration ri | supported | supported | OK |
| NL | 3-hop | 2 | Discount revenue impact limits prof | supported | contradicted | NG |
| NL | 3-hop | 2 | Seasonal spike concentrates annual  | supported | supported | OK |
| NL | 3-hop | 2 | VIP revenue drives concentration ri | supported | supported | OK |
| NL | 3-hop | 3 | Discount revenue impact limits prof | supported | contradicted | NG |
| NL | 3-hop | 3 | Seasonal spike concentrates annual  | supported | supported | OK |
| NL | 3-hop | 3 | VIP revenue drives concentration ri | supported | supported | OK |
| NL | 4-hop | 1 | Negative profit growth indicates po | supported | supported | OK |
| NL | 4-hop | 1 | Q4 concentration creates seasonal d | supported | supported | OK |
| NL | 4-hop | 2 | Negative profit growth indicates po | supported | supported | OK |
| NL | 4-hop | 2 | Q4 concentration creates seasonal d | supported | supported | OK |
| NL | 4-hop | 2 | VIP concentration creates segment d | supported | supported | OK |
| NL | 4-hop | 3 | Negative profit growth indicates po | supported | supported | OK |
| NL | 4-hop | 3 | Q4 concentration creates seasonal d | supported | supported | OK |
| NL | 4-hop | 3 | VIP concentration creates segment d | supported | supported | OK |
| NL | 5-hop | 1 | Poor campaign efficiency demands st | supported | supported | OK |
| NL | 5-hop | 1 | Seasonal dependency creates strateg | supported | supported | OK |
| NL | 5-hop | 1 | Segment dependency demands VIP rete | supported | supported | OK |
| NL | 5-hop | 2 | Poor campaign efficiency demands st | supported | supported | OK |
| NL | 5-hop | 2 | Seasonal dependency creates strateg | supported | supported | OK |
| NL | 5-hop | 2 | Segment dependency demands VIP rete | supported | supported | OK |
| NL | 5-hop | 3 | Poor campaign efficiency demands st | supported | supported | OK |
| NL | 5-hop | 3 | Seasonal dependency creates strateg | supported | supported | OK |
| NL | 5-hop | 3 | Segment dependency demands VIP rete | supported | supported | OK |
| MEMO | 1-hop | 1 | Discount increases order volume | contradicted | supported | NG |
| MEMO | 1-hop | 1 | Discounts reduce effective margin | supported | supported | OK |
| MEMO | 1-hop | 1 | Repeat purchases correlate with CLV | supported | inconclusive | NG |
| MEMO | 1-hop | 1 | Seasonal products spike in Q4 | supported | supported | OK |
| MEMO | 1-hop | 1 | VIP customers have higher AOV | contradicted | supported | NG |
| MEMO | 1-hop | 2 | Discount increases order volume | contradicted | supported | NG |
| MEMO | 1-hop | 2 | Discounts reduce effective margin | supported | supported | OK |
| MEMO | 1-hop | 2 | Free shipping increases order volum | inconclusive | contradicted | NG |
| MEMO | 1-hop | 2 | Repeat purchases correlate with CLV | supported | inconclusive | NG |
| MEMO | 1-hop | 2 | Seasonal products spike in Q4 | supported | supported | OK |
| MEMO | 1-hop | 2 | VIP customers have higher AOV | supported | supported | OK |
| MEMO | 1-hop | 3 | Discount increases order volume | contradicted | supported | NG |
| MEMO | 1-hop | 3 | Discounts reduce effective margin | supported | supported | OK |
| MEMO | 1-hop | 3 | Repeat purchases correlate with CLV | supported | inconclusive | NG |
| MEMO | 1-hop | 3 | Seasonal products spike in Q4 | supported | supported | OK |
| MEMO | 1-hop | 3 | VIP customers have higher AOV | supported | supported | OK |
| MEMO | 2-hop | 1 | Discount drives revenue through ord | contradicted | contradicted | OK |
| MEMO | 2-hop | 1 | Discount erodes effective margin th | supported | supported | OK |
| MEMO | 2-hop | 1 | VIP customers drive revenue through | supported | supported | OK |
| MEMO | 2-hop | 2 | Discount drives revenue through ord | contradicted | contradicted | OK |
| MEMO | 2-hop | 2 | Discount erodes effective margin th | supported | supported | OK |
| MEMO | 2-hop | 2 | VIP customers drive revenue through | supported | supported | OK |
| MEMO | 2-hop | 3 | Discount drives revenue through ord | contradicted | contradicted | OK |
| MEMO | 2-hop | 3 | Discount erodes effective margin th | supported | supported | OK |
| MEMO | 2-hop | 3 | VIP customers drive revenue through | supported | supported | OK |
| MEMO | 4-hop | 1 | Q4 concentration creates seasonal d | supported | supported | OK |
| MEMO | 4-hop | 1 | VIP concentration creates segment d | supported | supported | OK |
| MEMO | 4-hop | 2 | Q4 concentration creates seasonal d | supported | supported | OK |
| MEMO | 4-hop | 2 | VIP concentration creates segment d | supported | supported | OK |
| MEMO | 4-hop | 3 | Q4 concentration creates seasonal d | supported | supported | OK |
| MEMO | 4-hop | 3 | VIP concentration creates segment d | supported | supported | OK |
| DOC | 1-hop | 1 | Discounts reduce effective margin | supported | supported | OK |
| DOC | 1-hop | 1 | Repeat purchases correlate with CLV | supported | inconclusive | NG |
| DOC | 1-hop | 1 | VIP customers have higher AOV | supported | supported | OK |
| DOC | 1-hop | 2 | Discount increases order volume | inconclusive | supported | NG |
| DOC | 1-hop | 2 | Discounts reduce effective margin | supported | supported | OK |
| DOC | 1-hop | 2 | Repeat purchases correlate with CLV | supported | inconclusive | NG |
| DOC | 1-hop | 2 | Seasonal products spike in Q4 | supported | supported | OK |
| DOC | 1-hop | 2 | VIP customers have higher AOV | supported | supported | OK |
| DOC | 1-hop | 3 | Discounts reduce effective margin | supported | supported | OK |
| DOC | 1-hop | 3 | Repeat purchases correlate with CLV | inconclusive | inconclusive | OK |
| DOC | 1-hop | 3 | VIP customers have higher AOV | supported | supported | OK |
| DOC | 2-hop | 1 | Discount drives revenue through ord | contradicted | contradicted | OK |
| DOC | 2-hop | 1 | Discount erodes effective margin th | supported | supported | OK |
| DOC | 2-hop | 1 | VIP customers drive revenue through | contradicted | supported | NG |
| DOC | 2-hop | 2 | Discount drives revenue through ord | inconclusive | contradicted | NG |
| DOC | 2-hop | 2 | Discount erodes effective margin th | supported | supported | OK |
| DOC | 2-hop | 2 | VIP customers drive revenue through | supported | supported | OK |
| DOC | 2-hop | 3 | Discount drives revenue through ord | contradicted | contradicted | OK |
| DOC | 2-hop | 3 | Discount erodes effective margin th | supported | supported | OK |
| DOC | 2-hop | 3 | VIP customers drive revenue through | supported | supported | OK |
| DOC | 3-hop | 1 | Discount revenue impact limits prof | contradicted | contradicted | OK |
| DOC | 3-hop | 1 | VIP revenue drives concentration ri | supported | supported | OK |
| DOC | 3-hop | 2 | VIP revenue drives concentration ri | supported | supported | OK |
| DOC | 3-hop | 3 | Discount revenue impact limits prof | contradicted | contradicted | OK |
| DOC | 3-hop | 3 | VIP revenue drives concentration ri | supported | supported | OK |
| DOC | 4-hop | 1 | Negative profit growth indicates po | contradicted | supported | NG |
| DOC | 4-hop | 1 | Q4 concentration creates seasonal d | supported | supported | OK |
| DOC | 4-hop | 1 | VIP concentration creates segment d | supported | supported | OK |
| DOC | 4-hop | 2 | Q4 concentration creates seasonal d | supported | supported | OK |
| DOC | 4-hop | 2 | VIP concentration creates segment d | supported | supported | OK |
| DOC | 4-hop | 3 | Negative profit growth indicates po | supported | supported | OK |
| DOC | 4-hop | 3 | Q4 concentration creates seasonal d | supported | supported | OK |
| DOC | 4-hop | 3 | VIP concentration creates segment d | supported | supported | OK |
| DOC | 5-hop | 1 | Poor campaign efficiency demands st | contradicted | supported | NG |
| DOC | 5-hop | 1 | Seasonal dependency creates strateg | supported | supported | OK |
| DOC | 5-hop | 1 | Segment dependency demands VIP rete | supported | supported | OK |
| DOC | 5-hop | 3 | Poor campaign efficiency demands st | supported | supported | OK |
| DOC | 5-hop | 3 | Seasonal dependency creates strateg | supported | supported | OK |
| DOC | 5-hop | 3 | Segment dependency demands VIP rete | supported | supported | OK |

## 6. 考察

### 形式別平均正答率（段数の影響を平均化）

- **RDF**: ############################## 75.2%
- **NL**: ################################## 86.3%
- **MEMO**: #################### 50.0%
- **DOC**: ################################# 84.3%

### 段数別平均正答率（形式の影響を平均化）

- **1-hop**: ########################## 65.9%
- **2-hop**: #################################### 91.7%
- **3-hop**: ######################## 61.1%
- **4-hop**: ################################### 88.5%
- **5-hop**: ######################### 62.5%

### 交互作用

1-hop → 3-hop の精度変化（形式別）:

- **RDF**: -1.6% (改善)
- **NL**: -2.0% (改善)
- **MEMO**: +50.0% (劣化)
- **DOC**: -27.3% (改善)

形式によって段数の影響が異なる。**MEMO** が最も段数増加の影響を受けやすく、**DOC** が最も耐性がある。

### 総括

- 形式による精度差: 36.3%
- 段数による精度差: 30.6%

**知識記述形式が段数よりも大きな影響要因**である。多段階推論の精度向上には、チェーンの分解よりも知識の記述方式の最適化が優先されるべき。
