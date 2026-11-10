/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Core service base URL, e.g. `http://127.0.0.1:8765`. */
  readonly VITE_JARVIS_CORE_URL?: string;
  /** Name shown before the core service connects. */
  readonly VITE_JARVIS_USER_NAME?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
