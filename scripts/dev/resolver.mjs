import { existsSync } from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');

function tryExt(base, spec) {
  for (const ext of ['', '.js', '.jsx', '/index.js', '/index.jsx']) {
    const candidate = path.resolve(base, spec + ext);
    if (existsSync(candidate) && !existsSync(path.join(candidate, '.'))) return candidate;
    if (existsSync(candidate) && path.extname(candidate)) return candidate;
  }
  return null;
}

export function resolve(specifier, context, next) {
  if (specifier.startsWith('@/')) {
    const hit = tryExt(path.join(ROOT, 'src'), specifier.slice(2));
    if (hit) return next(pathToFileURL(hit).href, context);
  }
  if (specifier.startsWith('.') && !path.extname(specifier)) {
    const hit = tryExt(path.dirname(fileURLToPath(context.parentURL)), specifier);
    if (hit) return next(pathToFileURL(hit).href, context);
  }
  return next(specifier, context);
}

/** Vite exposes `import.meta.env`; Node does not. Inject it for these scripts. */
export function load(url, context, next) {
  return next(url, context).then((result) => {
    if (result.format === 'module' && typeof result.source !== 'undefined' && url.includes('/src/')) {
      const src = result.source.toString();
      if (src.includes('import.meta.env')) {
        return { ...result, source: `import.meta.env = import.meta.env || { VITE_API_BASE_URL: '/api', VITE_USE_MOCK_API: 'true' };\n${src}` };
      }
    }
    return result;
  });
}
