document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-server-action]').forEach((button) => {
    button.addEventListener('click', async () => {
      const action = button.dataset.serverAction;
      const serverId = button.dataset.serverId;
      const originalText = button.textContent;
      button.disabled = true;
      button.textContent = '...';

      try {
        const response = await fetch(`/api/server/${serverId}/${action}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
        });
        const payload = await response.json();
        if (payload.status === 'ok') {
          window.location.reload();
        } else {
          alert(payload.message || 'Action failed');
        }
      } catch (error) {
        alert('Request failed');
      } finally {
        button.disabled = false;
        button.textContent = originalText;
      }
    });
  });
});
