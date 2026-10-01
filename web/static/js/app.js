document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-server-action]').forEach((button) => {
    button.addEventListener('click', async () => {
      const action = button.dataset.serverAction;
      const serverId = button.dataset.serverId;
      const originalText = button.textContent;
      const originalClass = button.className;
      
      button.disabled = true;
      button.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Processing...';

      try {
        const response = await fetch(`/api/server/${serverId}/${action}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
        });
        const payload = await response.json();
        if (payload.status === 'ok') {
          setTimeout(() => {
            window.location.reload();
          }, 500);
        } else {
          showAlert(payload.message || 'Action failed', 'danger');
        }
      } catch (error) {
        showAlert('Request failed: ' + error.message, 'danger');
      } finally {
        button.disabled = false;
        button.textContent = originalText;
        button.className = originalClass;
      }
    });
  });

  // Auto-refresh monitoring data every 5 seconds
  const monitoringElements = document.querySelectorAll('[data-monitor]');
  if (monitoringElements.length > 0) {
    setInterval(refreshMonitoring, 5000);
  }
});

function showAlert(message, type = 'info') {
  const alertDiv = document.createElement('div');
  alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
  alertDiv.role = 'alert';
  alertDiv.innerHTML = `
    ${message}
    <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
  `;
  const container = document.querySelector('.container-fluid');
  container.insertBefore(alertDiv, container.firstChild);
  
  setTimeout(() => {
    alertDiv.remove();
  }, 5000);
}

function refreshMonitoring() {
  const elements = document.querySelectorAll('[data-monitor]');
  elements.forEach(el => {
    const serverId = el.dataset.monitor;
    // Add live monitoring refresh here if needed
  });
}
