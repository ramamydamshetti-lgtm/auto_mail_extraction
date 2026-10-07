/**
 * Metaforge Application Frontend Logic
 */

document.addEventListener('DOMContentLoaded', () => {
  // Setup Table Select-All Checkbox
  const thCheckbox = document.querySelector('.req-data-table th input[type="checkbox"]');
  if (thCheckbox) {
    thCheckbox.addEventListener('change', (e) => {
      const isChecked = e.target.checked;
      const tdCheckboxes = document.querySelectorAll('.req-data-table td input[type="checkbox"]');
      tdCheckboxes.forEach(cb => {
        cb.checked = isChecked;
      });
    });
  }

  // Sidebar Toggle
  const sidebarToggleBtn = document.querySelector('.sidebar-menu-btn');
  const sidebar = document.querySelector('.sidebar');
  if (sidebarToggleBtn && sidebar) {
    sidebarToggleBtn.addEventListener('click', () => {
      sidebar.classList.toggle('collapsed');
    });
  }
});

/**
 * Dynamic Tab Switching for Requirement Details
 * @param {string} tabName 
 * @param {HTMLElement} btnEl 
 */
function switchTab(tabName, btnEl) {
  // Hide all tab panes
  const allPanes = document.querySelectorAll('.tab-pane');
  allPanes.forEach(pane => {
    pane.style.display = 'none';
  });

  // Remove active class from all tab buttons
  const allBtns = document.querySelectorAll('.tab-btn');
  allBtns.forEach(btn => {
    btn.classList.remove('active');
  });

  // Show selected tab pane
  const targetPane = document.getElementById(`tab-${tabName}`);
  if (targetPane) {
    targetPane.style.display = 'block';
  }

  // Add active class to clicked button
  if (btnEl) {
    btnEl.classList.add('active');
  }
}

/**
 * UPDATE STATUS Widget Logic (Matches Uploaded Design)
 * Supports both detail view and list view table rows.
 */
function toggleStatusMenu(e, reqId) {
  if (e) e.stopPropagation();
  let popover = null;
  let btn = null;

  if (reqId) {
    popover = document.getElementById('popover-status-' + reqId);
    btn = document.getElementById('btn-status-' + reqId);
  } else {
    popover = document.getElementById('statusPopoverMenu');
    btn = document.getElementById('updateStatusBtn');
  }

  // Close any other open popovers
  document.querySelectorAll('.update-status-popover.active').forEach(p => {
    if (p !== popover) p.classList.remove('active');
  });
  document.querySelectorAll('.update-status-pill-btn.open').forEach(b => {
    if (b !== btn) b.classList.remove('open');
  });

  if (popover) {
    popover.classList.toggle('active');
    if (btn) btn.classList.toggle('open');
  }
}

document.addEventListener('click', function(e) {
  if (!e.target.closest('.update-status-dropdown-wrapper') && !e.target.closest('.update-status-widget-container')) {
    document.querySelectorAll('.update-status-popover.active').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.update-status-pill-btn.open').forEach(b => b.classList.remove('open'));
  }
});

async function selectRequirementStatus(reqId, statusKey, statusLabel, el) {
  try {
    const res = await fetch('/api/requirement/' + encodeURIComponent(reqId) + '/status', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: statusKey, changed_by: 'USER' })
    });
    const data = await res.json();
    if (data.success) {
      // Find wrapper for this reqId if in list view, or detail page
      const btnText = document.getElementById('text-status-' + reqId) || document.getElementById('currStatusText');
      const btnIcon = document.getElementById('icon-status-' + reqId) || document.getElementById('currStatusIcon');
      const popover = document.getElementById('popover-status-' + reqId) || document.getElementById('statusPopoverMenu');
      const btn = document.getElementById('btn-status-' + reqId) || document.getElementById('updateStatusBtn');

      if (el && popover) {
        popover.querySelectorAll('.status-option-item').forEach(item => item.classList.remove('active-selected'));
        el.classList.add('active-selected');
      }

      if (btnText) {
        btnText.textContent = statusLabel;
        if (statusKey === 'open') {
          btnText.style.color = '#0d9488';
          if (btnIcon) {
            btnIcon.className = 'status-icon-dot-green';
            btnIcon.innerHTML = '';
          }
        } else if (statusKey === 'hold') {
          btnText.style.color = '#1e3a8a';
          if (btnIcon) {
            btnIcon.className = 'status-icon-box status-icon-hold';
            btnIcon.innerHTML = '<svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16" rx="1"></rect><rect x="14" y="4" width="4" height="16" rx="1"></rect></svg>';
          }
        } else if (statusKey === 'reopen') {
          btnText.style.color = '#1e3a8a';
          if (btnIcon) {
            btnIcon.className = 'status-icon-box status-icon-reopen';
            btnIcon.innerHTML = '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="23 4 23 10 17 10"></polyline><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path></svg>';
          }
        } else {
          btnText.style.color = '#7e22ce';
          if (btnIcon) {
            btnIcon.className = 'status-icon-box status-icon-custom';
            btnIcon.innerHTML = '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20h9"></path><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"></path></svg>';
          }
        }
      }

      if (popover) popover.classList.remove('active');
      if (btn) btn.classList.remove('open');
    } else {
      alert('Error updating status: ' + (data.error || 'Failed'));
    }
  } catch (err) {
    alert('Failed to send status update: ' + err);
  }
}

function promptCustomStatus(reqId) {
  const custom = prompt("Enter custom status or note:");
  if (custom && custom.trim()) {
    selectRequirementStatus(reqId, 'custom', custom.trim(), null);
  }
}

async function changeRowStatus(reqId, selectEl) {
  const newStatus = selectEl.value;
  try {
    const res = await fetch('/api/requirement/' + encodeURIComponent(reqId) + '/status', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: newStatus, changed_by: 'USER' })
    });
    const data = await res.json();
    if (data.success) {
      selectEl.className = 'row-status-select status-' + newStatus;
    } else {
      alert('Error updating status: ' + (data.error || 'Failed'));
    }
  } catch (err) {
    alert('Failed to send status update: ' + err);
  }
}
