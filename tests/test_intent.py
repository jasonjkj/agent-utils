"""test_intent.py — 词表机械意图匹配（含重叠词正反用例）。

重叠词的处理口径（词表由调用方维护，本文件只测机制语义）：
  「找真人照片」→ 真人素材；「找照片」→ 旅行；裸「真人」→ 交回主模型；含「视频」→ 不落图类。
词表在这里以测试夹具形式各建一份，验证 match_intent 的匹配 / 排除语义。
"""
from agent_utils.intent import match_intent

# 旅行类词表夹具
TRAVEL_RULES = [
    {"id": "album", "action": "album",
     "keywords": ["相册", "之前去过", "翻相册", "走过", "找照片"],
     "exclude": ["真人", "模特"]},
    {"id": "portrait", "action": "portrait",
     "keywords": ["肖像", "官宣", "定妆"]},
    # selfie 规则 exclude「真人」：真人自拍已砍（spec A1），「拍真人/生成真人」不交 CG（G3）
    {"id": "selfie_phrase", "action": "selfie",
     "keywords": ["自拍", "CG", "生成"], "exclude": ["视频", "真人"]},
    {"id": "selfie_naked", "action": "selfie", "match": "exact",
     "keywords": ["拍", "看看", "好"], "exclude": ["视频", "真人"]},
    {"id": "selfie_prefix", "action": "selfie", "match": "prefix",
     "keywords": ["拍"], "exclude": ["视频", "真人"]},
]

# 真人素材类词表夹具
REALPHOTO_RULES = [
    {"id": "pool", "action": "send_asset", "keywords": ["素材库"]},
    {"id": "model", "action": "grab_model", "keywords": ["模特", "模特图"]},
    {"id": "asset", "action": "send_asset",
     "keywords": ["真人照片", "真人视频", "我的照片"], "exclude": ["拍", "生成"]},
]


class TestMechanics:
    def test_empty_inputs(self):
        assert match_intent("", TRAVEL_RULES) is None
        assert match_intent(None, TRAVEL_RULES) is None
        assert match_intent("自拍", []) is None
        assert match_intent("自拍", None) is None

    def test_first_match_wins(self):
        rules = [{"id": "a", "keywords": ["照片"]},
                 {"id": "b", "keywords": ["照片"]}]
        assert match_intent("照片", rules)["id"] == "a"

    def test_rule_without_keywords_skipped(self):
        rules = [{"id": "bad"}, {"id": "ok", "keywords": ["模特"]}]
        assert match_intent("模特图来一张", rules)["id"] == "ok"

    def test_exclude_blocks(self):
        rules = [{"id": "s", "keywords": ["生成"], "exclude": ["视频"]}]
        assert match_intent("生成视频", rules) is None

    def test_exact_and_prefix(self):
        rules_exact = [{"id": "e", "match": "exact", "keywords": ["拍"]}]
        assert match_intent("拍", rules_exact)["id"] == "e"
        assert match_intent("  拍  ", rules_exact)["id"] == "e"      # strip 后全等
        assert match_intent("拍一张", rules_exact) is None             # 长句不命中 exact
        rules_prefix = [{"id": "p", "match": "prefix", "keywords": ["拍"]}]
        assert match_intent("拍一张", rules_prefix)["id"] == "p"
        assert match_intent("来拍一张", rules_prefix) is None          # 非开头不命中


class TestOverlapRulings:
    """spec §9 验收点 5：重叠词分流正确（无重复触发 / 漏触），正反双面。"""

    def test_find_real_photo_goes_realphoto(self):
        # 「找真人照片」→ realphoto；旅行相册规则被 exclude「真人」挡住
        assert match_intent("找真人照片", REALPHOTO_RULES)["action"] == "send_asset"
        assert match_intent("找真人照片", TRAVEL_RULES) is None

    def test_find_photo_goes_travel_album(self):
        # 「找照片」→ 旅行相册
        assert match_intent("找照片", TRAVEL_RULES)["action"] == "album"
        assert match_intent("去找照片看看", TRAVEL_RULES)["action"] == "album"

    def test_naked_real_returns_none_both_domains(self):
        # 裸「真人」/「拍真人」/「生成真人」→ 无对应图类，两域都不命中（交回主模型）
        for text in ("真人", "拍真人", "生成真人"):
            assert match_intent(text, REALPHOTO_RULES) is None, text
            assert match_intent(text, TRAVEL_RULES) is None, text

    def test_video_never_lands_on_image_intents(self):
        # 含「视频」的拍/生成 → 不落图类（走视频链路，交回主模型）
        for text in ("拍个视频", "生成视频", "拍视频"):
            assert match_intent(text, TRAVEL_RULES) is None, text
        # 「拍真人视频」→ realphoto asset 也被 exclude「拍」挡住 → 交回主模型
        assert match_intent("拍真人视频", REALPHOTO_RULES) is None
        # 但「真人视频」直发词（无动作）→ realphoto 素材直发
        assert match_intent("来段真人视频", REALPHOTO_RULES)["action"] == "send_asset"

    def test_model_words_hit_grab(self):
        assert match_intent("模特", REALPHOTO_RULES)["action"] == "grab_model"
        assert match_intent("来张模特图", REALPHOTO_RULES)["action"] == "grab_model"
        # 「模特」不归旅行相册（exclude）
        assert match_intent("找模特照片", TRAVEL_RULES) is None

    def test_pool_first_and_action_exclude(self):
        # 素材库最先判
        assert match_intent("找几张素材库的视频", REALPHOTO_RULES)["action"] == "send_asset"
        # 带动作词的真人照片 = 生成意图（已砍）→ 不命中直发
        assert match_intent("拍一张真人照片", REALPHOTO_RULES) is None

    def test_selfie_hits_travel_cg(self):
        for text in ("自拍", "拍", "拍一张", "生成照片", "CG照片", "看看", "好"):
            r = match_intent(text, TRAVEL_RULES)
            assert r is not None and r["action"] == "selfie", text

    def test_non_image_text_passes(self):
        for text in ("今天天气怎么样", "你在想什么", "打球去吗"):
            assert match_intent(text, TRAVEL_RULES) is None, text
            assert match_intent(text, REALPHOTO_RULES) is None, text
