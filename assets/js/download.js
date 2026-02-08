/**
 * Download and source sync helpers for Skills4SocialScience
 */

const GITHUB_REPO = "mamingsuper/Skills4SocialScience";
const GITHUB_BRANCH = "main";

function getBaseUrl() {
    if (typeof window.siteBaseurl !== "undefined") {
        return window.siteBaseurl;
    }

    const currentPath = window.location.pathname;
    const marker = "/Skills4SocialScience";
    if (currentPath.includes(marker)) {
        return marker;
    }

    return "";
}

function normalizeRepoPath(path) {
    return (path || "").replace(/^\/+/, "").trim();
}

async function fetchFileContent(path) {
    const normalizedPath = normalizeRepoPath(path);
    if (!normalizedPath) {
        throw new Error("Missing source file path");
    }

    const baseUrl = getBaseUrl();

    // First try the current site host (works after GitHub Pages build).
    try {
        const localUrl = `${baseUrl}/${normalizedPath}`;
        const localResponse = await fetch(localUrl);
        if (localResponse.ok) {
            const localContent = await localResponse.text();
            if (!/^\s*<!DOCTYPE html>/i.test(localContent) && !/^\s*<html/i.test(localContent)) {
                return localContent;
            }
        }
    } catch (error) {
        console.warn("Local fetch failed, falling back to GitHub raw:", error);
    }

    // Fallback to GitHub raw.
    const githubUrl = `https://raw.githubusercontent.com/${GITHUB_REPO}/${GITHUB_BRANCH}/${normalizedPath}`;
    const githubResponse = await fetch(githubUrl);
    if (!githubResponse.ok) {
        throw new Error(`Failed to fetch ${normalizedPath}: ${githubResponse.statusText}`);
    }
    return await githubResponse.text();
}

function inferSkillSourcePath() {
    if (window.skillSourceFile) {
        return normalizeRepoPath(window.skillSourceFile);
    }

    const section = document.getElementById("skill-source-section");
    if (section && section.dataset.sourceFile) {
        return normalizeRepoPath(section.dataset.sourceFile);
    }

    // Fallback: infer from /skills/<slug>/ to _skills/<slug>.md
    const baseUrl = getBaseUrl();
    let path = window.location.pathname;
    if (baseUrl && path.startsWith(baseUrl)) {
        path = path.slice(baseUrl.length);
    }

    const slug = path
        .replace(/^\/+|\/+$/g, "")
        .split("/")
        .filter(Boolean)
        .slice(1) // drop "skills"
        .join("/");

    if (!slug) {
        return "";
    }

    return `_skills/${slug}/SKILL.md`;
}

async function renderSkillSourceContent() {
    const section = document.getElementById("skill-source-section");
    const sourceCode = document.getElementById("skill-source-content");
    if (!section || !sourceCode) {
        return;
    }

    const sourcePath = inferSkillSourcePath();
    if (!sourcePath) {
        return;
    }

    try {
        const content = await fetchFileContent(sourcePath);
        sourceCode.textContent = content;
        section.hidden = false;

        const fallback = document.getElementById("skill-fallback-content");
        if (fallback) {
            fallback.hidden = true;
        }
    } catch (error) {
        console.error("Failed to load skill source content:", error);
    }
}

async function downloadSkillFile() {
    const button = document.getElementById("download-skill-btn");
    if (!button) {
        return;
    }

    const originalText = button.textContent;
    button.disabled = true;
    button.textContent = "Downloading...";

    try {
        const sourcePath = inferSkillSourcePath();
        if (!sourcePath) {
            throw new Error("Cannot determine skill source path");
        }

        const content = await fetchFileContent(sourcePath);
        const filename = sourcePath.split("/").pop() || "SKILL.md";

        const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
        const downloadUrl = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = downloadUrl;
        anchor.download = filename;
        document.body.appendChild(anchor);
        anchor.click();
        document.body.removeChild(anchor);
        URL.revokeObjectURL(downloadUrl);
    } catch (error) {
        console.error("Failed to download skill file:", error);
        alert("Failed to download file. Please try again.");
    } finally {
        button.disabled = false;
        button.textContent = originalText;
    }
}

document.addEventListener("DOMContentLoaded", () => {
    const downloadBtn = document.getElementById("download-skill-btn");
    if (downloadBtn) {
        downloadBtn.addEventListener("click", downloadSkillFile);
    }

    renderSkillSourceContent();
});
