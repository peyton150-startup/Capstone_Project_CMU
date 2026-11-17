export type ApiBackend = 'local' | 'render';
export function isLoopbackFrontend(hostname: string): boolean;
export function defaultApiBackend(hostname: string): ApiBackend;
export function resolveApiUrl(path: string, backend: ApiBackend, hostname: string): string;
