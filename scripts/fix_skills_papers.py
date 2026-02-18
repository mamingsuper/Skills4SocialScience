#!/usr/bin/env python3
import os, re

# ============================================================
# 1. 删除6个完全不相关的自动采集技能
# ============================================================
to_delete = [
    "_skills/design/lobehub-lobehub.md",
    "_skills/data-analysis/liyupi-ai-guide.md",
    "_skills/data-analysis/adenhq-hive.md",
    "_skills/data-analysis/shareai-lab-learn-claude-code.md",
    "_skills/data-collection/danny-avila-librechat.md",
    "_skills/research-engineering/x1xhlol-system-prompts-and-models-of-ai-tools.md",
]
for f in to_delete:
    if os.path.exists(f):
        os.remove(f)
        print(f"[DELETED] {f}")

# ============================================================
# 2. 自动采集技能（保留的4个）添加 zh_description
# ============================================================
auto_skills_zh = {
    "_skills/research-engineering/affaan-m-everything-claude-code.md":
        "完整的 Claude Code 配置集合，包含 Agent、Hooks、命令与规则，由 Anthropic 黑客松获奖作品总结提炼，适合研究者快速搭建 AI 辅助工作流。",
    "_skills/research-engineering/khoj-ai-khoj.md":
        "Khoj：可自托管的 AI 第二大脑，支持文档问答、网络搜索、自动化任务与深度研究，适合社会科学研究者管理个人知识库。",
    "_skills/research-engineering/travisvn-awesome-claude-skills.md":
        "精选 Claude Skills 资源列表，汇集定制化 Claude 工作流的工具与示例，适合研究者按需配置 AI 辅助研究技能。",
    "_skills/writing/blader-humanizer.md":
        "Claude Code 写作技能：自动去除文本中 AI 生成的机械语调，使学术写作更具自然的人文表达风格。",
}

# ============================================================
# 3. 目录型技能（5个 index.md）添加 zh_description
# ============================================================
dir_skills_zh = {
    "_skills/analysis/ai-research-engineering-skills/index.md":
        "最全面的 AI 研究工程技能库，专为 AI Agent 设计，覆盖文献综述、数据分析、写作等社会科学研究全流程技能。",
    "_skills/analysis/claude-code-stata-guide/index.md":
        "使用 Claude Code 辅助 Stata 经济研究的实践教程，讲解如何通过 AI 编程助手提升计量经济学数据分析效率。",
    "_skills/analysis/stata-accounting-research/index.md":
        "Stata 会计研究 AI 辅助技能指南，涵盖财务数据处理、回归分析与学术论文写作的 AI 增强工作流。",
    "_skills/design/open-science-skills/index.md":
        "开放科学研究技能，涵盖预注册、数据共享、可复现研究流程及开放存取发表等学术规范实践。",
    "_skills/writing/claude-writer/index.md":
        "面向社会科学研究者的 AI 学术写作助手技能，支持 IMRAD 结构论文撰写、引用格式与摘要生成。",
}

# ============================================================
# 4. 论文（6篇）添加 zh_description
# ============================================================
papers_zh = {
    "_papers/argyle-out-of-one-many.md":
        "提出'硅基抽样'方法，证明正确条件化的 LLM 可生成接近真实人类的合成调查数据，发表于《政治分析》2023年。",
    "_papers/bail-generative-ai-social-science.md":
        "系统综述生成式 AI 对社会科学的影响，分析 LLM 在测量、理论构建与因果推断中的机遇与方法论挑战。",
    "_papers/bisbee-synthetic-survey.md":
        "系统评估合成调查回答与真实人类数据的一致性，为使用 LLM 替代大规模问卷调查提供方法论基础。",
    "_papers/grossmann-ai-transformation.md":
        "前瞻性讨论 AI 如何重塑社会科学的研究方法、发表生态与知识生产模式，呼吁学界主动拥抱变革。",
    "_papers/llm-social-science.md":
        "综述大语言模型在社会科学中的多元应用，包括文本分类、情感分析、模拟实验与因果推断方法。",
    "_papers/ziems-llm-css.md":
        "系统评估 LLM 在计算社会科学典型任务上的表现，探讨 AI 对该领域的变革潜力与现实局限性。",
}

def add_zh(path_dict, label):
    added = 0
    for fpath, zh in path_dict.items():
        if not os.path.exists(fpath):
            print(f"[SKIP] {fpath}")
            continue
        text = open(fpath, encoding="utf-8").read()
        if "zh_description:" in text:
            print(f"[ALREADY] {fpath}")
            continue
        safe = zh.replace('"', '\\"')
        updated = re.sub(r'(description:.*\n)', r'\1' + f'zh_description: "{safe}"\n', text, count=1)
        if updated != text:
            open(fpath, "w", encoding="utf-8").write(updated)
            print(f"[ZH ADDED - {label}] {os.path.basename(os.path.dirname(fpath)) if fpath.endswith('index.md') else os.path.basename(fpath)}")
            added += 1
        else:
            print(f"[WARN] no description line: {fpath}")
    return added

a = add_zh(auto_skills_zh, "auto-skill")
b = add_zh(dir_skills_zh, "dir-skill")
c = add_zh(papers_zh, "paper")

print(f"\n[SUMMARY] 新增zh_description: auto-skill={a}, dir-skill={b}, paper={c}")
print("✅ 全部完成")
