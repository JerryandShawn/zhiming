"""Synthetic lexical classification and topic CPU/allocation observations; B is never opened."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mingjing_core.organize.contracts import Message  # noqa: E402
from mingjing_core.organize.v2.classifier import LocalClassifier  # noqa: E402
from mingjing_core.organize.v2.scoped import OrganizeScope  # noqa: E402
from mingjing_core.organize.v2.topics import cluster_messages  # noqa: E402
from mingjing_core.timekit.clock import SystemClock  # noqa: E402
from tools.mod_week.performance import measure, write_report  # noqa: E402

TEXTS = (
    "明天参加求职面试，准备项目经历和简历",
    "今晚散步回家做饭，周末再看一场电影",
    "和伴侣沟通异地恋的见面安排",
    "父母养老照护需要兄妹一起商量",
    "最近失眠和肩颈疼，想先整理健康作息",
    "比较房贷利率与提前还款成本",
    "学习八字十神含义以及紫微三方四正概念",
    "我还没有组织好想聊什么",
)


def classification_workload() -> int:
    engine = LocalClassifier()
    for index in range(1000):
        prediction = engine.classify(TEXTS[index % len(TEXTS)])
        assert prediction.waiting == (prediction.area_id is None)
    return 1000


def topic_workload() -> int:
    scope, engine = OrganizeScope("synthetic", "self", "thread"), LocalClassifier()
    messages = [
        Message(
            f"m{index}",
            "user",
            TEXTS[index % len(TEXTS)],
            index,
            "synthetic",
            "self",
            thread_id="thread",
        )
        for index in range(100)
    ]
    predictions = {message.id: engine.classify(message.content) for message in messages}
    topics = cluster_messages(messages, predictions, scope=scope)
    covered = [ident for topic in topics for ident in topic.message_ids]
    assert len(covered) == len(set(covered)) == len(messages)
    return len(messages)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cases = [
        measure("organize_v2_classify_1000", classification_workload),
        measure("organize_v2_topics_100", topic_workload),
    ]
    sources = [*Path("mingjing_core/organize/v2").glob("*.py"), Path(__file__)]
    write_report(args.output, cases, sources, clock=SystemClock())
    for result in cases:
        print(result["name"], "median_seconds", result["median_seconds"])


if __name__ == "__main__":
    main()
