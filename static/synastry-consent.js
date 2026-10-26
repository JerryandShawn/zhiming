"use strict";

// The authenticated native card, never model text, controls the confirmation action.
async function renderSynastryConsents(root, { apiJson, conversationId, isCurrent }) {
  const generation = (root._synastryGeneration || 0) + 1;
  root._synastryGeneration = generation;
  root.replaceChildren();
  const current = () => root.isConnected && root._synastryGeneration === generation && isCurrent();
  const text = (tag, content, className = "") => {
    const node = document.createElement(tag);
    node.textContent = content;
    node.className = className;
    return node;
  };
  try {
    const cards = await apiJson("/api/synastry/consents?conversation_id=" + encodeURIComponent(conversationId));
    if (!current()) return;
    if (!Array.isArray(cards)) throw Error("确认状态暂不可用，请刷新对话后重试。");
    root.replaceChildren();
    for (const card of cards) {
      if (!card || !["pending_confirmation", "granted"].includes(card.state) ||
          typeof card.id !== "string" || !Number.isInteger(card.revision) || typeof card.message !== "string") continue;
      const section = document.createElement("section");
      section.className = "clarification-form";
      section.setAttribute("aria-label", "本次合盘确认");
      const kind = { romantic: "感情相处", friendship: "朋友相处", collaboration: "合作相处" }[card.kind];
      section.append(text("h3", "确认本次合盘"), text("p", card.message));
      if (kind) section.append(text("p", "这次比较：" + kind, "muted"));
      const status = text("p", card.state === "granted" ? "已确认本次使用。合盘结果尚未生成。" : "尚未授权使用对方出生资料。", "muted");
      status.setAttribute("role", "status");
      section.append(status);
      if (card.state === "pending_confirmation") {
        const button = text("button", "对方知情并同意，只做本次合盘", "btn-gold");
        button.type = "button";
        let requestId;
        button.addEventListener("click", async () => {
          if (button.disabled || !current()) return;
          requestId ||= crypto.randomUUID();
          button.disabled = true;
          status.textContent = "正在保存本次确认…";
          try {
            const response = await apiJson("/api/synastry/consents/" + encodeURIComponent(card.id) + "/confirm", {
              method: "POST",
              body: JSON.stringify({ confirmed: true, expected_revision: card.revision, request_id: requestId })
            });
            if (!current()) return;
            if (response.id !== card.id || response.state !== "granted" || response.uses_left !== 1) {
              throw Error("本次确认已变化，请刷新对话后核对。");
            }
            button.remove();
            status.textContent = "已确认本次使用。合盘结果尚未生成。";
          } catch {
            if (!current()) return;
            button.disabled = false;
            status.textContent = "确认尚未完成，可重试；若资料已改动，请刷新对话重新核对。";
          }
        });
        section.append(button);
      }
      root.append(section);
    }
  } catch {
    if (!current()) return;
    root.replaceChildren(text("p", "合盘确认状态暂不可用，请刷新对话后重试。", "muted"));
  }
}
