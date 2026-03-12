from webinfo2md.pipeline import WebInfo2MDPipeline


def test_merge_and_dedup():
    pipeline = WebInfo2MDPipeline()
    payloads = [
        {
            "source": "page-1",
            "company": "ByteDance",
            "position": "MLE",
            "questions": [
                {
                    "category": "ML理论",
                    "question": "什么是 attention 机制？",
                    "context": "一面",
                    "difficulty": "medium",
                }
            ],
        },
        {
            "source": "page-2",
            "company": "",
            "position": "",
            "questions": [
                {
                    "category": "ML理论",
                    "question": " 什么是 attention 机制？ ",
                    "context": "二面",
                    "difficulty": "medium",
                }
            ],
        },
    ]

    merged = pipeline._merge_and_dedup(payloads)

    assert merged["company"] == "ByteDance"
    assert merged["position"] == "MLE"
    assert len(merged["questions"]) == 1
