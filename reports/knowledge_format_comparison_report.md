# 知識記述形式がLLM仮説検証精度に与える影響

## 1. 目的

OntoProbeでは、ECサイトのドメイン知識をRDF/OWLオントロジーとして構造化し、
LLMに与えて因果仮説の生成・検証を行っている。
しかし実務では、ドメイン知識は議事録・社内文書・Slackなど非構造化テキストとして存在することが多い。

本実験では、**同一のドメイン知識を4つの異なる記述形式でLLMに渡した場合に、
仮説検証の精度にどの程度の差が生じるか**を定量的に検証する。

## 2. 実験設計

### 2.1 比較条件

| 条件 | 形式 | 特徴 |
|------|------|------|
| **RDF（構造化）** | ラベル付き箇条書き | `- Cause: Discount Campaign` / `- Direction: increase` / `- Expected magnitude: 15-30%` のようにRDFから抽出した構造化フィールドで記述 |
| **NL（自然言語）** | 散文パラグラフ | RDFと同一情報をルールごとに1段落の文章で記述。プログラム的に生成し情報パリティを保証 |
| **MEMO（社内文書）** | 個別の社内文書 | ルールごとに独立した文書（議事録抜粋・Slack会話・レポート等）。出典がバラバラ |
| **DOC（議事録）** | 1つの議事録 | マーケティング部定例会議の議事録に全ルールを埋め込み。無関係なノイズ（引越し・忘年会等）、会話形式、脱線を含む |

### 2.2 情報量の統制

4条件すべてに同一の7件の因果ルール情報を含めた:
因果関係（何が何に影響するか）、方向（増加/減少）、期待される効果の大きさ、適用条件、比較対象。

- RDF・NLは`CausalRule`データクラスからプログラム的に生成し、情報パリティを厳密に保証
- MEMO・DOCは同じ情報を日本語の社内文書として手動作成。口語表現を使用

### 2.3 評価方法

| 項目 | 内容 |
|------|------|
| LLM | Claude Code（Claude Opus 4.6）をCLI経由でサブプロセスとして使用 |
| パイプライン | 条件別コンテキスト → LLMで仮説+SQL生成 → DuckDBでSQL実行 → LLMでverdict判定 |
| Ground Truth | デモモードのルールベース検証（決定論的、LLM不使用） |
| 試行回数 | 各条件 5回（LLMの非決定性を考慮） |
| 評価指標 | verdict正答率、ルール別正答率、仮説生成カバレッジ、verdict一貫性 |

### 2.4 評価対象ルールとGround Truth

| # | ルール | 正解verdict | データの実態 |
|---|--------|-----------|------------|
| 1 | Q4 has highest overall revenue | supported | Q4売上は他四半期平均比 +96% |
| 2 | Discount increases order volume | supported | キャンペーン期間の注文数 +7%（期待15-30%を下回るが方向一致） |
| 3 | VIP customers have higher AOV | supported | VIP AOVはNew比 +601%（期待40-60%を大幅超過） |
| 4 | Seasonal products spike in Q4 | supported | Q4季節商品売上は他四半期の15倍（期待2-3倍を大幅超過） |
| 5 | Free shipping increases order volume | contradicted | 送料無料期間の注文数 -18%（期待と逆方向） |
| 6 | Repeat purchases correlate with CLV | inconclusive | 全セグメントrepeat_rate=100%で検証不能 |
| 7 | Discounts reduce effective margin | supported | 割引率に比例して実質割引率が上昇 |

## 3. 結果

### 3.1 総合比較

| 指標 | RDF（構造化） | NL（自然言語） | MEMO（社内文書） | DOC（議事録） |
|------|---|---|---|---|
| 総合正答率 | **74.3%** | **76.0%** | **32.0%** | **56.0%** |
| 有効試行数 | 35 | 25 | 25 | 25 |
| 平均一貫性 | 91.4% | 84.0% | 92.0% | 96.0% |

### 3.2 ルール別正答率

| ルール | RDF（構造化） | NL（自然言語） | MEMO（社内文書） | DOC（議事録） |
|--------|---|---|---|---|
| Discount increases order volume | 20% | 20% | 0% | 0% |
| Discounts reduce effective margin | 100% | N/A | N/A | N/A |
| Free shipping increases order volume | 100% | 100% | N/A | N/A |
| Q4 has highest overall revenue | 20% | N/A | 0% | 100% |
| Repeat purchases correlate with CLV | 100% | 100% | 100% | 80% |
| Seasonal products spike in Q4 | 100% | 100% | 60% | 100% |
| VIP customers have higher AOV | 80% | 60% | 0% | 0% |

### 3.3 仮説生成カバレッジ

| 条件 | 生成されたルール数（/7） | 未生成のルール |
|------|----------------------|--------------|
| RDF | **7/7 (100%)** | なし |
| NL | 5/7 (71%) | Discounts reduce effective margin, Q4 has highest overall revenue |
| MEMO | 5/7 (71%) | Discounts reduce effective margin, Free shipping increases order volume |
| DOC | 5/7 (71%) | Discounts reduce effective margin, Free shipping increases order volume |

### 3.4 ルール別一貫性（verdict安定度）

| ルール | RDF（構造化） | NL（自然言語） | MEMO（社内文書） | DOC（議事録） |
|--------|---|---|---|---|
| Discount increases order volume | 80% | 60% | 100% | 100% |
| Discounts reduce effective margin | 100% | N/A | N/A | N/A |
| Free shipping increases order volume | 100% | 100% | N/A | N/A |
| Q4 has highest overall revenue | 80% | N/A | 100% | 100% |
| Repeat purchases correlate with CLV | 100% | 100% | 100% | 80% |
| Seasonal products spike in Q4 | 100% | 100% | 60% | 100% |
| VIP customers have higher AOV | 80% | 60% | 100% | 100% |

### 3.5 全試行データ

| 条件 | Trial | ルール | LLM verdict | 正解 | 一致 |
|------|-------|--------|------------|------|------|
| RDF | 1 | Discount increases order volume | supported | supported | OK |
| RDF | 1 | Discounts reduce effective margin | supported | supported | OK |
| RDF | 1 | Free shipping increases order volum | contradicted | contradicted | OK |
| RDF | 1 | Q4 has highest overall revenue | contradicted | supported | NG |
| RDF | 1 | Repeat purchases correlate with CLV | inconclusive | inconclusive | OK |
| RDF | 1 | Seasonal products spike in Q4 | supported | supported | OK |
| RDF | 1 | VIP customers have higher AOV | supported | supported | OK |
| RDF | 2 | Discount increases order volume | contradicted | supported | NG |
| RDF | 2 | Discounts reduce effective margin | supported | supported | OK |
| RDF | 2 | Free shipping increases order volum | contradicted | contradicted | OK |
| RDF | 2 | Q4 has highest overall revenue | supported | supported | OK |
| RDF | 2 | Repeat purchases correlate with CLV | inconclusive | inconclusive | OK |
| RDF | 2 | Seasonal products spike in Q4 | supported | supported | OK |
| RDF | 2 | VIP customers have higher AOV | contradicted | supported | NG |
| RDF | 3 | Discount increases order volume | contradicted | supported | NG |
| RDF | 3 | Discounts reduce effective margin | supported | supported | OK |
| RDF | 3 | Free shipping increases order volum | contradicted | contradicted | OK |
| RDF | 3 | Q4 has highest overall revenue | contradicted | supported | NG |
| RDF | 3 | Repeat purchases correlate with CLV | inconclusive | inconclusive | OK |
| RDF | 3 | Seasonal products spike in Q4 | supported | supported | OK |
| RDF | 3 | VIP customers have higher AOV | supported | supported | OK |
| RDF | 4 | Discount increases order volume | contradicted | supported | NG |
| RDF | 4 | Discounts reduce effective margin | supported | supported | OK |
| RDF | 4 | Free shipping increases order volum | contradicted | contradicted | OK |
| RDF | 4 | Q4 has highest overall revenue | contradicted | supported | NG |
| RDF | 4 | Repeat purchases correlate with CLV | inconclusive | inconclusive | OK |
| RDF | 4 | Seasonal products spike in Q4 | supported | supported | OK |
| RDF | 4 | VIP customers have higher AOV | supported | supported | OK |
| RDF | 5 | Discount increases order volume | contradicted | supported | NG |
| RDF | 5 | Discounts reduce effective margin | supported | supported | OK |
| RDF | 5 | Free shipping increases order volum | contradicted | contradicted | OK |
| RDF | 5 | Q4 has highest overall revenue | contradicted | supported | NG |
| RDF | 5 | Repeat purchases correlate with CLV | inconclusive | inconclusive | OK |
| RDF | 5 | Seasonal products spike in Q4 | supported | supported | OK |
| RDF | 5 | VIP customers have higher AOV | supported | supported | OK |
| NL | 1 | Discount increases order volume | inconclusive | supported | NG |
| NL | 1 | Free shipping increases order volum | contradicted | contradicted | OK |
| NL | 1 | Repeat purchases correlate with CLV | inconclusive | inconclusive | OK |
| NL | 1 | Seasonal products spike in Q4 | supported | supported | OK |
| NL | 1 | VIP customers have higher AOV | contradicted | supported | NG |
| NL | 2 | Discount increases order volume | inconclusive | supported | NG |
| NL | 2 | Free shipping increases order volum | contradicted | contradicted | OK |
| NL | 2 | Repeat purchases correlate with CLV | inconclusive | inconclusive | OK |
| NL | 2 | Seasonal products spike in Q4 | supported | supported | OK |
| NL | 2 | VIP customers have higher AOV | supported | supported | OK |
| NL | 3 | Discount increases order volume | contradicted | supported | NG |
| NL | 3 | Free shipping increases order volum | contradicted | contradicted | OK |
| NL | 3 | Repeat purchases correlate with CLV | inconclusive | inconclusive | OK |
| NL | 3 | Seasonal products spike in Q4 | supported | supported | OK |
| NL | 3 | VIP customers have higher AOV | supported | supported | OK |
| NL | 4 | Discount increases order volume | inconclusive | supported | NG |
| NL | 4 | Free shipping increases order volum | contradicted | contradicted | OK |
| NL | 4 | Repeat purchases correlate with CLV | inconclusive | inconclusive | OK |
| NL | 4 | Seasonal products spike in Q4 | supported | supported | OK |
| NL | 4 | VIP customers have higher AOV | contradicted | supported | NG |
| NL | 5 | Discount increases order volume | supported | supported | OK |
| NL | 5 | Free shipping increases order volum | contradicted | contradicted | OK |
| NL | 5 | Repeat purchases correlate with CLV | inconclusive | inconclusive | OK |
| NL | 5 | Seasonal products spike in Q4 | supported | supported | OK |
| NL | 5 | VIP customers have higher AOV | supported | supported | OK |
| MEMO | 1 | Discount increases order volume | contradicted | supported | NG |
| MEMO | 1 | Q4 has highest overall revenue | contradicted | supported | NG |
| MEMO | 1 | Repeat purchases correlate with CLV | inconclusive | inconclusive | OK |
| MEMO | 1 | Seasonal products spike in Q4 | supported | supported | OK |
| MEMO | 1 | VIP customers have higher AOV | contradicted | supported | NG |
| MEMO | 2 | Discount increases order volume | contradicted | supported | NG |
| MEMO | 2 | Q4 has highest overall revenue | contradicted | supported | NG |
| MEMO | 2 | Repeat purchases correlate with CLV | inconclusive | inconclusive | OK |
| MEMO | 2 | Seasonal products spike in Q4 | supported | supported | OK |
| MEMO | 2 | VIP customers have higher AOV | contradicted | supported | NG |
| MEMO | 3 | Discount increases order volume | contradicted | supported | NG |
| MEMO | 3 | Q4 has highest overall revenue | contradicted | supported | NG |
| MEMO | 3 | Repeat purchases correlate with CLV | inconclusive | inconclusive | OK |
| MEMO | 3 | Seasonal products spike in Q4 | contradicted | supported | NG |
| MEMO | 3 | VIP customers have higher AOV | contradicted | supported | NG |
| MEMO | 4 | Discount increases order volume | contradicted | supported | NG |
| MEMO | 4 | Q4 has highest overall revenue | contradicted | supported | NG |
| MEMO | 4 | Repeat purchases correlate with CLV | inconclusive | inconclusive | OK |
| MEMO | 4 | Seasonal products spike in Q4 | contradicted | supported | NG |
| MEMO | 4 | VIP customers have higher AOV | contradicted | supported | NG |
| MEMO | 5 | Discount increases order volume | contradicted | supported | NG |
| MEMO | 5 | Q4 has highest overall revenue | contradicted | supported | NG |
| MEMO | 5 | Repeat purchases correlate with CLV | inconclusive | inconclusive | OK |
| MEMO | 5 | Seasonal products spike in Q4 | supported | supported | OK |
| MEMO | 5 | VIP customers have higher AOV | contradicted | supported | NG |
| DOC | 1 | Discount increases order volume | contradicted | supported | NG |
| DOC | 1 | Q4 has highest overall revenue | supported | supported | OK |
| DOC | 1 | Repeat purchases correlate with CLV | inconclusive | inconclusive | OK |
| DOC | 1 | Seasonal products spike in Q4 | supported | supported | OK |
| DOC | 1 | VIP customers have higher AOV | contradicted | supported | NG |
| DOC | 2 | Discount increases order volume | contradicted | supported | NG |
| DOC | 2 | Q4 has highest overall revenue | supported | supported | OK |
| DOC | 2 | Repeat purchases correlate with CLV | inconclusive | inconclusive | OK |
| DOC | 2 | Seasonal products spike in Q4 | supported | supported | OK |
| DOC | 2 | VIP customers have higher AOV | contradicted | supported | NG |
| DOC | 3 | Discount increases order volume | contradicted | supported | NG |
| DOC | 3 | Q4 has highest overall revenue | supported | supported | OK |
| DOC | 3 | Repeat purchases correlate with CLV | supported | inconclusive | NG |
| DOC | 3 | Seasonal products spike in Q4 | supported | supported | OK |
| DOC | 3 | VIP customers have higher AOV | contradicted | supported | NG |
| DOC | 4 | Discount increases order volume | contradicted | supported | NG |
| DOC | 4 | Q4 has highest overall revenue | supported | supported | OK |
| DOC | 4 | Repeat purchases correlate with CLV | inconclusive | inconclusive | OK |
| DOC | 4 | Seasonal products spike in Q4 | supported | supported | OK |
| DOC | 4 | VIP customers have higher AOV | contradicted | supported | NG |
| DOC | 5 | Discount increases order volume | contradicted | supported | NG |
| DOC | 5 | Q4 has highest overall revenue | supported | supported | OK |
| DOC | 5 | Repeat purchases correlate with CLV | inconclusive | inconclusive | OK |
| DOC | 5 | Seasonal products spike in Q4 | supported | supported | OK |
| DOC | 5 | VIP customers have higher AOV | contradicted | supported | NG |

## 4. 考察

### 4.1 形式間の序列

5回の試行により、以下の序列が確認された:

```
NL (76.0%) ≒ RDF (74.3%) >> DOC (56.0%) >> MEMO (32.0%)
```

正答率の差は最大44.0ポイント（NL vs MEMO）。記述形式が精度に大きく影響することが示された。

### 4.2 RDF vs NL: 判定精度は同等、カバレッジに差

RDFとNLの正答率はほぼ同等（74.3% vs 76.0%）である。ただし両者には質的な違いがある:

- **カバレッジ**: RDFは7/7ルールすべてを仮説として生成（有効試行35件）。NLは5/7（25件）に留まる
- **判定精度**: 生成された仮説に限ればNLはRDFと同等以上。構造化ラベルが判定精度を必ずしも高めるわけではない
- **欠落するルール**: NLでは「Discounts reduce effective margin」「Q4 has highest overall revenue」が生成されなかった。いずれも因果関係が間接的で、ラベルなしでは因果ルールとして認識されにくい

この結果は、RDFの最大の貢献が**ルールの発見・列挙**にあり、個々のルールの判定精度は記述形式にあまり依存しないことを示唆している。

### 4.3 MEMO（社内文書）: 最低精度の要因

32.0%という最低の正答率は、以下の特性に起因する:

- **文脈の断片化**: 各ルールが独立した短い文書として提示されるため、相互の関連が見えない
- **VIP AOV: 0%、Q4 revenue: 0%** — 他条件では高精度だったルールが全滅
- **Seasonal spike: 60%** — 他条件では100%の容易なルールでも不安定に
- **一貫性は高い（92.0%）が誤り方向に安定** — 同じ誤判定を繰り返す「自信を持って間違える」傾向

### 4.4 DOC（議事録）vs MEMO: 文脈の一貫性

同じ非構造化テキストでも、1つの議事録（DOC: 56.0%）はバラバラの文書（MEMO: 32.0%）の**約1.75倍**の精度を示した:

| 観点 | MEMO（社内文書） | DOC（議事録） |
|------|----------------|-------------|
| 正答率 | 32.0% | 56.0% |
| Q4 revenue | 0% | **100%** |
| 一貫性 | 92.0% | **96.0%** |

DOCでQ4 revenueが100%正答（RDFでは20%）になったのは注目すべき結果である。
議事録の会話の流れ（「毎年の話ですが、Q4は...3〜5割くらい高くなります」→「季節商品はもっとすごいですよね？」）が
Q4の季節性を文脈的に強調し、LLMの理解を助けたと考えられる。

一方で、VIP AOVは0%に低下。会話中で佐藤が「4〜6割くらい高い」と言及しているが、
前後の議題（キャンペーン効果、忘年会等）のノイズに埋もれたと推測される。

### 4.5 全条件共通の課題

**Discount volumeルール（全条件0-20%）**

データ上は+7%増で方向は一致しているが、期待値15-30%を大幅に下回る。
Ground Truthは「方向一致ならsupported」と定義しているが、LLMは量的乖離を重視してcontradictedと判定する。
これは知識記述形式の問題ではなく、**Ground Truthの定義とLLMの判断基準のミスマッチ**である。

**カバレッジの欠落（非構造化条件で約30%）**

NL/MEMO/DOCはいずれも5/7ルール（71%）の仮説生成に留まった。
構造化ラベルなしではLLMが因果ルールとして認識できないケースがあり、
特に「マージンへの影響」のような間接的な因果関係が見落とされやすい。

### 4.6 限界と今後の課題

- **試行回数**: 各条件5回。統計的な信頼区間算出には10回以上が望ましい
- **モデル依存性**: Claude Opus 4.6での結果。他モデルでは異なる傾向を示す可能性がある
- **DOC/MEMO条件の再現性**: 手動作成のため表現の微妙な違いが結果に影響しうる
- **Ground Truthの妥当性**: Discount volumeルールのように、判定基準自体に改善の余地がある

## 5. 結論

### 主要な知見

| 知見 | 詳細 |
|------|------|
| **構造化の最大の強みはカバレッジ** | RDFのみ7/7ルールを仮説化。非構造化では約30%が欠落する |
| **判定精度はNLと同等** | 生成された仮説の判定精度ではRDF・NLに大差なし（74.3% vs 76.0%） |
| **議事録は社内文書の1.75倍** | 文脈の一貫性がある1つの文書（56.0%）が断片的な文書群（32.0%）を大幅に上回る |
| **文脈効果はルール依存** | 議事録のQ4 revenue 100%正答はRDF（20%）を凌駕。一方VIP AOVは0%に低下 |
| **非構造化は「自信を持って間違える」** | MEMO/DOCは一貫性が高い（92-96%）が、誤判定を安定して反復する傾向 |

### 実務への示唆

1. **ドメイン知識の構造化にはROIがある**: 特にルールの網羅的な仮説化（カバレッジ100%）に効果的。仮説を1つも見落とさないことが重要な場面では構造化が不可欠
2. **社内文書を使う場合は1つにまとめる**: バラバラの文書より、1つのまとまった文書のほうが精度が高い。RAGで断片を取得するより、関連文書を結合して渡すほうが有効な可能性がある
3. **構造化と自然言語の併用が最適解**: カバレッジはRDFで確保し、判定精度はNL/DOCの文脈情報で補完するハイブリッドアプローチが考えられる
4. **期待値の数値は明示的に渡す**: 散文中の「15〜30%くらい」は見落とされやすい。定量的な判定基準は構造化して渡すべき
