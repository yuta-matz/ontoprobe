# Confirmatory Mini-Study: Pre-registration Protocol

**Status:** PRE-REGISTERED — committed prior to any data collection
**Date registered:** 2026-04-12
**Author:** yuta-matz
**Parent study:** `reports/llm_experiment_poc.md`(exploratory, n=104)

> このプロトコルは confirmatory 実験の **データ収集開始前に** git にコミットされる。
> 以降、判定基準・採点ルール・成功条件のいかなる変更も「プロトコル違反」として明示記録する。

---

## 1. 背景と動機

Exploratory phase(n=104, Part A-E)で「**期待値プロパティ(hasExpectedMagnitude)無しには定量的乖離判定は原理的に不可能**」という核心主張を得た。ただし当該実験は以下の方法論的制約を持つ(`llm_experiment_poc.md` Section 14):

1. 単一採点者・非盲検(ground truth を知った状態で採点)
2. 事前登録なし(実験中に "異常検出" の定義を拡張)
3. 採点ルーブリックが探索中に変化
4. 0-2 の3段階は粗く、ceiling effect を起こしやすい

本 confirmatory study は **これら4点を方法論的に解消した上で**、核心主張の中心的予測を独立に再検証する。

## 2. 主仮説(事前登録)

**H_main**: Opus 4.6 において、L3(期待値含む)条件下の定量乖離検出スコアは L0(オントロジー無し)条件より**統計的に有意に高い**。

- 検定: 片側 Wilcoxon signed-rank(paired by hypothesis)
- 有意水準: α = 0.05
- 効果量基準: L3平均 - L0平均 ≥ 0.4(0-1スケール上)
- **両方を満たした場合のみ "核心主張を支持" と結論する**

## 3. 副仮説(事前登録)

**H_null**: 「現状把握(situation awareness)」スコアは L0/L3 で有意差なし(両条件とも高い天井に達する)。

- 検定: 両側 Wilcoxon signed-rank
- これは **null prediction**。差が出てしまったら ceiling assumption が崩れているため H_main の解釈を慎重化する。

## 4. 設計

| 項目 | 値 |
|---|---|
| 対象仮説 | H1, H2, H3, H4(`hypotheses/demo.py` の最初の4つ) |
| 条件 | L0(オントロジーなし)/ L3(期待値含む) |
| trial 数 | n=5 per (hypothesis × level) cell |
| 総実験数 | 4 × 2 × 5 = **40** |
| LLM | Claude Opus 4.6(`model: opus`、Part A と一致) |
| 実行手段 | Claude Code サブエージェント、独立コンテキスト |
| temperature | 既定値(再現性より独立性を優先) |

### 4.1 重要な設計決定: 仮説文から magnitude を剥がす

L0 と L3 の contrast を意味のあるものにするため、**runner に渡す仮説 claim は方向性のみ**(例: "Q4 revenue is higher than Q1-Q3 average")。"30-50%" 等の expected magnitude は claim に含めない。

- L0 条件: 方向性 claim + query result のみ
- L3 条件: 方向性 claim + query result + **オントロジーに記載された expected magnitude**

この措置を取らないと L0 でも LLM は「claim に書かれた 30-50% と実測 96% を比較」で trivially Q_quant を取ってしまい、L0 vs L3 差が消失する。

この決定は Part A の exploratory setup と整合的(Part A のスコア差は L0 9/10 vs L3 10/10 であり、L0 はベースライン捏造で 1 点失点していた — magnitude が claim に無かった状況を再現している)。

### 4.2 H1-H4 選定理由

| ID | 内容 | 選定理由 |
|---|---|---|
| H1 | Q4 売上 +96%(想定 30-50%) | 1-hop, 標準的定量乖離 |
| H2 | 割引→注文 +7%(想定 15-30%) | **負方向の乖離**(想定未満)を含む唯一の例 |
| H3 | VIP AOV +601%(想定 40-60%) | 巨大乖離(>10x)、検出失敗時の影響大 |
| H4 | 季節 Q4 15x(想定 2-3x) | 比率系・magnitude が比率で表現 |

代表性: 方向(±)・スケール(7%〜15x)・指標タイプ(売上/注文/AOV/季節性)を分散。

## 5. 採点ルーブリック(二値化、事前固定)

旧 0-2 の3段階を廃止。各 trial について、スコアラーは LLM 出力テキストのみを見て以下の **二つの 0/1 判定** を独立に下す。

### 5.1 Q_quant: 定量乖離検出(主スコア)

**1点の条件(全て満たす):**
- LLM 出力に「想定/期待/baseline/typical」値と実測値の **数値的な比較**が含まれる
- かつ、その比較が「N倍ずれている」「N% 上回る」等の **明示的な乖離量**を述べている
- かつ、判定方向(超過/未満)が ground truth と一致している

**0点となる代表例:**
- 「異常に高い」等の定性的言及のみ
- 想定値への言及なしに「想定通り」と述べる
- 想定値を捏造して(LLM が prior から作って)比較する場合も 0点 ★重要
  - 例: H1 L0 で「a naive baseline would assume 10-30% deviation」→ 0(捏造ベースライン)

### 5.2 Q_aware: 現状把握(副スコア、null prediction 用)

**1点の条件:**
- LLM 出力が当該指標の実測値を正しく要約している(数値の reading 正確)
- かつ「supported / contradicted / inconclusive」のいずれかの判定を下している

両スコアは独立。同じ trial が (1, 0)、(0, 1)、(1, 1)、(0, 0) のいずれもありうる。

## 6. 盲検採点プロトコル

1. **実行者(Runner agent)**: 仮説と level プロンプトを受け、LLM 出力を JSON に保存。出力ファイル名は `trial_<UUID>.json`(level/hypothesis を含めない)
2. **マスキング**: 別プロセスが trial を読み込み、出力テキストから以下を除去:
   - 仮説 ID/名称(`H1`, `Q4`, `VIP` 等のキーワードはそのまま残す。これは出力本体)
   - level ラベル(`L0`, `L3`, "ontology" 等)
   - **マスクするのは "ファイル名・メタデータ・プロンプト echo" のみ**。LLM 出力本体は無改変
3. **採点者(Scorer agent)**: 別 Claude Code サブエージェント、独立コンテキスト。マスク済み出力テキストを受け、5.1/5.2 の判定のみを返す。ground truth・仮説 ID・level を**知らない**
4. **二重採点**: 各 trial を 2 回独立に採点(別サブエージェント)。不一致は protocol 違反としてログし、3人目で多数決
5. **採点者は本プロトコルを読まない**: 採点ルール文面のみ渡す。研究の動機・主仮説・期待される結果は伝えない

## 7. 除外・再実行ルール(事前固定)

- API エラー、JSON parse 失敗の場合のみ再実行を許可。**最大 1 回**
- 再実行後も失敗した trial は除外。除外数を結果セクションに明記
- それ以外の理由(「結果が予想と違うから」等)での再実行・除外は **禁止**

## 8. 成功条件(事前固定)

| 結果 | 解釈 |
|---|---|
| H_main 有意かつ効果量 ≥ 0.4 | 核心主張を **confirmatory に支持** |
| H_main 有意だが効果量 < 0.4 | 「方向は一致するが効果は exploratory より小」と記録 |
| H_main 非有意 | **核心主張は confirmatory 再現に失敗**。発表で正直に開示し、exploratory finding の解釈を制限 |
| H_null 有意差あり | ceiling assumption 不成立。H_main の解釈に caveat 追加 |

**いずれの結果でも全データ・全コードを公開する。** 結果を見てからの追加分析は "post-hoc, exploratory" と明示ラベル。

## 9. 分析計画(事前固定)

1. (hypothesis, level) セルごとの平均 Q_quant、95% CI(bootstrap)
2. Wilcoxon signed-rank(paired by hypothesis-trial)
3. 効果量: L3 mean - L0 mean(0-1 スケール)
4. Q_aware について同上
5. 二重採点の一致率(Cohen's kappa)

予定スクリプト: `notebooks/confirmatory.py`(marimo)

## 10. 公開物

- 本プロトコル(本ファイル、コミット時点で凍結)
- `data/confirmatory/trial_*.json` 全 40 件
- `notebooks/confirmatory.py` 分析ノートブック
- 結果 section(本ファイル末尾に追記、結果改変禁止)

---

## 11. 結果(データ収集後に追記)

*このセクションは実験完了後にのみ追記される。プロトコル本体(Section 1-10)はその時点で改変しない。*

**データ収集期間**: 2026-04-12(単日、並列実行)
**実行コミット**: trials = 大部分が自動ドライバで実行(`scripts/run_confirmatory.py`)、最初の 8 trials は Claude Code サブエージェント経由(手動保存)
**除外・再実行**: 0 件(全 40 trials が初回成功、JSON parse も全件成功)
**モデル**: Claude Opus 4.6(runner, scorer 共通)

### 11.1 事前登録された主仮説の検定結果

| 指標 | 値 |
|---|---|
| Wilcoxon 統計量(片側, L3 > L0) | 55.00 |
| **p 値** | **0.00148** |
| 効果量(平均 L3 − L0, Q_quant) | **0.450** |
| 95% ブートストラップ CI | [0.250, 0.650] |
| 事前登録基準: p < 0.05 **かつ** 効果量 ≥ 0.4 | **両方を満たす** |

→ **H_main: 核心主張は confirmatory に支持された**

### 11.2 null prediction(H_null, Q_aware)

| 指標 | 値 |
|---|---|
| Wilcoxon 統計量(両側) | 0.00 |
| p 値 | 0.3173 |
| 平均差(L3 − L0) | 0.050 |

→ **Q_aware(現状把握)は L0/L3 で有意差なし。ceiling assumption 成立**、H_main の解釈は無修正で維持できる。

### 11.3 Inter-rater reliability

|  | 一致率 | Cohen's κ |
|---|---|---|
| Q_quant | 95.0% (38/40) | **0.857** |
| Q_aware | 100.0% (40/40) | **1.000** |

Q_quant の κ=0.857 は "almost perfect agreement" 水準。採点ルーブリックの operationalization は再現可能だったと言える。

### 11.4 Per-cell breakdown(Q_quant 平均、2-scorer 平均)

| Hypothesis | Observed | Expected (L3 only) | L0 | L3 | Gap |
|---|---|---|---|---|---|
| H1 Q4 売上 | +96% | 30–50% | 0.90 | 1.00 | 0.10 |
| H2 割引→注文 | +7% | 15–30% | **0.30** | **1.00** | **0.70** |
| H3 VIP AOV | +601% | 40–60% | **0.00** | **1.00** | **1.00** |
| H4 季節 Q4 | 15× | 2–3× | 1.00 | 1.00 | 0.00 |

**構造的観察(post-hoc, exploratory)**:
- **H3 は最もクリーンな証拠**: L0 は観測値 "VIP は New の 7x" を計算できるが、"40–60% を想定していた"という expectation 比較を**一度も**行わない。L3 では 5/5 で expectation 比較が発生。
- **H2 は最も重要な bias 開示**: 観測値(+7%)が想定(15–30%)未満という "negative deviation" は L0 では検出失敗(support と誤判定されやすい)。
- **H1 は claim 自己言及の罠**: 仮説文 "Q4 > Q1-Q3 average" が比較対象を内包するため、L0 でも "Q4 は平均の 1.96x" と定量的に語れる。この場合、期待値の追加価値は限定的。
- **H4 は extreme deviation の罠**: 15x という極端な乖離では L0 も within-data 比率を計算し、"異常" と判定できてしまう。

これらは事前登録の予測ではなかったが、**核心主張をより精密化する方向**の知見である。

### 11.5 Confirmatory study の結論

- 片側 Wilcoxon の p = 0.00148、効果量 0.45、CI [0.25, 0.65] で **H_main を支持**
- null prediction(Q_aware 天井)も成立
- Inter-rater κ = 0.857 で採点の再現性を担保
- exploratory 104 実験の核心主張は、**事前登録・盲検・二重採点の確認試験でも再現された**

ただし以下の caveat を付す:
1. Opus 4.6 単一モデルでの検定(他モデルでの検定は未実施)
2. 合成 e-commerce データの 4 仮説のみ(真のドメイン転移は未実施)
3. 効果量 0.45 は per-cell で大きく分布するため、"期待値が critical" の主張は **"中程度から大きな乖離(15–30%想定 vs ±7%〜+600%)" の regime で最も強く成立**。Extreme lift(15x)でも trivial な directional 検定でも、L0 は独自に定量感を出せる。

これは exploratory phase では定性的にしか述べられなかった "構造" の confirmatory な定量化である。

