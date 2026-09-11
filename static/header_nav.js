(() => {
  const toggle = document.querySelector(".mobile-nav-toggle");
  const nav = document.querySelector("#site-navigation");
  if (!toggle || !nav) return;

  const close = () => {
    toggle.setAttribute("aria-expanded", "false");
    toggle.setAttribute("aria-label", "Open navigation");
    nav.classList.remove("mobile-open");
  };

  toggle.addEventListener("click", () => {
    const open = toggle.getAttribute("aria-expanded") !== "true";
    toggle.setAttribute("aria-expanded", String(open));
    toggle.setAttribute("aria-label", open ? "Close navigation" : "Open navigation");
    nav.classList.toggle("mobile-open", open);
  });
  nav.querySelectorAll("a").forEach(link => link.addEventListener("click", close));
  document.addEventListener("click", event => {
    if (!nav.contains(event.target) && !toggle.contains(event.target)) close();
  });
  document.addEventListener("keydown", event => { if (event.key === "Escape") close(); });
})();

(() => {
  const banner = document.querySelector("#live-auction-banner");
  if (!banner) return;
  banner.addEventListener("click", event => {
    const destination = new URL(banner.href, window.location.origin);
    if (destination.pathname !== window.location.pathname) return;
    event.preventDefault();
    window.dispatchEvent(new Event("endgame:open-live-auction"));
  });
  const boss = banner.querySelector("[data-live-auction-boss]");
  const timer = banner.querySelector("[data-live-auction-time]");
  let activeAuction = null;

  const secondsLeft = endsAt => Math.max(0, Math.ceil((Date.parse(`${endsAt}Z`) - Date.now()) / 1000));
  const render = () => {
    if (!activeAuction) return;
    const seconds = secondsLeft(activeAuction.ends_at);
    if (!seconds) { banner.hidden = true; activeAuction = null; return; }
    boss.textContent = activeAuction.boss;
    timer.textContent = `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
    banner.hidden = false;
  };
  const update = payload => {
    activeAuction = payload.auctions?.find(auction => auction.status === "Active" && !auction.paused) || null;
    banner.hidden = !activeAuction;
    render();
  };
  window.addEventListener("endgame:auctions-updated", event => update(event.detail));
  if (window.EndgameAuctionPolling.payload) update(window.EndgameAuctionPolling.payload);
  window.EndgameAuctionPolling.start();
  setInterval(render, 1000);
})();
