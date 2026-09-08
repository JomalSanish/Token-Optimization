// T038: Centralized API client wrapper

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
const APP_SECRET = import.meta.env.VITE_APP_SECRET;

/**
 * Enhanced fetch wrapper that injects X-App-Secret.
 * Admin endpoints require an Authorization Bearer token instead, which
 * should be passed explicitly in options.headers if calling an /admin route.
 */
export async function apiFetch(path, options = {}) {
  const url = `${API_BASE_URL}${path.startsWith('/') ? path : '/' + path}`;
  
  const headers = new Headers(options.headers || {});
  
  // Inject default content type if not provided and body is present
  if (options.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  // Inject the shared secret header for normal endpoints.
  // We apply it everywhere; admin endpoints will ignore it and look for Bearer.
  if (APP_SECRET) {
    headers.set('X-App-Secret', APP_SECRET);
  }

  const response = await fetch(url, {
    ...options,
    headers,
  });

  // Automatically parse JSON if the response is application/json
  const contentType = response.headers.get('content-type');
  const isJson = contentType && contentType.includes('application/json');
  
  if (!response.ok) {
    let errorDetail = response.statusText;
    if (isJson) {
      try {
        const errorData = await response.json();
        errorDetail = errorData.detail || errorDetail;
      } catch (e) {
        // Ignore JSON parse errors on error responses
      }
    }
    const error = new Error(`API Error ${response.status}: ${errorDetail}`);
    error.status = response.status;
    error.detail = errorDetail;
    error.response = response;
    throw error;
  }

  if (isJson) {
    return response.json();
  }
  
  return response.text();
}

/**
 * Admin wrapper that automatically injects the Bearer token from the environment.
 */
export async function adminApiFetch(path, options = {}) {
  const ADMIN_SECRET = import.meta.env.VITE_ADMIN_SECRET || 'test_admin_secret';
  
  const headers = new Headers(options.headers || {});
  headers.set('Authorization', `Bearer ${ADMIN_SECRET}`);
  
  return apiFetch(path, {
    ...options,
    headers
  });
}

