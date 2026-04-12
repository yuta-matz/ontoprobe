# Theory v2 — 期待値プロパティの認知的役割(精密化版)

**Status**: Reference document, 2026-04-12 作成、同日 v2 結果で改訂
**Supersedes**: `reports/llm_experiment_poc.md` §4 の "原理的に不可能" 主張
**Basis**: 104 exploratory + 40 confirmatory v1 (H1-H4) + 40 confirmatory v2 (H5-H8, prior-resistant)
**Strongest evidence**: confirmatory v2 (`reports/confirmatory_protocol_v2.md`)
- Wilcoxon p = 1.69 × 10⁻⁵
- 効果量 0.875, 95% CI [0.725, 1.000]
- Cohen's κ = 0.950

このメモは、発表骨子・レポート・Q&A 回答すべての参照点となる。以降の資料はこの枠組みから逸脱しないこと。

---

## 1. 一文サマリ

> **LLM は観測値を記述できるが、記述と判定は別物である。観測値を「想定からの乖離」に変換する認知操作は、期待値プロパティが提供されない限り起きない。**

## 2. なぜ v1 の「原理的に不可能」は強すぎたか

v1 主張: 「定量的な乖離判定は期待値プロパティなしには原理的に不可能」

Confirmatory の per-cell 実測(n=5 × 4仮説 × 2条件、盲検二重採点):

| 仮説 | 観測値 | 想定(L3のみ) | L0 Q_quant | L3 Q_quant |
|---|---|---|---|---|
| H1 Q4売上 | +96% | 30–50% | 0.90 | 1.00 |
| H2 割引→注文 | +7% | 15–30% | 0.30 | 1.00 |
| H3 VIP AOV | +601% | 40–60% | **0.00** | 1.00 |
| H4 季節Q4 | 15× | 2–3× | 1.00 | 1.00 |

- H3 ケースだけが「L0 は定量乖離判定を一切しない」を**文字通り**支持する
- H1 / H4 は L0 でも定量出力が出る
- よって「原理的に不可能」は H3 regime でのみ真、他の regime では精密化が必要

## 3. 3 層の認知タスクモデル

これまで "定量乖離検出" という単一バケツに入れていた操作は、独立した 3 つのタスクである。

| 層 | タスク名 | 例 | LLM の L0 能力 | 必要な情報源 |
|---|---|---|---|---|
| **T1** | 観測内記述 | "Q4 は Q1-Q3 平均の 1.96 倍" | **可能** | query result のみ |
| **T2** | 期待値比較 | "観測 96% は想定 30-50% を超える" | **不可** | 外部 expected 値 |
| **T3** | 規範判定 | "この乖離は施策変更に値する" | **不可** | 規範閾値 + 意思決定文脈 |

- T1 は LLM のデフォルト認知モード(「データにあるものを記述する」)
- T2 は T1 とは**異なる** frame を要求する(「データに無いものを参照する」)
- T3 は T2 を前提とした上で、さらに normative label を要求する

**期待値プロパティの真の仕事**: T1 → T2 のフレーム遷移を**強制**すること。
LLM は自発的に T2 frame に入らない。expected 値が prompt に存在しない限り、LLM の default は T1 で完結する。

## 4. なぜ L0 は自発的に T2 に入らないか

### 情報理論的根拠
- 組織固有の「想定値」は訓練データに存在しない(private information)
- LLM は "generic 業界平均" を prior として持つが、それは任意の組織の specific target と一致する保証がない
- 従って L0 で T2 に入っても、比較対象は LLM が捏造した generic prior になる

### 行動的根拠
- Part A の exploratory 観察: L0-L2 で LLM は時々 "naive baseline" を捏造する("通常 10-30% 想定" 等)
- Confirmatory の観察: 多くの場合は捏造すらせず、T1 のまま終わる(observed ratio を述べて verdict を下す)
- つまり L0 LLM の典型的挙動は「T1 で完結して T2 を省略する」であり、稀に「T2 風に見える出力をするが比較対象が捏造」となる

### どちらの挙動も T2 として機能しない
- 省略: そもそも expectation と比較していない
- 捏造: 比較対象が組織の想定と無関係

**結論**: T2 frame への遷移には、prompt に expected 値が explicit に存在することが必要条件。

## 5. Boundary conditions — v2 で仮説設計の artifact と判明

**重要更新(v2 以降)**: 以下の "boundary conditions" は当初 theory v2 初稿では「理論の限界」として扱っていたが、**confirmatory v2 によって "v1 hypothesis set 固有の artifact" であったと判明した**。prior-resistant hypothesis set(H5-H8)では L0 ≤ 0.20 と L0 の定量出力が消失したため、この節は「v1 hypothesis set がなぜ effect size を過小評価したか」の説明として読むべき。

### Boundary 1: Claim 自己言及型(H1 ケース)
- 仮説文自体が比較構造を内包("Q4 > Q1-Q3 average")
- L0 LLM は claim を読むだけで比較対象を取得でき、within-data 比率を計算できる
- その出力は表層上は T2 的に見える("Q4 is 1.96x the Q1-Q3 average")
- **実質**: T1 を T2 風に言い換えているだけ。組織の想定値は一切参照されていない
- **実務含意**: hypothesis 生成段階で比較対象を内包させると L0 でも "定量的に見える" が、それは T2 の代替ではない

### Boundary 2: Extreme lift 型(H4 ケース)
- 観測値が極端(15x 等)
- L0 LLM は within-data 比率だけで「これは異常」と感じられる
- "Obvious anomaly" は T1 の範囲内で処理できてしまう
- **実質**: 異常の "検出" はできているが、"どの程度想定から外れているか" の定量化はしていない
- **実務含意**: extreme な deviation は L0 でも検出可能、だが判定理由の解像度は低い

### Boundary 3: Trivial directional 型
- 仮説が方向性のみ("A は B より大きい")
- L0 LLM は単純な比較で答えられる
- この場合 T2 は不要(そもそも期待値比較が問題設定に含まれない)
- **実務含意**: 仮説の性質によっては L0 で十分

### Regime map

```
                deviation の大きさ →
                trivial    moderate    extreme
              ┌────────────┬───────────┬────────────┐
  claim が    │ L0 充分    │ L0 充分  │ L0 充分    │
  比較構造    │ (H1型)    │           │            │
  内包        ├────────────┼───────────┼────────────┤
  claim が    │ L0 充分    │ **期待値**│ L0 が異常  │
  比較構造    │ (方向だけ) │ **必須**  │ 検出可能   │
  を持たず    │            │ (H2,H3型) │ (H4型)     │
              └────────────┴───────────┴────────────┘
                               ↑
                 期待値プロパティが critical な regime
```

核心主張は図の中央セルで最も強く成立する。

## 6. 精密化された主張(発表で使う公式版)

**核心主張(v2)**:
> 組織固有の想定と観測値を比較する認知操作(T2: 期待値比較)は、LLM のデフォルト認知モード(T1: 観測内記述)とは異なる frame を要求する。LLM は prompt に expected 値が explicit に提供されない限り、自発的に T2 frame に入らない。従って「観測値は想定を N% 超えている」という判定は、期待値プロパティが ontology 側で提供されて初めて可能になる。

**副次主張(v2 で追加)**:
> この必要性は deviation の regime に依存する。仮説文が比較構造を内包する場合、deviation が extreme な場合、あるいは問題設定が方向性のみを問う場合、L0 LLM は within-data 操作だけで表層上は定量的な出力を生成できる。従って期待値プロパティの限界効用は「中規模の deviation」かつ「仮説が比較構造を内包しない」regime で最大となる。

**情報理論的根拠**:
> 組織固有の想定値は訓練データに存在しない(private information)。LLM が保持する generic prior は、任意の組織の specific target と一致する保証がない。従って prompt に expected 値を注入する以外に、組織の想定を LLM に反映させる方法は原理的に存在しない。

## 7. confirmatory が支持した命題 / しなかった命題

### v1 (H1-H4, prior-friendly) ✓
1. L3 条件の Q_quant スコアは L0 より有意に高い(Wilcoxon p=0.00148)
2. 効果量 0.45(pre-registered ≥ 0.4 基準をクリア)
3. Q_aware(現状把握)は L0/L3 で有意差なし → ceiling 懸念棄却
4. Inter-rater κ=0.857 で採点は再現可能
5. v1 では H1 (L0=0.90) と H4 (L0=1.00) で L0 が高得点 → boundary conditions 存在

### v2 (H5-H8, prior-resistant) ✓✓ — 決定的証拠
1. Wilcoxon p = **1.69 × 10⁻⁵**(v1 より 2 桁強い)
2. 効果量 **0.875**(v1 の約 2 倍)、95% CI **[0.725, 1.000]**
3. Inter-rater κ = **0.950**
4. **4 仮説すべて L0 ≤ 0.20** — v1 の boundary conditions は仮説設計の artifact だったと確定
5. **H6 は pure T2 test** として機能 — LLM 自身が "target を知らない限り判定不能" と 5/5 で明言
6. **H7, H8 で L0 LLM は prior と逆方向の verdict を 5/5 で正しく出す** → LLM は prior に騙されていない、単に T2 frame に自発的に入らないだけ

### 決定的メカニズム観察(v2 由来、最重要)

**H7/H8 の L0 挙動を直視すると**:
- データ: Dec < Oct(-15%), VIP ≈ new(-1.1%)
- LLM prior: Dec > Oct, VIP ≫ new
- L0 LLM の verdict: 5/5 で "contradicted"(データ側が正しく読まれている)
- L0 LLM の Q_quant: 0.00〜0.20(expectation 比較言語を使っていない)

→ **LLM は prior に騙されていないが、自発的に「想定からの乖離」を語らない**
→ これは theory v2 の「T1 → T2 frame 遷移が必要」を直接実証する

**H6 の L0 挙動(より決定的)**:
- claim: "Tokyo Q4 revenue meets the internal target"
- L0 verdict: 5/5 で "inconclusive"(target を知らないため判定不能、LLM 自身が明言)
- L0 Q_quant: 0/5(期待値がないので比較言語なし)
- L3 verdict: 5/5 で "contradicted"(target 与えられて初めて判定可能)
- L3 Q_quant: 5/5

→ **LLM は自分の限界を認識している**("I cannot determine without the target")
→ 期待値プロパティは LLM の認知能力を拡張するのではなく、**既に存在する能力に対象を与える**

### 支持されなかった / 撤回した ✗
1. 「**原理的に**不可能」 → 「T1 → T2 frame 遷移が起きない」に refine
2. 「LLM は定量比較ができない」 → 「LLM は within-data 比率を計算できるが expected 比較には期待値が必要」
3. v1 の boundary conditions(H1, H4)は一般的限界ではなく prior-friendly 仮説設計の artifact

### 未決 / 今後の検証対象
1. 他モデル(Sonnet, GPT-5, Gemini)での再現
2. 真のドメイン転移(EC 以外)
3. **実データでの検証**(合成データは (1) 情報理論的主張の source 証明にはならない)
4. T3(規範判定)を測る実験設計
5. 事前登録なしの exploratory phase で観察した副次発見の confirmatory 検証

## 8. v1 の頑健性開示との関係

`llm_experiment_poc.md` §14 が開示した 6 つの妥当性問題のうち、confirmatory study により:

- ✓ 問題 1(非盲検)→ 解消(独立 scorer 2名)
- ✓ 問題 2(事前登録なし)→ 解消(protocol を git commit してから実験開始)
- ✓ 問題 3(異常検出の多義性)→ 解消(T1/T2 への分解 + 独立採点)
- ✓ 問題 6(3段階は粗い)→ 解消(二値化 + 2-scorer 平均で解像度維持)
- ⚠ 問題 4(L3 ceiling)→ Q_aware で実測、Q_quant には残存しない
- ⚠ 問題 5(double counting)→ T1/T2 独立採点で分離

**残る limitation**(v2 で明示):
- 単一モデル(Opus 4.6)での検定
- 合成 e-commerce データの 4 仮説のみ
- 表層言語で T1 と T2 を区別しているため、深層 meaning の区別は未検証

## 9. 発表で使うべき語彙(統制用)

以下の言葉は v2 と整合的:

- 「観測値の記述」(T1, L0 能力)
- 「期待値比較」「想定からの乖離判定」(T2, L3 能力)
- 「規範判定」「action 優先度」(T3, L4+ 能力)
- 「フレーム遷移」「認知モード切り替え」(T1 → T2 の役割説明)
- 「中規模 deviation regime」(期待値の限界効用が最大の領域)

以下の言葉は**避ける**:

- 「原理的に不可能」→ 「自発的には起きない」「frame 遷移を要求する」
- 「LLM は定量比較ができない」→ 「LLM の定量比較は観測内に閉じている」
- 「期待値は必須」→ 「中規模 deviation regime では critical」「extreme case では補助的」

## 10. この理論から派生する発表構成の修正方針

(次のステップで発表骨子を update する際の指針)

1. **Slide 2 の一本柱** は v2 一文サマリに差し替え
2. **Slide 18-21(結果グラフ類)** は per-cell を 4 仮説で表示し、regime map を併置
3. **Slide 28+(confirmatory)** は v2 theory への昇華として再構成(結果単体ではなく、理論 refinement の証拠として)
4. **Slide 29(next steps)** に T3 実験設計・他モデル検証・深層 meaning 採点を追加
5. **Q&A**:
   - 「原理的に不可能と言うが H4 で L0 できているのでは?」→ boundary condition 1/2 で応答
   - 「T1 と T2 の区別は結局表層言語の違いでは?」→ Yes, confirmatory は表層で測った。深層 meaning の区別は future work
