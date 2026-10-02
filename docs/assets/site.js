(() => {
  const copyButtons = document.querySelectorAll('[data-copy-target]');
  for (const button of copyButtons) {
    button.addEventListener('click', async () => {
      const target = document.getElementById(button.getAttribute('data-copy-target'));
      if (!target) return;
      try {
        await navigator.clipboard.writeText(target.value || target.textContent || '');
        const old = button.textContent;
        button.textContent = 'Copied';
        window.setTimeout(() => { button.textContent = old; }, 1400);
      } catch (_) {
        target.focus();
        target.select?.();
        button.textContent = 'Select and copy';
      }
    });
  }

  const rows = document.getElementById('leaderboard-rows');
  const leaderScore = document.getElementById('leader-score');
  const leaderName = document.getElementById('leader-name');
  const feedBadge = document.getElementById('feed-status');
  const retrievedAt = document.getElementById('leaderboard-retrieved');
  if (!rows) return;

  fetch('data/leaderboard.json', { cache: 'no-store' })
    .then((response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.json();
    })
    .then((data) => {
      const entries = Array.isArray(data.rows) ? data.rows : [];
      const topRows = entries.filter((entry) => entry.rank <= 10).sort((a, b) => a.rank - b.rank);
      rows.replaceChildren();
      for (const entry of topRows) {
        const tr = document.createElement('tr');
        for (const value of [entry.rank, entry.participant, Number(entry.score).toFixed(4)]) {
          const td = document.createElement('td');
          td.textContent = value;
          if (typeof value === 'number' || /^0\.\d{4}$/.test(String(value))) td.className = 'numeric';
          tr.appendChild(td);
        }
        rows.appendChild(tr);
      }
      const leader = topRows[0];
      if (leader) {
        if (leaderScore) leaderScore.textContent = Number(leader.score).toFixed(4);
        if (leaderName) leaderName.textContent = leader.participant;
      }
      if (retrievedAt) retrievedAt.textContent = `Snapshot / refresh: ${data.retrieved_utc || 'date not supplied'}`;
      if (feedBadge) {
        const isLive = data.source_status === 'live';
        const refreshFailed = data.refresh_status?.status === 'stale-snapshot-retained';
        feedBadge.textContent = isLive
          ? 'Live feed refreshed'
          : (refreshFailed ? 'Dated snapshot · refresh failed' : 'Dated snapshot');
        feedBadge.className = `status ${isLive ? 'status-ok' : (refreshFailed ? 'status-warning' : 'status-neutral')}`;
        if (refreshFailed && data.refresh_status?.error) feedBadge.title = data.refresh_status.error;
      }
    })
    .catch((error) => {
      if (feedBadge) {
        feedBadge.textContent = 'Feed unavailable; use official leaderboard';
        feedBadge.className = 'status status-warning';
      }
      console.error('Leaderboard JSON could not be loaded:', error);
    });
})();
