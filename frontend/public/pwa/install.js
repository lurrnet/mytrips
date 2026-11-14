(() => {
      const setStatus = (id, ok, message) => {
        const element = document.getElementById(id);
        element.className = ok ? 'ok' : 'error';
        element.textContent = (ok ? 'PASS — ' : 'FAIL — ') + message;
      };
      const checkResource = async (url, type) => {
        const response = await fetch(url, { cache: 'no-store', credentials: 'omit' });
        if (!response.ok || response.redirected ||
            !response.headers.get('content-type')?.toLowerCase().startsWith(type)) {
          throw new Error('HTTP ' + response.status + ', ' + (response.headers.get('content-type') || 'no content type'));
        }
        return response;
      };
      let installPrompt;
      const button = document.getElementById('install-btn');
      window.addEventListener('beforeinstallprompt', (event) => {
        event.preventDefault();
        installPrompt = event;
        button.hidden = false;
        button.disabled = false;
      });
      button.addEventListener('click', async () => {
        if (!installPrompt) return;
        const prompt = installPrompt;
        installPrompt = undefined;
        button.disabled = true;
        await prompt.prompt();
      });
      if (window.matchMedia('(display-mode: standalone)').matches) {
        document.getElementById('install-help').textContent =
          'MyTrips is already open as an installed app. No installation is needed.';
      }
      window.addEventListener('appinstalled', () => {
        button.hidden = true;
        document.getElementById('install-help').textContent =
          'MyTrips has been installed. Open it from your home screen.';
      });
      (async () => {
        let manifest;
        try {
          const response = await checkResource('/pwa/manifest.json?v=7', 'application/manifest+json');
          manifest = await response.json();
          if (manifest.name !== 'MyTrips' || manifest.id !== '/' || manifest.start_url !== '/' || !Array.isArray(manifest.icons)) {
            throw new Error('Unexpected manifest fields');
          }
          setStatus('manifest-status', true, 'MyTrips Web Manifest fetched');
        } catch (error) {
          setStatus('manifest-status', false, 'Manifest unavailable: ' + String(error.message || error));
        }
        try {
          if (!manifest) throw new Error('Manifest is unavailable');
          for (const icon of manifest.icons) {
            await checkResource(icon.src, 'image/png');
          }
          setStatus('icon-status', true, 'All manifest PNG icons fetched');
        } catch (error) {
          setStatus('icon-status', false, 'Icons unavailable: ' + String(error.message || error));
        }
        try {
          if (!window.isSecureContext || !('serviceWorker' in navigator)) {
            throw new Error('Secure context/service worker not available');
          }
          const registration = await navigator.serviceWorker.register('/pwa/sw.js', { scope: '/', updateViaCache: 'none' });
          if (registration.scope !== new URL('/', location.href).href) {
            throw new Error('Unexpected worker scope: ' + registration.scope);
          }
          setStatus('worker-status', true, 'Service worker registered at /');
        } catch (error) {
          setStatus('worker-status', false, 'Worker unavailable: ' + String(error.message || error));
        }
      })();
    })();
