import json
import random

# A long base text about History of the Internet (approx 800 chars)
BASE_TEXT = """
互联网（Internet）的诞生彻底改变了人类社会的运作方式。它的起源可以追溯到 20 世纪 60 年代，当时正值冷战高峰期，美国国防部高级研究计划局（ARPA）为了建立一个能够抵御核打击的通信网络，启动了 ARPANET 项目。1969 年，ARPANET 实现了加州大学洛杉矶分校（UCLA）和斯坦福研究院（SRI）之间的第一次数据传输，标志着互联网雏形的诞生。
20 世纪 70 年代，TCP/IP 协议的制定为不同网络之间的互联奠定了基础。1983 年，ARPANET 正式切换到 TCP/IP 协议，现代互联网由此诞生。随后，蒂姆·伯纳斯-李（Tim Berners-Lee）在 1989 年发明了万维网（World Wide Web），通过超文本链接将信息组织起来，使得非技术人员也能轻松访问网络资源。1993 年，Mosaic 浏览器的发布进一步推动了互联网的普及。
进入 21 世纪，互联网经历了从 Web 1.0（只读）到 Web 2.0（互动）的转变。社交媒体（如 Facebook、Twitter、微信）的兴起让每个人都成为了信息的发布者。移动互联网的爆发更是将网络延伸到了我们口袋里的智能手机上，随时随地连接世界成为现实。如今，我们正站在 Web 3.0 的门槛上，区块链、去中心化和元宇宙等概念正在重塑我们对数字未来的想象。
互联网的影响是全方位的。在经济领域，电子商务（如 Amazon、Alibaba）颠覆了传统零售业；在教育领域，在线课程（MOOCs）让知识获取变得更加公平；在政治领域，网络成为了公众表达意见和参与公共事务的重要平台。然而，互联网也带来了假新闻、网络霸凌、隐私泄露和数字鸿沟等问题。
展望未来，随着 5G、物联网（IoT）和人工智能（AI）的融合，万物互联（IoE）的时代即将到来。互联网将不再仅仅是连接人与人，而是连接人、机、物、环境的庞大生态系统。在这个数字化生存的新时代，如何平衡技术进步与人文关怀，构建一个安全、开放、包容的网络空间，是我们共同面临的挑战。
"""

def get_long_text(min_chars=3000):
    """Generates text longer than min_chars by repeating and shuffling base text."""
    text = BASE_TEXT.strip()
    while len(text) < min_chars:
        text += "\n\n" + BASE_TEXT.strip()
    return text

long_context = get_long_text()

test_cases = [
    {
        "id": "case_01_summarize",
        "messages": [
            {"role": "system", "content": "你是一个历史学家。请用 3 个关键时间点总结互联网的发展历程。"},
            {"role": "user", "content": f"请总结这段关于互联网历史的文本：\n\n{long_context}"}
        ]
    },
    {
        "id": "case_02_json_extraction",
        "messages": [
            {"role": "system", "content": "请提取文本中提到的所有技术协议、项目名称和软件，并以 JSON 列表格式输出。"},
            {"role": "user", "content": f"分析这段文本并提取技术实体：\n\n{long_context}"}
        ]
    },
    {
        "id": "case_03_translation",
        "messages": [
            {"role": "system", "content": "请将以下文本的第二段翻译成法文。"},
            {"role": "user", "content": f"文本：\n\n{long_context}"}
        ]
    },
    {
        "id": "case_04_impact_analysis",
        "messages": [
            {"role": "system", "content": "请分析互联网对现代社会的负面影响，并给出具体的例子。"},
            {"role": "user", "content": f"基于文本分析：\n\n{long_context}"}
        ]
    },
    {
        "id": "case_05_quiz_generation",
        "messages": [
            {"role": "system", "content": "请根据文本内容设计 5 道单项选择题，每题包含 4 个选项和正确答案。"},
            {"role": "user", "content": f"文本：\n\n{long_context}"}
        ]
    },
    {
        "id": "case_06_rewrite_cyberpunk",
        "messages": [
            {"role": "system", "content": "请用赛博朋克（Cyberpunk）的风格改写这段文本，强调高科技与低生活的反差。"},
            {"role": "user", "content": f"文本：\n\n{long_context}"}
        ]
    },
    {
        "id": "case_07_concept_explanation",
        "messages": [
            {"role": "system", "content": "请向一位 80 岁的老人解释什么是“Web 3.0”和“元宇宙”，使用通俗的比喻。"},
            {"role": "user", "content": f"参考文本：\n\n{long_context}"}
        ]
    },
    {
        "id": "case_08_headline_clickbait",
        "messages": [
            {"role": "system", "content": "请为这篇文章生成 5 个“标题党”风格的标题，旨在吸引最大点击量。"},
            {"role": "user", "content": f"文章：\n\n{long_context}"}
        ]
    },
    {
        "id": "case_09_timeline_table",
        "messages": [
            {"role": "system", "content": "请将文本中的关键事件整理成一个 Markdown 表格，包含年份、事件和意义三列。"},
            {"role": "user", "content": f"文本：\n\n{long_context}"}
        ]
    },
    {
        "id": "case_10_debate_script",
        "messages": [
            {"role": "system", "content": "请撰写一段辩论赛的开篇陈词，辩题是“互联网让世界变得更好了吗？”，你持反方观点。"},
            {"role": "user", "content": f"基于文本论据：\n\n{long_context}"}
        ]
    },
    {
        "id": "case_11_tech_evolution",
        "messages": [
            {"role": "system", "content": "请描述从 Web 1.0 到 Web 3.0 的演变逻辑，重点分析用户角色的变化。"},
            {"role": "user", "content": f"文本：\n\n{long_context}"}
        ]
    },
    {
        "id": "case_12_future_prediction",
        "messages": [
            {"role": "system", "content": "基于文本最后一段，预测 2050 年的互联网形态，写一段科幻微小说。"},
            {"role": "user", "content": f"文本：\n\n{long_context}"}
        ]
    },
    {
        "id": "case_13_entity_classification",
        "messages": [
            {"role": "system", "content": "请将文本中的实体分类为：人物、组织、技术、概念。以 JSON 对象格式输出。"},
            {"role": "user", "content": f"文本：\n\n{long_context}"}
        ]
    },
    {
        "id": "case_14_code_generation",
        "messages": [
            {"role": "system", "content": "请写一个 Python 类 `InternetHistory`，包含文本中提到的关键里程碑作为属性。"},
            {"role": "user", "content": f"参考文本：\n\n{long_context}"}
        ]
    },
    {
        "id": "case_15_comparative_analysis",
        "messages": [
            {"role": "system", "content": "请比较 ARPANET 和现代互联网的区别，从目的、规模和技术三个维度进行分析。"},
            {"role": "user", "content": f"文本：\n\n{long_context}"}
        ]
    },
    {
        "id": "case_16_keyword_extraction_weighted",
        "messages": [
            {"role": "system", "content": "请提取 20 个关键词，并根据其在互联网发展史上的重要性打分（1-10 分），输出 CSV 格式。"},
            {"role": "user", "content": f"文本：\n\n{long_context}"}
        ]
    },
    {
        "id": "case_17_tweet_thread",
        "messages": [
            {"role": "system", "content": "请将这段历史改写成一个由 5 条推文组成的 Twitter Thread，每条推文不超过 280 字符。"},
            {"role": "user", "content": f"文本：\n\n{long_context}"}
        ]
    },
    {
        "id": "case_18_swot_analysis",
        "messages": [
            {"role": "system", "content": "请对“万物互联（IoE）”进行 SWOT 分析（优势、劣势、机会、威胁）。"},
            {"role": "user", "content": f"基于文本内容：\n\n{long_context}"}
        ]
    },
    {
        "id": "case_19_eli5",
        "messages": [
            {"role": "system", "content": "请像给 5 岁孩子讲故事一样，解释互联网是如何诞生的。"},
            {"role": "user", "content": f"文本：\n\n{long_context}"}
        ]
    },
    {
        "id": "case_20_philosophical_reflection",
        "messages": [
            {"role": "system", "content": "请从哲学的角度思考：互联网是否改变了人类的本质？请写一篇 300 字的短文。"},
            {"role": "user", "content": f"文本：\n\n{long_context}"}
        ]
    }
]

output_file = "benchmark_test_cases.json"
with open(output_file, "w", encoding='utf-8') as f:
    json.dump(test_cases, f, indent=2, ensure_ascii=False)

print(f"Generated {len(test_cases)} test cases in {output_file}. Each input is approx {len(long_context)} characters.")
