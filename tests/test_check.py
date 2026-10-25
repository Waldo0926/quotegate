"""check() against the ways a model's quotes go wrong: paraphrased, put on the wrong passage, cut from a
sentence that needs what is around it, or from a table, a question or a past year."""
import pytest

from quotegate import Dropped, Passage, Quote, Rules, check, parse, sentence
from quotegate.prompts import EN, ZH, user_message

R2026 = Rules(current_year=2026)


def reasons(result):
    return [d.reason for d in result.dropped]


def test_keeps_quotes_found_word_for_word_as_whole_sentences():
    ps = [Passage("Renewal must be submitted three months before the pass expires. Fees are paid online."),
          Passage("先在 EMGS 网站\n交申请，再等邮件通知。", soft_breaks=True)]
    r = check("[2] 先在 EMGS 网站交申请\n[1] Renewal must be submitted three months\n[9] something else", ps, R2026)
    assert r.ok and [q.text for q in r.kept] == [
        "先在 EMGS 网站交申请，再等邮件通知。", "Renewal must be submitted three months before the pass expires."]
    assert [q.passage for q in r.kept] == [2, 1]
    assert reasons(r) == ["not found"]                      # [9] names no passage
    q = r.kept[1]
    assert ps[0].text[q.start:q.end] == q.text


def test_a_paraphrase_an_added_step_or_the_wrong_passage_is_never_kept():
    ps = ["请在 Moodle 上传作业，并在三个工作日内提交医生证明。", "ISP 会在贴纸剩 14 天或更少时收护照。"]
    assert check("[1] 老师收到证明后会替你申请特殊考虑\n[2] 过期后有 14 天宽限期", ps).status == "unsupported"
    assert check("[2] 请在 Moodle 上传作业", ps).status == "unsupported"
    r = check("[1] 请在 Moodle 上传作业，并在三个工作日内提交医生证明。\n[1] 老师会替你申请特殊考虑", ps)
    assert r.ok and len(r.kept) == 1 and reasons(r) == ["not found"]
    assert reasons(check("[1] 上传", ps)) == ["too short"]


def test_reads_the_formats_models_write_and_keeps_at_most_four():
    ps = ["满分是 4.0，按学分加权平均。第二句话在这里。第三句话在这里。第四句话在这里。第五句话在这里。"]
    assert check("【1†L9-L12】 满分是 4.0", ps).ok
    assert check("- [1]：“满分是 4.0”[1]", ps).kept[0].text == "满分是 4.0，按学分加权平均。"
    r = check("[1] 满分是 4.0\n[1] 第二句话在这里\n[1] 第三句话在这里\n[1] 第四句话在这里\n[1] 第五句话在这里\n[1] 满分是 4.0", ps)
    assert len(r.kept) == 4 and reasons(r) == ["over the limit", "duplicate"]
    assert parse("intro\n[3] 「quoted」 [3]\nnot a quote") == [(3, "quoted")]


def test_a_sentence_that_needs_what_is_around_it_is_dropped():
    renew = Passage("续签\n最早可在到期前约 3 个月提交续签申请。\n如果你没有满足上述任何一项要求：\n"
                    "· 你必须在你学生签证到期前四个月提交续签申请；并且\n· 你必须联系 ISP。", title="续签")
    faq = Passage("补考\n常见问题\n· 不，你必须使用补考申请表进行申请。", title="补考")
    ps = [renew, faq]
    # The deadline without the condition above it tells everyone to apply four months ahead.
    r = check("[1] 最早可在到期前约 3 个月提交续签申请\n[1] 你必须在你学生签证到期前四个月提交续签申请", ps)
    assert [q.text for q in r.kept] == ["最早可在到期前约 3 个月提交续签申请。"] and reasons(r) == ["needs context"]
    assert check("[1] 你必须联系 ISP", ps).status == "fragment"                      # list item under a condition
    assert reasons(check("[1] 你必须联系 ISP", ps)) == ["list item"]
    assert check("[2] 你必须使用补考申请表进行申请", ps).status == "fragment"         # "不，" answers a hidden question
    assert check("[1] 如果你没有满足上述任何一项要求", ps).status == "fragment"


def test_english_sentences_that_lean_on_others():
    p = Passage("Eligibility\nYou can apply for special consideration online. This must be done within "
                "two working days. You need all of the following:\n- a medical certificate\n- the form", title="Eligibility")
    assert check("[1] You can apply for special consideration online", [p]).ok
    assert reasons(check("[1] This must be done within two working days", [p])) == ["needs context"]
    assert reasons(check("[1] You need all of the following", [p])) == ["needs context"]
    assert reasons(check("[1] a medical certificate", [p])) == ["list item"]
    # "Items" and "Some" don't start with "It" or "So" as words.
    q = Passage("Items are returned within a week. Some units have no exam.")
    assert len(check("[1] Items are returned within a week\n[1] Some units have no exam", [q]).kept) == 2


def test_an_answer_may_open_with_yes_or_no_after_its_question():
    pause = Passage("可以休学吗\n答：可以，这叫 intermission（休学）。", title="可以休学吗", qa=True)
    assert check("[1] 可以，这叫 intermission（休学）", [pause]).kept[0].text == "可以，这叫 intermission（休学）。"
    plain = Passage("可以休学吗\n答：可以，这叫 intermission（休学）。", title="可以休学吗")
    assert check("[1] 可以，这叫 intermission（休学）", [plain]).status == "fragment"


def test_a_question_a_table_row_or_a_past_year_is_dropped():
    exchange = Passage("交换\n多数项目按一学期规划\n最后一学期可以交换吗？", title="交换", soft_breaks=True)
    assert reasons(check("[1] 多数项目按一学期规划", [exchange])) == ["a question"]
    finals = Passage("期末考核日期\n10 月入学 | OCT-MY-01 | 2025年1月6日\n期末考核期一般在每学期末。\n自 2022 年起改为线上考试。\n"
                     "2027 年起考试周提前一周。\n2025 年 3 月 1 日起实行新规，过渡期到 2026 年 12 月 31 日。", title="期末考核日期")
    assert reasons(check("[1] 10 月入学 | OCT-MY-01 | 2025年1月6日", [finals], R2026)) == ["table row"]
    assert reasons(check("[1] 自 2022 年起改为线上考试", [finals], R2026)) == ["past year"]
    assert check("[1] 2027 年起考试周提前一周", [finals], R2026).ok
    assert check("[1] 期末考核期一般在每学期末", [finals], R2026).ok
    assert check("[1] 2025 年 3 月 1 日起实行新规，过渡期到 2026 年 12 月 31 日", [finals], R2026).ok
    assert check("[1] 自 2022 年起改为线上考试", [finals], Rules(current_year=0)).ok


def test_line_breaks_end_a_sentence_unless_the_passage_has_soft_breaks():
    art = Passage("交换\n多数项目按一学期\n算。一学期通常对应\n18–24\n个\nMonash\n学分。\n下一段", title="交换", soft_breaks=True)
    assert check("[1] 一学期通常对应", [art]).kept[0].text == "一学期通常对应18–24个Monash学分。"
    assert check("[1] 多数项目按一学期", [art]).kept[0].text == "多数项目按一学期算。"
    page = Passage("Heading\nA line that is its own paragraph\nNext line")
    assert check("[1] A line that is its own paragraph", [page]).kept[0].text == "A line that is its own paragraph"
    # A checklist mark ends a sentence too.
    marks = Passage("清单\n✓ 最早可提前约 3 个月提交续签\n✓ Coursework：WAM 至少 50", title="清单", soft_breaks=True)
    assert check("[1] 最早可提前约 3 个月提交续签", [marks]).kept[0].text == "最早可提前约 3 个月提交续签"


def test_a_latin_full_stop_inside_a_number_or_word_does_not_end_a_sentence():
    p = Passage("The pass mark is 50.0 in every unit. See monash.edu for details.")
    assert check("[1] The pass mark is 50.0", [p]).kept[0].text == "The pass mark is 50.0 in every unit."
    assert sentence("See monash", p) == (37, 64)


def test_unsure_and_uncited_replies():
    ps = ["第 1 段资料的原文。"]
    assert check("签证可以在网上续签。", ps).status == "uncited"
    assert check("这个我不确定。", ps).status == "unsure"
    assert check("I'm not sure.", ps).status == "unsure"
    assert check("", ps).status == "unsure"


def test_custom_checks_run_last():
    def retired(sentence, passage):
        return "retired service" if "Ask Mira" in sentence else None
    p = Passage("通过 Ask Mira 联系学位课程顾问。学位课程顾问可以帮你规划选课。")
    rules = Rules(checks=[retired])
    assert reasons(check("[1] 通过 Ask Mira 联系学位课程顾问", [p], rules)) == ["retired service"]
    assert check("[1] 学位课程顾问可以帮你规划选课", [p], rules).ok


def test_result_types():
    r = check("[1] 第 1 段资料的原文", ["第 1 段资料的原文。"])
    assert r.kept == [Quote(1, "第 1 段资料的原文。", 0, 11)] and r.dropped == []
    assert isinstance(check("[1] 没有这句", ["第 1 段资料的原文。"]).dropped[0], Dropped)


@pytest.mark.parametrize("prompt", [EN, ZH])
def test_prompts_ask_for_the_format_check_reads(prompt):
    assert "[" in prompt and "]" in prompt
    msg = user_message("When?", ["a" * 1000, "b"])
    assert "[1] " + "a" * 600 + "\n" in msg and "a" * 601 not in msg and "[2] b" in msg


def test_the_readme_example():
    passages = [
        Passage("Special consideration\nApply online within two working days of the due date. "
                "This must include supporting documents.", title="Special consideration"),
        Passage("Exams\nFinal exams run in weeks 13 and 14."),
    ]
    result = check("[1] Apply online within two working days\n[1] This must include supporting documents", passages)
    assert result.status == "ok"
    assert result.kept == [Quote(1, "Apply online within two working days of the due date.", 22, 75)]
    assert result.dropped == [Dropped(1, "This must include supporting documents.", "needs context")]


def test_the_chinese_readme_example():
    passages = [Passage("特殊考虑\n截止日期后两个工作日内在网上申请。此流程需要附上证明材料。", title="特殊考虑"),
                Passage("考试\n期末考试在第 13 和 14 周。")]
    result = check("[1] 截止日期后两个工作日内在网上申请\n[1] 此流程需要附上证明材料", passages)
    assert result.kept == [Quote(1, "截止日期后两个工作日内在网上申请。", 5, 22)]
    assert result.dropped == [Dropped(1, "此流程需要附上证明材料。", "needs context")]
