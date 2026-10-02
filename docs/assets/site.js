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
  const leaderScoreLead = document.getElementById('leader-score-lead');
  const leaderScore2 = document.getElementById('leader-score-2');
  const leaderName = document.getElementById('leader-name');
  const leaderName2 = document.getElementById('leader-name-2');
  const feedBadge = document.getElementById('feed-status');
  const retrievedAt = document.getElementById('leaderboard-retrieved');
  if (!rows) return;

  fetch('data/leaderboard.json', { cache: 'no-store' })
    .then((response) => {
      if (response.ok) return response.json();
      return fetch('docs/data/leaderboard.json', { cache: 'no-store' }).then((fallback) => {
        if (!fallback.ok) throw new Error(`HTTP ${fallback.status}`);
        return fallback.json();
      });
    })
    .then((data) => {
      const entries = Array.isArray(data.rows) ? data.rows : [];
      const maxRank = rows.children.length >= 25 ? 25 : 10;
      const topRows = entries.filter((entry) => entry.rank <= 10 || entry.rank <= maxRank).sort((a, b) => a.rank - b.rank).slice(0, maxRank);
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
        const scoreText = Number(leader.score).toFixed(4);
        if (leaderScore) leaderScore.textContent = scoreText;
        if (leaderScoreLead) leaderScoreLead.textContent = scoreText;
        if (leaderScore2) leaderScore2.textContent = scoreText;
        if (leaderName) leaderName.textContent = leader.participant;
        if (leaderName2) leaderName2.textContent = leader.participant;
      }
      if (retrievedAt) retrievedAt.textContent = `Snapshot / refresh: ${data.retrieved_utc || 'date not supplied'}`;
      if (feedBadge) {
        const isLive = data.source_status === 'live';
        const refreshState = data.refresh_status?.status;
        const refreshFailed = refreshState === 'stale-snapshot-retained' || refreshState === 'unavailable-no-snapshot';
        const manual = refreshState === 'dated-snapshot' || refreshState === 'manual-dated-snapshot';
        feedBadge.textContent = isLive
          ? 'Live feed refreshed'
          : (refreshFailed ? 'Dated snapshot · automated refresh failed'
            : (manual ? 'Dated snapshot · captured from the official page by hand' : 'Dated snapshot'));
        feedBadge.className = `status ${isLive ? 'status-ok' : (refreshFailed ? 'status-warning' : 'status-neutral')}`;
        const why = data.refresh_status?.error || data.capture_method;
        if ((refreshFailed || manual) && why) feedBadge.title = why;
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
