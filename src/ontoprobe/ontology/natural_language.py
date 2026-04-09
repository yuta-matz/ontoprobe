"""Natural language formatting of ontology knowledge for RDF vs NL comparison."""

from ontoprobe.ontology.query import CausalRule, MetricMapping


def _rule_to_paragraph(rule: CausalRule) -> str:
    """Convert a single causal rule to a natural language paragraph."""
    sentences = []

    # Core causal relationship: cause → effect + direction
    sentences.append(
        f"{rule.cause} is known to {rule.direction} {rule.effect}."
    )

    # Expected magnitude
    if rule.magnitude:
        sentences.append(
            f"The expected magnitude of this effect is {rule.magnitude}."
        )

    # Condition
    if rule.condition:
        sentences.append(
            f"This relationship holds when {rule.condition}."
        )

    # Comparison baseline
    if rule.compared_to:
        sentences.append(
            f"This is measured relative to {rule.compared_to}."
        )

    # Description (same as RDF's hasDescription)
    sentences.append(rule.description)

    return " ".join(sentences)


def format_nl_context(
    rules: list[CausalRule],
    mappings: list[MetricMapping],
) -> str:
    """Format ontology knowledge as natural language prose.

    Produces the same information as format_ontology_context() but
    with causal rules expressed as prose paragraphs instead of
    structured bullet points. Class hierarchy and metric mappings
    sections remain identical to isolate the effect of rule format.
    """
    lines = ["## Domain Knowledge (Ontology)\n"]

    lines.append("### Causal Rules\n")
    for rule in rules:
        lines.append(_rule_to_paragraph(rule))
        lines.append("")  # blank line between paragraphs

    lines.append("### Metric Mappings")
    lines.append("Ontology concepts mapped to dbt metrics:")
    for m in mappings:
        lines.append(f"  - {m.concept} → `{m.dbt_metric}`")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# MEMO condition: individual internal documents (reports, memos, Slack)
# Each rule is a separate short document. Same info, different sources.
# ---------------------------------------------------------------------------

_MEMO_TEMPLATES: dict[str, str] = {
    "rule_discount_order_volume": """\
【マーケティング定例 議事録より抜粋】
田中さんから、過去の割引キャンペーンの効果について共有がありました。
10%以上の割引を出したときは注文数がだいたい15〜30%くらい伸びる傾向があるとのこと。
非キャンペーン期間と比較した数字です。次回のサマーセールでも同様の効果を見込んで
予算を組みたいという話でした。""",

    "rule_seasonal_revenue": """\
【Q4振り返りミーティング メモ】
季節商品（冬物ファッション、ギフトセットなど）のQ4売上について。
毎年Q4は他の四半期に比べて2〜3倍くらいに跳ね上がる。去年もそうだったし、
一昨年もだいたいそんな感じ。在庫の積み増しは9月中に判断したいので、
来月の会議でまた議論しましょう。""",

    "rule_vip_higher_aov": """\
【CRM戦略会議 資料より】
VIP顧客のAOV（平均注文額）は新規顧客と比較して40〜60%ほど高いことが
確認されています。購買力とエンゲージメントの深さを反映していると思われます。
VIP向けの限定セールはROIが高いので、引き続き注力すべきとの意見が多数でした。""",

    "rule_free_shipping_volume": """\
【施策レビュー Slackまとめ】
鈴木: 送料無料キャンペーンの効果ってどのくらいでしたっけ？
佐藤: 過去のデータだと注文数10〜20%増くらいですね。割引より控えめですが
コストも低いのでROIは悪くないです。
鈴木: なるほど、次の施策候補に入れておきます。""",

    "rule_repeat_clv": """\
【データ分析チーム 週次レポートより】
リピート購入率とLTV（顧客生涯価値）の関係を確認しました。
予想どおり正の相関が見られます。リピーターほどLTVが高い傾向で、
これはまあ当然といえば当然なんですが、CRM施策の優先度を考えるうえで
改めて定量的に確認できたのは良かったです。""",

    "rule_q4_overall_revenue": """\
【経営会議 四半期レビュー 抜粋】
Q4の全体売上は四半期平均に対して30〜50%程度高くなっています。
ホリデーシーズンの需要増と年末のキャンペーン集中が主因です。
来期も同程度の上振れを見込んで年間計画を策定する予定です。""",

    "rule_discount_reduces_margin": """\
【ファイナンスチーム 月次MTG 議事録】
割引率とマージンの関係について改めて整理しました。
割引率が上がるほど割引総額も比例して大きくなり、実質的な受取額が減ります。
30%オフのBlack Fridayは客数は取れるんですが、マージンへの影響が大きいので
来年はもう少し控えめな設定（20%上限とか）も検討したいという声がありました。""",
}


def format_memo_context(
    rules: list[CausalRule],
    mappings: list[MetricMapping],
) -> str:
    """Format ontology knowledge as individual internal documents.

    Each rule appears as a separate short document (meeting notes, Slack,
    reports) from different sources.
    """
    lines = ["## Domain Knowledge (Internal Documents)\n"]

    lines.append("以下は社内の議事録・レポート・チャットから抽出した、")
    lines.append("ビジネスに関するドメイン知識です。\n")

    for rule in rules:
        template = _MEMO_TEMPLATES.get(rule.name)
        if template:
            lines.append(template)
            lines.append("")

    lines.append("### Metric Mappings")
    lines.append("Ontology concepts mapped to dbt metrics:")
    for m in mappings:
        lines.append(f"  - {m.concept} → `{m.dbt_metric}`")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# DOC condition: single realistic meeting minutes
# All rules embedded in one document with noise and conversational tone.
# ---------------------------------------------------------------------------

_DOC_BODY = """\
【マーケティング部 定例ミーティング 議事録】
日時: 2025/10/15 14:00-15:30
出席者: 田中（部長）、鈴木、佐藤、山田、李
書記: 山田

■ 前回アクションの確認
・新オフィスの引越し日程は11/20で確定。荷物の梱包は各自で。
・採用面接のスケジュール、来週中に人事から連絡が来るとのこと。

■ サマーセール振り返り
田中: サマーセールの数字が出揃ったので共有します。割引ありの期間は
やっぱり注文数伸びますね。ただ今回、そこまで劇的ではなかった。
鈴木: 具体的にはどのくらいでした？
田中: 割引10%以上出してたときで、通常期と比べて15〜30%増ってところ。
前回のBlack Fridayのときもだいたいそんな感じだったので、まあ想定内かと。
佐藤: 送料無料のほうはどうでしたっけ？
田中: 送料無料は割引ほどインパクトないんですよね。注文数でいうと10〜20%増
くらい。ただコストが小さいのでROIは悪くないです。
鈴木: なるほど。次のキャンペーン、送料無料をベースに割引は控えめにする案も
ありかもしれませんね。
田中: それ検討しましょう。あ、あと経理から言われてるんですが、割引率上げすぎ
問題。割引率に比例して割引総額が膨らむのはまあ当然として、30%オフの
Black Fridayは実質の受取額がかなり減ってたと。来年は上限20%とかにしたい
みたいな話が出てます。
佐藤: マージンへの影響、ちゃんと数字で見たほうがいいですね。

■ Q4の見通し
田中: 毎年の話ですが、Q4は全体売上が他の四半期に比べて3〜5割くらい高くなります。
ホリデーシーズンの駆け込みと年末セールが重なるので。
鈴木: 季節商品はもっとすごいですよね？
田中: そうそう。冬物ファッションとかギフトセットとか、Q4だけで他の四半期の
2〜3倍くらい売れる。去年も一昨年もそんな感じ。在庫の積み増しは
9月中に判断しないといけないので、発注チームと早めに握りましょう。
山田: 倉庫のキャパ大丈夫ですかね。去年パンクしかけたじゃないですか。
田中: そこは物流チームと別途調整します。

■ 顧客セグメント施策
佐藤: CRMの分析チームからレポートが上がってきてるんですけど、いくつか
共有させてください。まずVIP顧客のAOV（平均注文額）、新規のお客さんと
比べると4〜6割くらい高い。まあ感覚的にはそうだろうなって感じですけど、
数字で改めて確認できました。
鈴木: VIP向けの限定セール、引き続きやったほうがよさそうですね。
佐藤: はい。あとリピート率とLTVの関係も見てるんですけど、まあ予想通り
正の相関ですね。リピーターほど生涯価値が高い。当たり前っちゃ当たり前
なんですが、CRMの優先度づけに使えるかなと。
田中: そのへんのデータ、次回の経営会議で使いたいのでスライドにまとめて
もらえますか？
佐藤: 了解です。

■ その他
・来月の忘年会、幹事は山田さん。場所は新宿あたりで探すとのこと。
・社内勉強会のテーマ募集中。希望があればSlackに投稿してください。

次回: 2025/10/29 14:00-"""


def format_doc_context(
    rules: list[CausalRule],
    mappings: list[MetricMapping],
) -> str:
    """Format ontology knowledge as internal documents (meeting minutes, memos).

    Contains the same factual information as RDF/NL conditions but
    embedded in a realistic meeting minutes document with context,
    noise, and conversational tone.
    """
    lines = ["## Domain Knowledge (Internal Documents)\n"]

    lines.append("以下は社内の議事録から抽出した、ビジネスに関するドメイン知識です。\n")
    lines.append(_DOC_BODY)
    lines.append("")

    lines.append("### Metric Mappings")
    lines.append("Ontology concepts mapped to dbt metrics:")
    for m in mappings:
        lines.append(f"  - {m.concept} → `{m.dbt_metric}`")

    return "\n".join(lines)
