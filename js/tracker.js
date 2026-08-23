/**
 * Jawebni Lightweight Analytics & Visitor Tracker
 * Privacy-friendly, fast, zero-dependency session tracker.
 */
(function () {
  'use strict';

  // 1. Session Identification
  function getSessionId() {
    let sid = sessionStorage.getItem('jawebni_sid');
    if (!sid) {
      sid = 'jb_' + Math.random().toString(36).substring(2, 11) + '_' + Date.now().toString(36);
      sessionStorage.setItem('jawebni_sid', sid);
    }
    return sid;
  }

  const sessionId = getSessionId();
  const startTime = Date.now();
  let maxScrollDepth = 0;
  let isTracking = true;

  // 2. Track Scroll Depth
  function updateScrollDepth() {
    const docEl = document.documentElement;
    const body = document.body;
    const scrollTop = window.pageYOffset || docEl.scrollTop || body.scrollTop || 0;
    const scrollHeight = Math.max(
      body.scrollHeight, docEl.scrollHeight,
      body.offsetHeight, docEl.offsetHeight,
      body.clientHeight, docEl.clientHeight
    );
    const clientHeight = docEl.clientHeight || window.innerHeight;
    
    if (scrollHeight > clientHeight) {
      const currentDepth = Math.round(((scrollTop + clientHeight) / scrollHeight) * 100);
      if (currentDepth > maxScrollDepth) {
        maxScrollDepth = Math.min(100, currentDepth);
      }
    } else {
      maxScrollDepth = 100;
    }
  }

  window.addEventListener('scroll', updateScrollDepth, { passive: true });
  updateScrollDepth();

  // 3. Initial Visit Ping
  function trackVisit() {
    const payload = {
      session_id: sessionId,
      referrer: document.referrer || 'Direct / مباشر',
      screen_width: window.innerWidth,
      path: window.location.pathname
    };

    try {
      fetch('/api/track/visit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      }).catch(function () {});
    } catch (e) {}
  }

  // 4. Periodic & Final Duration Ping
  function sendPing(isFinal) {
    if (!isTracking) return;
    updateScrollDepth();
    
    const durationSeconds = Math.round((Date.now() - startTime) / 1000);
    const payload = JSON.stringify({
      session_id: sessionId,
      duration_seconds: durationSeconds,
      scroll_depth: maxScrollDepth
    });

    if (isFinal && navigator.sendBeacon) {
      const blob = new Blob([payload], { type: 'application/json' });
      navigator.sendBeacon('/api/track/ping', blob);
    } else {
      try {
        fetch('/api/track/ping', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: payload,
          keepalive: isFinal === true
        }).catch(function () {});
      } catch (e) {}
    }
  }

  // Start initial visit
  if (document.readyState === 'complete' || document.readyState === 'interactive') {
    trackVisit();
  } else {
    document.addEventListener('DOMContentLoaded', trackVisit);
  }

  // Heartbeat every 15 seconds while tab is active
  const heartbeatInterval = setInterval(function () {
    if (!document.hidden) {
      sendPing(false);
    }
  }, 15000);

  // Send update on visibility change / exit
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'hidden') {
      sendPing(true);
    } else {
      sendPing(false);
    }
  });

  window.addEventListener('pagehide', function () {
    sendPing(true);
  });

  window.addEventListener('beforeunload', function () {
    sendPing(true);
  });

})();
