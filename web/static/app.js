function getTime() {
  return new Date().toLocaleTimeString('he-IL', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function addLog(message, type = 'info') {
  const logBox = document.getElementById('logBox');
  if (!logBox) return;
  
  const emptyMsg = logBox.querySelector('.result-empty');
  if (emptyMsg) emptyMsg.remove();
  
  const entry = document.createElement('div');
  entry.className = `log-entry ${type}`;
  entry.innerHTML = `<span class="log-time">${getTime()}</span><span class="log-msg">${message}</span>`;
  logBox.appendChild(entry);
  logBox.scrollTop = logBox.scrollHeight;
}

function clearLog() {
  const logBox = document.getElementById('logBox');
  if (logBox) {
    logBox.innerHTML = '<div class="result-empty">לוג נוקה</div>';
  }
}

function renderResults(data) {
  const container = document.getElementById('resultsContainer');
  if (!container) return;
  
  if (!data.ok) {
    container.innerHTML = `<div class="result-card error">
      <div class="result-header">
        <span class="result-order">שגיאה</span>
        <span class="result-status error">ERROR</span>
      </div>
      <div class="result-tickets">${data.error || 'שגיאה לא ידועה'}</div>
    </div>`;
    return;
  }
  
  if (!data.results || data.results.length === 0) {
    container.innerHTML = '<div class="result-empty">לא נמצאו הזמנות לעיבוד</div>';
    return;
  }
  
  let html = '';
  for (const r of data.results) {
    const statusClass = r.status === 'ASSIGNED' ? 'assigned' : 
                        r.status === 'NO_AVAILABLE_TICKETS' ? 'no-tickets' : 
                        r.status === 'ALREADY_ASSIGNED' ? 'already' : 'error';
    const statusText = r.status === 'ASSIGNED' ? 'הוקצה' : 
                       r.status === 'NO_AVAILABLE_TICKETS' ? 'אין כרטיסים' : 
                       r.status === 'ALREADY_ASSIGNED' ? 'כבר שובץ' : r.status;
    
    let ticketsInfo = '';
    if (r.tickets && r.tickets.length > 0) {
      const ticketsList = r.tickets.map(t => `בלוק ${t.block}, שורה ${t.row}, מושב ${t.seat}`).join(' | ');
      ticketsInfo = `<div class="result-tickets">${ticketsList}</div>`;
    } else if (r.reason) {
      ticketsInfo = `<div class="result-tickets">סיבה: ${r.reason}</div>`;
    }
    
    html += `<div class="result-card ${statusClass}">
      <div class="result-header">
        <span class="result-order">הזמנה: ${r.order}</span>
        <span class="result-status ${statusClass}">${statusText}</span>
      </div>
      ${ticketsInfo}
    </div>`;
  }
  
  container.innerHTML = html;
}

let pollInterval = null;

async function pollLogs() {
  try {
    const res = await fetch('/logs/poll');
    const data = await res.json();
    for (const log of data.logs) {
      addLog(log.message, log.level);
    }
  } catch(e) {}
}

function startPolling() {
  if (pollInterval) clearInterval(pollInterval);
  pollInterval = setInterval(pollLogs, 300);
}

function stopPolling() {
  if (pollInterval) {
    clearInterval(pollInterval);
    pollInterval = null;
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const startBtn = document.getElementById('startBtn');
  const continueBtn = document.getElementById('continueBtn');
  const stopBtn = document.getElementById('stopBtn');
  const statusText = document.getElementById('statusText');
  const clearLogBtn = document.getElementById('clearLogBtn');
  
  const progressContainer = document.getElementById('progressContainer');
  const progressBar = document.getElementById('progressBar');
  const progressStep = document.getElementById('progressStep');

  function showProgress(step, percent) {
    if (progressContainer) {
      progressContainer.classList.add('active');
      progressBar.style.width = percent + '%';
      progressStep.textContent = step;
    }
  }

  function hideProgress() {
    if (progressContainer) {
      progressContainer.classList.remove('active');
      progressBar.style.width = '0%';
    }
  }

  function setStatus(text) {
    if (statusText) statusText.textContent = text;
  }

  function setRunning(isRunning) {
    if (startBtn) startBtn.disabled = isRunning;
    if (continueBtn) continueBtn.disabled = isRunning;
    if (stopBtn) stopBtn.disabled = !isRunning;
  }

  async function checkProgress() {
    try {
      const res = await fetch('/progress_status');
      const data = await res.json();
      if (data.has_progress) {
        if (continueBtn) continueBtn.disabled = false;
        setStatus(`נעצר בהזמנה ${data.last_index}/${data.total}`);
      } else {
        setStatus('מוכן');
      }
    } catch(e) {
      setStatus('מוכן');
    }
  }

  if (clearLogBtn) {
    clearLogBtn.addEventListener('click', clearLog);
  }

  async function runAllocation(endpoint, isRestart) {
    setRunning(true);
    setStatus('רץ...');
    showProgress('מעבד הזמנות...', 30);
    startPolling();
    
    try {
      const res = await fetch(endpoint, { method: 'POST' });
      const data = await res.json();
      
      if (!data.ok) {
        showProgress('שגיאה!', 100);
        addLog(`שגיאה: ${data.error}`, 'error');
        setStatus('שגיאה');
        await new Promise(r => setTimeout(r, 500));
        hideProgress();
        return;
      }
      
      while (true) {
        await pollLogs();
        const statusRes = await fetch('/run_status');
        const status = await statusRes.json();
        
        if (!status.is_running) {
          await pollLogs();
          if (status.results) {
            showProgress('הושלם!', 100);
            renderResults(status.results);
          }
          setStatus('הושלם');
          await new Promise(r => setTimeout(r, 500));
          hideProgress();
          break;
        }
        await new Promise(r => setTimeout(r, 300));
      }
    } catch (e) {
      showProgress('שגיאה!', 100);
      addLog(`שגיאה: ${e.message}`, 'error');
      setStatus('שגיאה');
      await new Promise(r => setTimeout(r, 500));
      hideProgress();
    } finally {
      stopPolling();
      setRunning(false);
      checkProgress();
    }
  }

  if (startBtn) {
    startBtn.addEventListener('click', () => runAllocation('/run_restart', true));
  }

  if (continueBtn) {
    continueBtn.addEventListener('click', () => runAllocation('/run_continue', false));
  }

  if (stopBtn) {
    stopBtn.addEventListener('click', async () => {
      stopBtn.disabled = true;
      setStatus('עוצר...');
      try {
        await fetch('/stop', { method: 'POST' });
      } catch(e) {}
    });
  }

  checkProgress();
});
