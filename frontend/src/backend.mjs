// Route every API request via one named backend, never by arbitrary user URL.
export function isLoopbackFrontend(hostname) {
  return ['127.0.0.1', 'localhost', '::1', '[::1]'].includes(hostname);
}
export function defaultApiBackend(hostname) {
  return isLoopbackFrontend(hostname) ? 'local' : 'render';
}
export function resolveApiUrl(path, backend, hostname) {
  if (typeof path !== 'string' || !path.startsWith('/api/v1/'))
    throw new Error('Only versioned /api/v1/ paths can be requested.');
  if (backend === 'render')
    return isLoopbackFrontend(hostname) ? '/render-api' + path.slice('/api'.length) : path;
  if (backend === 'local') {
    if (!isLoopbackFrontend(hostname))
      throw new Error('Local API requires the locally served frontend (127.0.0.1:5173). Open the local frontend or select Render.');
    return path;
  }
  throw new Error('Unknown API backend.');
}
