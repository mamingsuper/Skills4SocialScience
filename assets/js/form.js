/**
 * Multi-type submission helper for Skills4SocialScience.
 * Static site pages cannot write directly to the repo, so we open a prefilled GitHub issue.
 */

const TARGET_REPO = "mamingsuper/Skills4SocialScience";

document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("submission-form");
    if (!form) {
        return;
    }

    const entryTypeInput = document.getElementById("entry-type");
    switchType((entryTypeInput && entryTypeInput.value) || "skill");

    form.querySelectorAll("input, select, textarea").forEach((field) => {
        field.addEventListener("input", updatePreview);
        field.addEventListener("change", updatePreview);
    });

    updatePreview();
});

function switchType(type) {
    const normalizedType = ["skill", "paper", "resource"].includes(type) ? type : "skill";
    const entryTypeInput = document.getElementById("entry-type");
    if (entryTypeInput) {
        entryTypeInput.value = normalizedType;
    }

    document.querySelectorAll(".type-option").forEach((option) => {
        option.classList.toggle("active", option.dataset.entryType === normalizedType);
    });

    ["skill", "paper", "resource"].forEach((candidate) => {
        const section = document.getElementById(`fields-${candidate}`);
        if (section) {
            section.classList.toggle("active", candidate === normalizedType);
        }
    });

    updatePreview();
}

function getCurrentType() {
    const entryTypeInput = document.getElementById("entry-type");
    return (entryTypeInput && entryTypeInput.value) || "skill";
}

function getInputValue(id, fallback = "") {
    const element = document.getElementById(id);
    if (!element) {
        return fallback;
    }
    return (element.value || "").trim() || fallback;
}

function splitCsv(raw) {
    if (!raw) {
        return [];
    }
    return raw
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
}

function slugify(value, fallback = "new-entry") {
    const slug = (value || "")
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-+|-+$/g, "");
    return slug || fallback;
}

function toYamlList(items) {
    if (!items.length) {
        return "[]";
    }
    const quoted = items.map((item) => `"${item.replace(/"/g, '\\"')}"`);
    return `[${quoted.join(", ")}]`;
}

function yamlQuote(value) {
    return `"${String(value || "").replace(/"/g, '\\"')}"`;
}

function buildSubmissionData() {
    const type = getCurrentType();
    const title = getInputValue("title", "Untitled");
    const description = getInputValue("description", "Please add description.");
    const slug = slugify(title);

    if (type === "paper") {
        return {
            type,
            title,
            slug,
            description,
            year: getInputValue("paper-year", new Date().getFullYear().toString()),
            link: getInputValue("paper-link", "https://example.com"),
            category: getInputValue("paper-category", "general")
        };
    }

    if (type === "resource") {
        return {
            type,
            title,
            slug,
            description,
            resourceType: getInputValue("resource-type", "Dataset"),
            resourceCategory: getInputValue("resource-category", "research-tool"),
            link: getInputValue("resource-link", "https://example.com")
        };
    }

    const tags = splitCsv(getInputValue("skill-tags"));
    const tools = splitCsv(getInputValue("skill-tools", "Claude, Cursor"));
    const workflowStage = getInputValue("skill-stage", "writing");

    return {
        type,
        title,
        slug,
        description,
        workflowStage,
        tools,
        tags
    };
}

function buildSkillMarkdown(data) {
    const sourceFile = `_skills/${data.workflowStage}/${data.slug}/SKILL.md`;

    return `---
layout: skill
name: ${yamlQuote(data.title)}
description: ${yamlQuote(data.description)}
workflow_stage: ${data.workflowStage}
category: ${data.workflowStage}
tags: ${toYamlList(data.tags)}
compatibility: ${toYamlList(data.tools)}
source_file: ${sourceFile}
---
# ${data.title}

Loading the latest \`SKILL.md\` content from the repository source.
`;
}

function buildSkillSourceMarkdown(data) {
    return `# ${data.title}

## Overview

${data.description}

## Purpose

Describe what this skill should help researchers accomplish.

## Instructions

1. Clarify the research question and expected output.
2. Propose a workflow aligned with social science best practices.
3. Provide reusable prompts, templates, or scripts.
4. Add validation checks before final output.
`;
}

function buildPaperMarkdown(data) {
    return `---
layout: paper
title: ${yamlQuote(data.title)}
description: ${yamlQuote(data.description)}
year: ${data.year}
link: ${data.link}
category: ${data.category}
---
# ${data.title}

Add abstract, methods, and key findings here.
`;
}

function buildResourceMarkdown(data) {
    return `---
layout: resource
title: ${yamlQuote(data.title)}
description: ${yamlQuote(data.description)}
type: ${data.resourceType}
category: ${data.resourceCategory}
link: ${data.link}
---
# ${data.title}

Describe why this resource is useful for social science researchers.
`;
}

function buildArtifacts() {
    const data = buildSubmissionData();
    let markdown;
    let proposedPath;
    let label;
    let template;
    let additionalFiles = [];

    if (data.type === "paper") {
        markdown = buildPaperMarkdown(data);
        proposedPath = `_papers/${data.slug}.md`;
        label = "paper-submission";
        template = "paper-submission.yml";
    } else if (data.type === "resource") {
        markdown = buildResourceMarkdown(data);
        proposedPath = `_resources/${data.slug}.md`;
        label = "resource-submission";
        template = "resource-submission.yml";
    } else {
        markdown = buildSkillMarkdown(data);
        proposedPath = `_skills/${data.workflowStage}/${data.slug}/index.md`;
        label = "skill-submission";
        template = "skill-submission.yml";
        additionalFiles = [
            {
                path: `_skills/${data.workflowStage}/${data.slug}/SKILL.md`,
                content: buildSkillSourceMarkdown(data)
            }
        ];
    }

    const issueTitle = `[${data.type.toUpperCase()}] ${data.title}`;
    const issueBody = [
        `## Submission type`,
        `${data.type}`,
        ``,
        `## Proposed file path`,
        `\`${proposedPath}\``,
        ``,
        `## File content`,
        "```markdown",
        markdown.trim(),
        "```",
        "",
        ...additionalFiles.flatMap((file) => [
            `## Additional file`,
            `\`${file.path}\``,
            "```markdown",
            file.content.trim(),
            "```",
            ""
        ]),
        "",
        `## Notes`,
        `- Generated from the website submit form.`,
        `- Please review and commit to \`${proposedPath}\`.`,
        ...additionalFiles.map((file) => `- Also add \`${file.path}\`.`)
    ].join("\n");

    const issueUrl =
        `https://github.com/${TARGET_REPO}/issues/new` +
        `?template=${encodeURIComponent(template)}` +
        `&title=${encodeURIComponent(issueTitle)}` +
        `&body=${encodeURIComponent(issueBody)}` +
        `&labels=${encodeURIComponent(`${label},needs-triage`)}`;

    return { data, markdown, proposedPath, issueUrl };
}

function getSubmitButtonText(type) {
    const isZh = document.documentElement.lang.toLowerCase().startsWith("zh");
    if (!isZh) {
        return `Submit ${type} to GitHub →`;
    }

    const labels = {
        skill: "提交 Skill 到 GitHub →",
        paper: "提交论文到 GitHub →",
        resource: "提交资源到 GitHub →"
    };
    return labels[type] || "提交到 GitHub →";
}

function updatePreview() {
    const preview = document.getElementById("yaml-preview");
    const submitLink = document.getElementById("github-submit-link");

    const { data, markdown, issueUrl } = buildArtifacts();

    if (preview) {
        preview.textContent = markdown;
    }

    if (submitLink) {
        submitLink.href = issueUrl;
        submitLink.textContent = getSubmitButtonText(data.type);
    }
}

async function copyPreview() {
    const preview = document.getElementById("yaml-preview");
    if (!preview) {
        return;
    }

    const text = preview.textContent || "";
    if (!text) {
        return;
    }

    try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            await navigator.clipboard.writeText(text);
            return;
        }
    } catch (error) {
        console.warn("Clipboard API unavailable, falling back:", error);
    }

    const textarea = document.createElement("textarea");
    textarea.value = text;
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand("copy");
    document.body.removeChild(textarea);
}

window.switchType = switchType;
window.updatePreview = updatePreview;
window.copyPreview = copyPreview;
