"use strict";

// Native completed tool evidence offers navigation; only the existing form saves facts.
async function renderP8ProfileRequirements(root, { apiJson, conversationId, isCurrent, openProfile }) {
  const generation = (root._profileGeneration || 0) + 1;
  root._profileGeneration = generation;
  root.replaceChildren();
  const current = () => root.isConnected && root._profileGeneration === generation && isCurrent();
  const text = (tag, value) => {
    const node = document.createElement(tag);
    node.textContent = value;
    return node;
  };
  try {
    const cards = await apiJson("/api/subjects/self/profile/requirements?conversation_id=" + encodeURIComponent(conversationId));
    if (!current()) return;
    if (!Array.isArray(cards)) throw Error("invalid native requirements");
    for (const card of cards.slice(0, 1)) {
      if (card?.action !== "open_profile" || !Array.isArray(card.labels) || !card.labels.length ||
          !card.labels.every(value => typeof value === "string") || typeof card.message !== "string") continue;
      const section = document.createElement("section");
      section.className = "clarification-form";
      section.setAttribute("aria-label", "核对排盘资料");
      section.append(text("h3", "先核对出生资料"), text("p", card.message));
      const list = document.createElement("ul");
      card.labels.forEach(label => list.append(text("li", label)));
      section.append(list);
      const button = text("button", "打开资料确认表");
      button.className = "btn-gold";
      button.type = "button";
      const status = text("p", "打开表单不会保存资料，也不会自动重新计算。");
      status.className = "muted";
      status.setAttribute("role", "status");
      button.addEventListener("click", async () => {
        if (!current() || button.disabled) return;
        button.disabled = true;
        try {
          await openProfile();
        } catch {
          if (current()) status.textContent = "表单暂时无法打开，请从“我的档案”重新核对。";
        } finally {
          if (current()) button.disabled = false;
        }
      });
      section.append(button, status);
      root.append(section);
    }
  } catch {
    if (current()) root.replaceChildren(text("p", "资料核对入口暂不可用，请从“我的档案”打开确认表。"));
  }
}
