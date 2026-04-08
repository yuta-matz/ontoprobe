# オントロジー入門ガイド — データ分析者のためのドメイン知識の構造化

## この文書の対象

- SQLやdbtは使えるが、オントロジーは初めて
- LLMを使ったデータ分析に興味がある
- 「ドメイン知識を機械可読にする」とはどういうことか知りたい

---

## 1. オントロジーとは何か

### 一言で

**「ある分野の知識を、機械が読み取れる形で整理したもの」**

### もう少し詳しく

ECサイトで働く人なら、こんなことを「当たり前」として知っている：

- VIP顧客は普通の顧客より多く買う
- 冬物コートは冬に売れる
- 割引キャンペーンをすると注文が増える

これらは **ドメイン知識**（業務知識）と呼ばれる。人間はこれを暗黙的に知っているが、機械（LLM含む）はデータベースを見ただけでは分からない。

オントロジーは、この暗黙知を **明示的・構造的に記述** する方法である。

### データベースとの違い

| | データベース | オントロジー |
|---|---|---|
| 格納するもの | 事実（何が起きたか） | 知識（なぜ起きるか） |
| 例 | 「注文ID 1234は12月に発生」 | 「冬物商品は12月に売上が2-3倍になる」 |
| 変更頻度 | 毎秒（トランザクション） | 稀（知識の更新時のみ） |
| 問いへの答え | 「いくら売れた？」 | 「なぜ売れた？」 |

```
データベース: 12月の売上は1,000万円だった        ← 事実
オントロジー: 冬物商品はQ4に売上が2-3倍になる    ← 知識
                ↓ 組み合わせると
仮説検証:    「12月の売上増は冬物商品の季節需要が主因か？」 ← 検証可能な問い
```

---

## 2. 実際のオントロジーを見てみる

### 最小の例

「VIP顧客は平均注文額が高い」という知識を記述する：

```turtle
# 「VIP顧客」というものが存在する
:VIPCustomer a owl:Class ;
    rdfs:label "VIP Customer" .

# 「平均注文額」というメトリクスが存在する
:AverageOrderValue a :Metric ;
    :measuredBy "average_order_value" .

# VIP顧客は平均注文額を40-60%押し上げる（New顧客と比較して）
:rule_vip_aov a :CausalRule ;
    :hasCause :VIPCustomer ;
    :hasEffect :AverageOrderValue ;
    :hasDirection "increase" ;
    :hasExpectedMagnitude "40-60%" ;
    :hasComparedTo :NewCustomer .
```

### これは何をしているのか

3つのことを記述している：

1. **概念の定義** — 「VIP顧客」「平均注文額」という概念を名前付きで定義
2. **データとの接続** — 「平均注文額」は dbt の `average_order_value` メトリクスで測定できる
3. **因果関係** — VIP顧客は平均注文額を押し上げる。程度は40-60%。比較対象はNew顧客

### 書式について

上の例は **Turtle** という形式で書かれている。OWL/RDFオントロジーの代表的な記法の一つ。

```turtle
:VIPCustomer a owl:Class .
```

これは日本語に訳すと：

```
VIPCustomer は クラス（概念）である。
```

`:hasCause :VIPCustomer` は：

```
原因は VIPCustomer である。
```

Turtleは「主語 述語 目的語 .」の繰り返しで知識を記述する。人間にもそこそこ読みやすく、機械にも解析しやすい形式。

---

## 3. オントロジーの構成要素

ontoprobeプロジェクトのオントロジーは3つの要素で構成される。

### 3.1 クラス階層 — 「何があるか」

データベースのカラム値に意味を与える。

```
Customer（顧客）
├── NewCustomer      ← customer_segment = 'new'
├── ReturningCustomer ← customer_segment = 'returning'
└── VIPCustomer      ← customer_segment = 'vip'

Product（商品）
├── SeasonalProduct  ← is_seasonal = true （季節商品）
└── EvergreenProduct ← is_seasonal = false（通年商品）

Campaign（キャンペーン）
├── DiscountCampaign      ← campaign_type = 'discount'
└── FreeShippingCampaign  ← campaign_type = 'free_shipping'
```

**なぜ必要か：** データベースの `is_seasonal = true` だけでは「何が季節的なのか」が分からない。クラス定義により「需要が特定季節に集中する商品」という意味が明確になる。

### 3.2 メトリクスマッピング — 「どう測るか」

オントロジーの概念とデータベースのメトリクスを接続する。

```
オントロジーの概念        dbtメトリクス              実際のSQL
─────────────          ─────────────            ──────────
Revenue           →    total_revenue        →   SUM(total_amount) on fct_orders
Order Volume      →    order_count          →   COUNT(order_id) on fct_orders
Average Order Value →  average_order_value  →   AVG(total_amount) on fct_orders
```

**なぜ必要か：** オントロジーで「売上が上がる」と言ったときに、具体的にどのSQLで検証するかを定義する橋渡し。これがないとオントロジーは「絵に描いた餅」で終わる。

### 3.3 因果ルール — 「なぜそうなるか」

最も重要な部分。ドメインの因果関係を記述する。

```
┌─────────────────────────────────────────────────────┐
│ ルール: 割引キャンペーンは注文数を増加させる          │
│                                                     │
│   原因:     DiscountCampaign  （割引キャンペーン）    │
│   結果:     OrderVolume        （注文数）             │
│   方向:     increase           （増加）              │
│   期待値:   15-30%             （15-30%増加）         │
│   条件:     discount > 10%     （割引率10%超のとき）   │
└─────────────────────────────────────────────────────┘
```

**なぜ必要か：** データから「キャンペーン中に注文が7%増えた」と分かっても、それが良いのか悪いのか分からない。「15-30%増えるはず」という期待値があって初めて「期待以下」と判定できる。

---

## 4. オントロジーがあると何ができるか

### 具体例: 「売上が上がった原因は？」

#### オントロジーなしの場合

LLMはデータベースのメタデータ（テーブル名、カラム名）だけを手がかりに分析する。

```
→ 四半期別に集計してみよう
→ Q4が高いことが分かった
→ セグメント別に分けてみよう
→ VIPの売上が大きいことが分かった
→ ...で、なぜ？どうすべき？ → 答えられない
```

手当たり次第にdimensionで分解する「探索的分析」はできるが、**なぜそうなったか**の説明と**どうすべきか**の提案ができない。

#### オントロジーありの場合

LLMは因果ルールに導かれて仮説を検証する。

```
→ 因果ルール「季節商品はQ4に2-3倍売上増」がある
→ 仮説: Q4売上増は季節商品の需要集中が主因
→ SQL実行: Q4の季節商品売上は他四半期の15倍
→ 判定: 仮説を支持。ただし期待値2-3倍を大幅超過（異常）
→ 提案: 季節商品の在庫計画見直し、データ生成パラメータの確認
```

### できることの比較表

| 能力 | なし | あり |
|------|------|------|
| データ集計 | できる | できる |
| パターン発見 | できる | できる |
| 因果の説明 | **できない** | できる |
| 異常の検出 | **できない** | できる |
| 施策の提案 | **できない** | できる |

---

## 5. 因果ルールのプロパティ詳細

因果ルールは最大7つのプロパティを持つ。すべてが必須ではないが、記述量に応じて分析の質が段階的に向上する。

### 一覧

| プロパティ | 意味 | 例 | 重要度 |
|-----------|------|-----|-------|
| `hasCause` | 原因（何が） | DiscountCampaign | 必須 |
| `hasEffect` | 結果（何に影響） | OrderVolume | 必須 |
| `hasDirection` | 方向（増 or 減） | increase | 必須 |
| `hasExpectedMagnitude` | 期待値（どれだけ） | 15-30% | 必須 |
| `hasCondition` | 条件（いつ適用） | discount > 10% | 推奨 |
| `hasComparedTo` | 比較対象 | NewCustomer | 推奨 |
| `hasDescription` | 自然言語説明 | "Discount campaigns..." | 任意 |

### 追加するごとに何が変わるか

```
プロパティなし      → 「データが見える」だけ           (達成率  7%)
+ クラス+マッピング → 「何を調べるべきか」のヒント      (達成率 20%)
+ 因果方向         → 検証可能な仮説を立てられる         (達成率 47%)
+ 期待値           → 異常を検出し改善を提案できる       (達成率 77%)  ← ここが最大の転換点
+ 条件・比較対象    → 検証の精度と提案の具体性が向上     (達成率 86%)
+ 説明文           → 施策提案をさらに具体化             (達成率 93%)
```

**最大の転換点は「期待値」の追加。** 「増える」と分かるだけではなく「15-30%増えるはず」という基準があって初めて、「+7%は期待以下」「+601%は異常」と判定できる。

### 良い記述と悪い記述

| | 悪い例 | 良い例 | 理由 |
|---|---|---|---|
| 期待値 | "positive correlation" | "15-30%" | 数値範囲の方が判定基準が明確 |
| 条件 | "冬に" | "order_quarter = 4" | SQLに直結する形式が有効 |
| 比較対象 | (省略) | "NewCustomerと比較" | ベースラインが明確になる |

---

## 6. ファイル構成

ontoprobeプロジェクトのオントロジーは2つのファイルで構成される。

```
ontology/
├── ecommerce.ttl     ← クラス階層 + メトリクスマッピング + 業務制約
└── causal_rules.ttl  ← 因果ルール（7つ）
```

### ecommerce.ttl（構造定義）

```turtle
# クラス定義
:VIPCustomer a owl:Class ;
    rdfs:subClassOf :Customer ;
    rdfs:label "VIP Customer"@en ;
    rdfs:comment "High-value customer, customer_segment = 'vip'"@en .

# メトリクス定義とdbtとの接続
:Revenue a :Metric ;
    rdfs:label "Revenue"@en ;
    :measuredBy "total_revenue" .

# 業務制約
:Order :hasConstraint :MinOrderValue .
```

### causal_rules.ttl（因果ルール）

```turtle
:rule_discount_order_volume a :CausalRule ;
    rdfs:label "Discount increases order volume"@en ;
    :hasCause :DiscountCampaign ;
    :hasEffect :OrderVolume ;
    :hasDirection "increase" ;
    :hasExpectedMagnitude "15-30%" ;
    :hasCondition "discount_percent > 10" ;
    :hasDescription "Discount campaigns with >10% off are expected to
        increase order volume by 15-30%" .
```

---

## 7. PoCデータについて

本プロジェクトのデータは `src/ontoprobe/db/seeder.py` により生成された**合成データ（synthetic data）**である。実在のECサイトのデータではない。

オントロジーの因果ルールが検証可能であることを示すため、以下のパターンが意図的に埋め込まれている：

| 埋め込みパターン | 実装方法 | 対応する因果ルール |
|----------------|---------|-----------------|
| 季節商品がQ4に集中 | Q4以外では季節商品の選択確率を10%に制限 | Seasonal products spike in Q4 |
| VIPが高額購入 | VIPは数量2-5点、価格倍率1.5x | VIP customers have higher AOV |
| Q4の注文数増加 | 10月以降のbase_ordersを8件/日（通常5件） | Q4 has highest overall revenue |
| キャンペーンで注文増 | 割引時1.25倍、送料無料時1.15倍 | Discount/Free shipping increases volume |
| セグメント構成比 | new:returning:vip = 50:35:15 | — |

乱数シードは `random.seed(42)` で固定されており、同じデータを再現できる。

合成データを使う理由は、PoCの段階では「仕組みが正しく動くか」の検証が目的であるため。実データでの運用時にはオントロジーの期待値を実際のドメイン知識に基づいて校正する必要がある。

---

## 8. PoC環境

ontoprobeプロジェクトは以下の技術スタックで構成されている。

| レイヤー | 技術 | 役割 |
|---------|------|------|
| データベース | **DuckDB** | ローカルで動作する軽量OLAPデータベース。インストール不要、ファイル1つで完結 |
| セマンティックレイヤー | **dbt** (dbt-duckdb) | メトリクスの定義（「売上 = SUM(total_amount)」等）とデータモデルの管理 |
| オントロジー | **rdflib** (OWL/RDF Turtle) | ドメイン知識の記述とSPARQLクエリによる取得 |
| LLM | **Claude Code** (Claude Opus 4.6) | 仮説生成とSQL生成・検証。Claude CodeのセッションからLLMを直接利用（API不要）。デモモードではLLM不使用 |
| パッケージ管理 | **uv** | Python依存関係の管理と仮想環境 |
| 可視化 | **marimo** + **plotly** | インタラクティブなEDAノートブック |

### なぜこの構成か

- **DuckDB:** PoCに最適。サーバー不要、`pip install duckdb` だけで使える。SQLも標準的
- **dbt:** セマンティックレイヤーの業界標準。メトリクス定義を宣言的に管理できる
- **rdflib:** Python で OWL/RDF を扱う標準ライブラリ。SPARQLクエリでオントロジーからルールを取得
- **uv:** 高速なPythonパッケージマネージャ。`uv run` でコマンド実行、`uv sync` で依存解決

### セットアップ手順

```bash
# 1. リポジトリをクローン
git clone https://github.com/yuta-matz/ontoprobe.git
cd ontoprobe

# 2. 依存関係をインストール
uv sync --all-extras

# 3. シードデータ生成 + DuckDBロード
uv run python -m ontoprobe.db.seeder

# 4. dbtモデルのビルド
cd dbt_project && uv run dbt build --profiles-dir . && cd ..

# 5. デモ実行（LLM不要）
uv run python -m ontoprobe --demo

# 6. EDAノートブック起動
uv run marimo edit notebooks/eda.py
```

本PoCの仮説検証では、Claude Code（Claude Opus 4.6）をLLMとして使用した。Claude Codeのセッション内でコンテキスト（DBメタデータ、セマンティックレイヤー、オントロジー）を読み取り、仮説生成・SQL実行・結果分析をすべて実行した。APIキーの設定は不要。デモモード（`--demo`）ではLLM自体も不使用で動作する。

---

## 9. 実行の流れ

オントロジーは以下の流れでデータ分析に使われる。

```
Step 1: コンテキスト組み立て
  DBメタデータ（テーブル構造）
  + dbtセマンティックレイヤー（メトリクス定義）
  + オントロジー（因果ルール）
        │
        ▼
Step 2: 仮説生成（LLMまたは事前定義）
  因果ルールごとに検証可能な仮説を生成
  例: 「割引キャンペーン中の注文数は15-30%多いはず」
        │
        ▼
Step 3: SQL実行
  仮説をDuckDBのSQLクエリに変換して実行
  例: SELECT has_campaign, AVG(daily_orders) FROM ...
        │
        ▼
Step 4: 検証
  クエリ結果を期待値と比較して判定
  例: +7% → 期待値15-30%を下回る → 「期待以下」
        │
        ▼
Step 5: レポート
  supported / contradicted / inconclusive で結論
  + 改善提案
```

---

## 10. 他の技術との比較

### セマンティックレイヤー（dbt）との違い

| | セマンティックレイヤー | オントロジー |
|---|---|---|
| 定義するもの | メトリクスの計算方法 | メトリクス間の因果関係 |
| 例 | revenue = SUM(total_amount) | DiscountCampaign → revenue: increase |
| 役割 | 「何をどう計算するか」 | 「なぜそうなるか」 |
| ツール | dbt, Cube, Looker | OWL/RDF, Protege |

両者は排他的ではなく補完的。メトリクスマッピング（`:measuredBy`）で接続される。

### ナレッジグラフとの違い

| | ナレッジグラフ | 本プロジェクトのオントロジー |
|---|---|---|
| 格納するもの | エンティティ間の関係（事実） | ドメインの因果知識（法則） |
| 例 | 「商品Aはカテゴリ電子機器に属する」 | 「割引はorderVolumeを15-30%増加させる」 |
| 規模 | 数百万〜数億トリプル | 数十〜数百トリプル |
| 更新 | データ変更のたびに | ドメイン知識の変更時のみ |

本プロジェクトのオントロジーはナレッジグラフよりはるかに小さく、**法則（ルール）の記述に特化** している。

### プロンプトエンジニアリングとの違い

| | プロンプトに直接書く | オントロジー |
|---|---|---|
| 管理 | プロンプト内に散在 | 独立ファイルで管理 |
| 再利用 | コピペ | SPARQLで取得 |
| 検証 | 困難 | 構造的に可能 |
| バージョン管理 | 困難 | Gitで管理可能 |

ドメイン知識が少ないうちはプロンプトに直接書いても問題ないが、ルール数が増えると管理が破綻する。オントロジーは知識の構造化・管理のための仕組み。

---

## 11. はじめの一歩

自分のドメインでオントロジーを作り始めるなら：

### Step 1: 主要な概念を3-5個書き出す

```
例: Customer, Product, Campaign, Order
```

### Step 2: サブクラスを追加する

```
例: Customer → VIP / New / Returning
```

### Step 3: 測定可能なメトリクスを定義する

```
例: Revenue → SUM(total_amount)
```

### Step 4: 因果ルールを1つ書く

```
例: DiscountCampaign → OrderVolume: increase, 15-30%
```

### Step 5: データで検証する

期待通りかどうか確認し、ルールを修正する。

最初から完璧を目指す必要はない。**1つの因果ルールから始めて、検証結果を見ながら育てていく** のが現実的。

---

## 12. 用語集

| 用語 | 意味 |
|------|------|
| **オントロジー** | ある分野の知識を機械可読な形で整理したもの |
| **OWL** | Web Ontology Language。オントロジー記述の標準規格 |
| **RDF** | Resource Description Framework。「主語-述語-目的語」でデータを表現する枠組み |
| **Turtle (.ttl)** | RDFの記法の一つ。人間に読みやすい |
| **SPARQL** | RDFデータに対するクエリ言語（SQLのRDF版） |
| **クラス** | 概念のカテゴリ（例: Customer, Product） |
| **インスタンス** | クラスに属する具体的な個体（例: Revenue, OrderVolume） |
| **プロパティ** | 概念間の関係（例: hasCause, hasEffect） |
| **トリプル** | 「主語 述語 目的語」の1組。RDFの最小単位 |
| **因果ルール** | 原因と結果の関係を記述したルール |
| **セマンティックレイヤー** | メトリクスの定義と計算方法を管理する層（dbt等） |
| **メトリクスマッピング** | オントロジーの概念とセマンティックレイヤーを接続する定義 |
