(() => {
  if (window.EndgameAuctionPolling) return;

  const LIVE_INTERVAL = 5000;
  let payload = null;
  let timer = null;
  let request = null;
  let started = false;
  let detailed = false;

  const hasLiveAuction = value => value?.auctions?.some(auction => auction.status === "Active") || false;
  const schedule = () => {
    clearTimeout(timer);
    timer = null;
    if (document.hidden) return;
    if (hasLiveAuction(payload)) timer = setTimeout(refresh, LIVE_INTERVAL);
  };
  const publish = value => {
    payload = value;
    window.dispatchEvent(new CustomEvent("endgame:auctions-updated", {detail: value}));
  };
  async function refresh() {
    if (document.hidden) {
      schedule();
      return null;
    }
    if (request) return request;
    clearTimeout(timer);
    timer = null;
    const endpoint = detailed ? "/api/endgame/auctions" : "/api/endgame/auction-status";
    request = fetch(endpoint, {headers: {Accept: "application/json"}})
      .then(response => {
        if (!response.ok) throw new Error("Could not refresh auctions.");
        return response.json();
      })
      .then(value => {
        publish(value);
        return value;
      })
      .catch(() => null)
      .finally(() => {
        request = null;
        schedule();
      });
    return request;
  }
  const start = () => {
    if (started) return;
    started = true;
    refresh();
  };

  document.addEventListener("visibilitychange", () => {
    clearTimeout(timer);
    timer = null;
    if (!document.hidden && started) refresh();
  });

  window.EndgameAuctionPolling = {
    get payload() { return payload; },
    requireDetails() { detailed = true; },
    refresh,
    start,
  };
})();
