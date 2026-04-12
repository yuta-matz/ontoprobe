# Confirmatory Mini-Study v2 — Prior-Resistant Hypotheses

**Status:** PRE-REGISTERED — committed prior to any v2 data collection
**Date registered:** 2026-04-12
**Parent:** `reports/confirmatory_protocol.md`(v1, commit c76a2a8)
**Theory reference:** `reports/theory_v2.md`

## 1. 動機 — v1 の制約を解消する

v1(H1–H4, 40 trials)は **p=0.00148, 効果量 0.45** で核心主張を支持した。しかし theory_v2 の T1/T2/T3 分解で見ると、以下の制約が残る:

1. **LLM prior 汚染**: H1-H4 はすべて e-commerce の教科書的仮説(Q4 > 他四半期, VIP AOV > 新規, etc.)。LLM prior で方向性が当たるため、"organizational private information" の論点が実証できない
2. **Within-data baseline の遍在**: 全ての仮説が A vs B 型で、B が query result 内にあるため、L0 でも within-data 比率が計算できてしまう(boundary condition 1)
3. **期待値を作者が自由に書いた**: 合成データの実 magnitude と無関係に expected を設定。乖離が人為的に極端

v2 は以下で (2) を解決する:

- **LLM prior が弱い or 逆方向の仮説を4つ導入**
- **1 つは within-data baseline を持たない target-based 仮説**(H6, pure T2 test)
- **expected magnitude は「架空の経営計画 / 組織想定」として設定**し、protocol でその source を明示

## 2. 主仮説(事前登録)

**H_main_v2**: Opus 4.6 において、L3 条件下の Q_quant スコアは L0 より**統計的に有意に高い**(v1 と同一の仮説、prior-resistant 仮説で再検定)。

- 検定: 片側 Wilcoxon signed-rank(paired by hypothesis)
- 有意水準: α = 0.05
- 効果量基準: L3平均 - L0平均 ≥ 0.4
- 両方を満たした場合のみ "核心主張は prior-resistant regime でも支持" と結論

**H_sub_v2(新設)**: H6(target-based, no within-data baseline)では L3 - L0 差が他の H5/H7/H8 より大きい。

- 根拠: H6 のみが within-data に比較対象を持たないため、L0 は T1 で完結できない
- 検定: H6 の L3-L0 差 vs H5/H7/H8 の平均 L3-L0 差(記述統計、正式な検定は事前登録せず)

**H_sub_prior(新設)**: H7, H8(LLM prior が強い誤方向)では L0 LLM が prior に引きずられて方向判定を誤る frequency が H1-H4 より高い。

- 根拠: H1-H4 は方向が prior と一致していた
- 観測対象: L0 trial の verdict(supported/contradicted)が ground truth と一致する割合
- 形式検定なし、記述的に報告

## 3. 副仮説(null prediction, 継続)

**H_null**: Q_aware は L0/L3 で有意差なし(ceiling 確認)

- v1 で支持済み、v2 で再確認

## 4. 設計

| 項目 | 値 |
|---|---|
| 対象仮説 | H5, H6, H7, H8(新設) |
| 条件 | L0 vs L3 |
| trial 数 | n=5 per cell = **40 trials** |
| LLM | Claude Opus 4.6 |
| 採点 | 二値化 Q_quant / Q_aware、独立 2 scorer 盲検 |
| インフラ | `src/ontoprobe/evaluation/confirmatory.py`(v1 と共用) |
| 主ドライバ | `scripts/run_confirmatory.py`, `scripts/run_blind_scoring.py` |

## 5. H5-H8 仕様(事前登録)

### H5 — Contrarian direction: campaign AOV 低下

- **Claim**: "Average order value on discount campaign days is lower than on non-campaign days."
- **Query**: `SELECT has_campaign, AVG(total_amount) AS aov FROM fct_orders GROUP BY has_campaign`
- **Observed**: campaign 9,693 / non-campaign 12,617 → **-23.2%**
- **Expected magnitude (L3 ontology)**: "campaign days see 10-25% lower AOV than non-campaign days (bargain-hunter effect)"
- **Expected source**: 架空の「社内マーケ分析チームの事前想定」
- **Ground truth**: **supported**, observed は expected 範囲の上端に位置
- **LLM prior 評価**: 弱〜中(discount ↓ AOV は部分的に一般知識、強い逆 prior ではない)

### H6 — Target-based, no within-data baseline: Q4 Tokyo revenue

- **Claim**: "The Q4 revenue from the Tokyo region meets the company's internal revenue target for that region."
- **Query**: `SELECT region, order_quarter, SUM(total_amount) AS rev FROM fct_orders WHERE region='tokyo' AND order_quarter=4 GROUP BY region, order_quarter`
- **Observed**: 2,698,389(2.70M)
- **Expected magnitude (L3 ontology)**: "Q4 Tokyo regional revenue target: 3.0-4.0M JPY(2025年度中期経営計画)"
- **Expected source**: **架空の経営計画**(organizational private の代理)
- **Ground truth**: **contradicted**, observed 2.70M は target 範囲 3.0-4.0M を下回る(undershoot -10 to -33%)
- **LLM prior**: 無(LLM は当社の target 数値を絶対に知らない)
- **Critical design property**: **within-data に比較対象が存在しない** — L0 は単一観測値 2.70M を報告するしかない。これが pure T2 test

### H7 — Contrarian: VIP per-customer order frequency

- **Claim**: "VIP customers place more orders per customer than new customers."
- **Query**: 
```sql
SELECT customer_segment,
       COUNT(*) AS total_orders,
       COUNT(DISTINCT customer_id) AS unique_customers,
       1.0*COUNT(*)/COUNT(DISTINCT customer_id) AS orders_per_customer
FROM fct_orders WHERE customer_segment IN ('vip','new')
GROUP BY customer_segment
```
- **Observed**: VIP 11.33 / new 11.46 → VIP は **1.1% 低い**
- **Expected magnitude (L3 ontology)**: "VIP customers are expected to place 30-50% more orders per customer than new customers (loyalty effect)"
- **Expected source**: 架空の「CRM チームの想定」(LLM prior と同方向だが組織固有の magnitude)
- **Ground truth**: **contradicted**, direction が prior と逆
- **LLM prior 評価**: 強(VIP = high activity = more orders という強い generic prior)
- **Testing target**: L0 LLM は prior に引きずられて "supported" と誤判定する?データを正しく読めるか?

### H8 — Contrarian within Q4: Dec vs Oct revenue

- **Claim**: "December revenue exceeds October revenue within the Q4 period."
- **Query**: `SELECT order_month, SUM(total_amount) AS rev FROM fct_orders WHERE order_quarter=4 GROUP BY order_month`
- **Observed**: Oct 4.09M, Nov 3.47M, Dec 3.46M → Dec is **-15.5% vs Oct**
- **Expected magnitude (L3 ontology)**: "December revenue is expected to be 10-20% higher than October (year-end holiday shopping effect)"
- **Expected source**: 架空の「EC 部門の季節計画」(LLM prior と同方向)
- **Ground truth**: **contradicted**, direction が prior と逆
- **LLM prior 評価**: 非常に強(12月が最大という holiday prior)

## 6. 採点・分析計画

v1 と同一:

- Q_quant / Q_aware の二値採点
- 独立 2 scorer(scorer_a, scorer_b)盲検
- Wilcoxon signed-rank(片側, L3>L0 on Q_quant)
- Cohen's κ
- Bootstrap 95% CI

追加分析(v2 特有、事前登録):

1. **Per-hypothesis L0 Q_quant** を v1 H1-H4 と並べて表示。prior-resistance の regime map を作成
2. **H6 vs 他 3 仮説** の L3-L0 差を比較(記述統計)
3. **L0 の方向判定エラー率**(verdict が ground truth と一致しない割合)を H5-H8 と H1-H4 で比較

## 7. 成功条件(事前固定)

| 結果 | 解釈 |
|---|---|
| H_main_v2 有意かつ効果量 ≥ 0.4 | theory_v2 を **prior-resistant regime でも支持** |
| H_main_v2 有意だが効果量 < 0.4 | 「prior resistant でも差はあるが効果は弱い」と記録、theory_v2 を下方修正 |
| H_main_v2 非有意 | **theory_v2 失敗**、v1 の結果は prior-friendly な仮説に限定されると結論。発表で正直に開示 |
| H_sub_v2 が成立(H6 で差最大) | pure T2 test で期待値の critical 性を個別に確認 |
| H_sub_prior が成立(L0 が prior で誤判定) | "LLM は自発的に T2 に入らない" 主張の直接証拠 |

## 8. 事前固定した除外ルール

- API エラー / JSON parse 失敗は 1 回再実行、それ以降は除外
- それ以外の理由での再実行・除外は禁止
- 除外数を結果セクションに記録

## 9. 結果(データ収集後に追記)

*このセクションは実験完了後にのみ追記される。プロトコル本体(Section 1-8)はその時点で改変しない。*
