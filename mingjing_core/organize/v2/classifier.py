"""Selective local classification with bounded contextual continuity and explicit abstention."""

import re
from collections.abc import Iterable, Mapping

from .contracts import ClassificationContext, ClassifierSettings, Prediction
from .lexicons import LEXICONS
from .ngrams import char_ngrams, cosine, normalize

_SWITCH = re.compile(
    r"换个话题|换一件事|另起|先不(?:聊|说)|不(?:接着|继续|聊|谈).{0,8}(?:刚才|前面|那件)|换个方向|另外[，,]"
)
_UNCERTAIN = re.compile(
    r"说不上|没(?:有)?想好|不知道(?:聊|说|从哪)|没组织好|没(?:有)?具体.{0,4}(?:问题|事)|"
    r"随便聊|打个招呼|来坐一会|先停一下|先告一段落|只是路过|道声晚安"
)
_FOCUS = re.compile(
    r"这次重点(?:是|想)|当前主要|现在主要|重点是|先比较|先聊|先谈|主要想|现在关心|问题在于|"
    r"我想谈的是|核心问题是|我自己也|我自己现在|我自己最近|而是|只想|只核算|先算清|主要比较|主要想|主要讨论"
)
_CARE = re.compile(r"陪护|陪诊|照护|照顾|轮流|住院安排|家人.{0,10}(?:医院|手术)")
_FAMILY_PERSON = re.compile(
    r"父母|爸妈|我妈|我爸|妈妈|爸爸|父亲|母亲|老人|奶奶|爷爷|外婆|外公|家人|孩子|婆媳|婆婆|祖母|祖父|亲属|子女"
)
_LEARNING = re.compile(
    r"学习|学会|学懂|研习|概念|区别|原理|术语|含义|解释|牌义|怎么理解|怎么看|排盘|命盘解读|象征|口径|流派|依据"
)
_DIVINATION = re.compile(r"塔罗|抽牌|占卜|算一卦|命盘|八字")
_CONTINUATION = re.compile(
    r"这件事|刚才|前一步|第二[个条步]|按你说|照这个|继续|那一步|上面|再具体|这次在意|接下来|不急着|关于"
)
_AREA_LABELS = {
    "daily": ("日常生活", "普通日常", "生活小事", "日常"),
    "career": ("事业学业",),
    "relationships": ("感情人际",),
    "family": ("家庭",),
    "wellbeing": ("身心",),
    "finance": ("财务",),
    "metaphysics": ("命理研习",),
}
_DISMISSED = re.compile(
    r"先放(?:在)?(?:一边|旁边)|先不(?:聊|谈|算)|不是(?:在)?(?:谈|讨论|研究)|不讨论|不研究|不是怕|不是要"
)
_NO_PRIMARY = re.compile(r"只是报流水账|没有主要话题|暂时不分主次|几件事混在一起")


def _context(
    value: ClassificationContext | Mapping | None,
) -> ClassificationContext | None:
    if value is None or isinstance(value, ClassificationContext):
        return value
    if not isinstance(value, Mapping):
        raise ValueError("整理上下文无效")
    try:
        return ClassificationContext(**value)
    except TypeError:
        raise ValueError("整理上下文无效") from None


class LocalClassifier:
    def __init__(self, settings: ClassifierSettings | None = None) -> None:
        self.settings = ClassifierSettings() if settings is None else settings
        if not isinstance(self.settings, ClassifierSettings):
            raise ValueError("整理分类配置无效")
        self._prototypes = {area: char_ngrams(" ".join(words)) for area, words in LEXICONS.items()}

    def classify(self, text: str, context: ClassificationContext | Mapping | None = None) -> Prediction:
        if type(text) is not str:
            raise ValueError("待整理正文必须是文本")
        context = _context(context)
        original = normalize(text).strip()
        folded = "，".join(clause for clause in re.split(r"[，,。；;]", original) if not _DISMISSED.search(clause))
        scores = self._scores(folded)
        markers = tuple(_FOCUS.finditer(folded))
        focused = folded[markers[-1].start() :] if markers else folded
        if focused != folded and focused.strip():
            focus_scores = self._scores(focused)
            scores = {area: score * 0.30 + focus_scores[area] * 1.50 for area, score in scores.items()}
        _semantic_prior(focused if focused != folded else folded, scores)
        if _NO_PRIMARY.search(folded):
            return Prediction(None, 0, scores, "unprioritized_areas")
        if _UNCERTAIN.search(folded) and max(scores.values(), default=0) < self.settings.minimum_evidence:
            return Prediction(None, 0, scores, "uncertain_content")
        inherited = self._smooth(folded, scores, context)
        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        (first, top), (second, runner) = ranked[:2]
        confidence = top / (top + runner + 0.65) if top else 0
        threshold = self.settings
        if (
            top < threshold.minimum_evidence
            or confidence < threshold.minimum_confidence
            or top - runner < threshold.minimum_margin
        ):
            reason = "low_evidence" if top < threshold.minimum_evidence else "ambiguous_areas"
            return Prediction(None, confidence, scores, reason)
        secondary = second if runner >= 2 and runner >= top * 0.4 else None
        return Prediction(
            first,
            confidence,
            scores,
            "context_continuation" if inherited else "lexical_ngram",
            secondary,
        )

    def _scores(self, text: str) -> dict[str, float]:
        vector = char_ngrams(text)
        scores = {}
        for area, words in LEXICONS.items():
            matches = [(word, weight) for word, weight in words.items() if _contains(text, word)]
            # A long lexical phrase subsumes its shorter fragments; repeating it is not more evidence.
            lexical = sum(
                weight for word, weight in matches if not any(word != other and word in other for other, _ in matches)
            )
            scores[area] = lexical + self.settings.ngram_weight * cosine(vector, self._prototypes[area])
        return scores

    def _smooth(self, text: str, scores: dict[str, float], context: ClassificationContext | None) -> bool:
        if context is None or not context.topic_active or context.previous_area_id is None or _SWITCH.search(text):
            return False
        if context.previous_confidence < self.settings.minimum_confidence or not text:
            return False
        previous = context.previous_area_id
        first = max(scores, key=scores.get)
        if (
            first != previous
            and scores[first] >= self.settings.minimum_evidence
            and scores[previous] < scores[first] * 0.35
        ):
            return False
        recent = (
            *context.recent_texts[-3:],
            *((context.previous_text,) if context.previous_text else ()),
        )
        similarity = max((cosine(char_ngrams(text), char_ngrams(item)) for item in recent), default=0)
        if not _CONTINUATION.search(text) and similarity < 0.13 and len(text) > 12:
            return False
        support = max(2.05, context.previous_confidence * 2.8) * self.settings.context_weight
        scores[previous] += support + min(similarity, 0.5)
        return True


def _contains(text: str, word: str) -> bool:
    if word.isascii():
        return re.search(r"(?<![a-z0-9_])" + re.escape(word) + r"(?![a-z0-9_])", text) is not None
    return word in text


def _semantic_prior(text: str, scores: dict[str, float]) -> None:
    for area, labels in _AREA_LABELS.items():
        for label in labels:
            marker = re.search(
                r"(?:聊聊|想聊|归入|放到|这条是|这是|记个|记录一件)[^，,。；;]{0,8}" + label,
                text,
            )
            if marker and not re.search(r"别|不要|不用", text[max(0, marker.start() - 3) : marker.start()]):
                scores[area] += 3.5
                break
    nonfamily = re.search(r"恋爱|恋人|男友|女友|朋友|同事|室友", text)
    if _FAMILY_PERSON.search(text) and not nonfamily and scores["family"] >= 1.7 and scores["relationships"] >= 0.8:
        scores["family"] += 1.8
        scores["relationships"] *= 0.5
    if re.search(r"核算|算清|计算|比较.{0,4}成本", text) and scores["finance"] >= 1.65:
        scores["finance"] += 2.2
        scores["family"] *= 0.5
    if _FAMILY_PERSON.search(text) and _CARE.search(text):
        scores["family"] += 2.3
        scores["wellbeing"] *= 0.65
    if _DIVINATION.search(text) and not _LEARNING.search(text):
        worldly = max(
            (value for area, value in scores.items() if area != "metaphysics"),
            default=0,
        )
        if worldly >= 1.7:
            scores["metaphysics"] *= 0.30


_DEFAULT = LocalClassifier()


def classify(text: str, context: ClassificationContext | Mapping | None = None) -> Prediction:
    return _DEFAULT.classify(text, context)


def classify_batch(
    texts: Iterable[str], context: ClassificationContext | Mapping | None = None
) -> tuple[Prediction, ...]:
    previous = _context(context)
    results = []
    recent = ()
    for text in texts:
        prediction = classify(text, previous)
        results.append(prediction)
        recent = (*recent[-2:], text)
        previous = (
            ClassificationContext(prediction.area_id, prediction.confidence, recent_texts=recent)
            if not prediction.waiting
            else None
        )
    return tuple(results)
