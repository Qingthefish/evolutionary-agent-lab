// Agent Lab prototype (2026-11-27): hide Open WebUI menu items the classroom platform cannot serve
// and that have no stable selector. Archive moves a chat into a list only reachable from the hidden
// user menu, so an archived chat could not be found again.
(() => {
  const HIDDEN = new Set(["归档", "Archive"]);
  const sweep = () => {
    document.querySelectorAll('[role="menuitem"], [role="menu"] button, [data-menu-item]').forEach((item) => {
      if (HIDDEN.has(item.textContent.trim())) item.style.display = "none";
    });
  };
  new MutationObserver(sweep).observe(document.documentElement, { childList: true, subtree: true });
})();
